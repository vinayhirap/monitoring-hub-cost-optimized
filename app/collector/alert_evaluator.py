# app/collector/alert_evaluator.py
"""
Production alert evaluator.
- Reads latest metric per resource from metrics table
- Joins with thresholds per service type and account
- Inserts alerts for breaches
- Resolves alerts when metric returns to normal
- Publishes new alerts to Redis for real-time WebSocket push
"""
import json
import logging
from datetime import datetime
from app.db import get_connection
from app.ws.publisher import publish_alert

logger = logging.getLogger(__name__)


def compare(value, threshold, op):
    if threshold is None or value is None:
        return False
    try:
        v = float(value)
        t = float(threshold)
    except (TypeError, ValueError):
        return False
    ops = {
        ">":  v >  t,
        ">=": v >= t,
        "<":  v <  t,
        "<=": v <= t,
    }
    return ops.get(op, False)


def evaluate_alerts():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ── Fetch latest metric per resource+metric combo ─────────
    # Joins resources → thresholds → metric_catalog
    # Only evaluates metrics that have a threshold configured
    cursor.execute("""
        SELECT
            m.resource_id          AS db_resource_id,
            r.resource_id          AS aws_resource_id,
            r.resource_type,
            r.aws_account_id,
            r.tags,
            r.region,
            m.metric_name,
            m.metric_value,
            m.metric_timestamp,
            t.id                   AS threshold_id,
            t.warning_value,
            t.critical_value,
            t.comparison
        FROM metrics m
        JOIN resources r
            ON r.id = m.resource_id
        JOIN metric_catalog mc
            ON mc.metric_name = m.metric_name
        JOIN thresholds t
            ON t.metric_id       = mc.id
           AND t.resource_type   = r.resource_type
           AND t.aws_account_id  = r.aws_account_id
           AND t.enabled         = 1
        JOIN (
            SELECT resource_id, metric_name, MAX(metric_timestamp) AS ts
            FROM metrics
            GROUP BY resource_id, metric_name
        ) latest
            ON latest.resource_id = m.resource_id
           AND latest.metric_name = m.metric_name
           AND latest.ts          = m.metric_timestamp
        WHERE m.metric_timestamp >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
    """)

    rows = cursor.fetchall()
    logger.info(f"Evaluating {len(rows)} metric readings")

    new_alerts    = 0
    resolved      = 0
    already_open  = 0

    for row in rows:
        aws_resource_id = row["aws_resource_id"]
        metric_name     = row["metric_name"]
        metric_value    = row["metric_value"]
        resource_type   = row["resource_type"]
        aws_account_id  = row["aws_account_id"]

        # Parse environment from tags
        try:
            tags = json.loads(row["tags"] or "{}")
        except Exception:
            tags = {}
        environment = tags.get("environment", tags.get("Environment", "prod")).lower()

        # ── Threshold check ───────────────────────────────────
        is_critical = compare(metric_value, row["critical_value"], row["comparison"])
        is_warning  = compare(metric_value, row["warning_value"],  row["comparison"])

        if not is_critical and not is_warning:
            # Metric is healthy — resolve any open alert
            cursor.execute("""
                UPDATE alerts
                SET status      = 'resolved',
                    resolved_at = NOW()
                WHERE resource_id = %s
                  AND metric_name = %s
                  AND status      = 'active'
            """, (aws_resource_id, metric_name))
            if cursor.rowcount > 0:
                resolved += cursor.rowcount
            continue

        # ── Determine severity ────────────────────────────────
        # Critical threshold breach always = CRITICAL regardless of environment
        # Warning threshold breach severity depends on environment
        if is_critical:
            severity = "CRITICAL"
        else:
            # Warning breach
            if environment in ("prod", "production"):
                severity = "WARNING"
            else:
                severity = "INFO"

        threshold_value = row["critical_value"] if is_critical else row["warning_value"]

        # ── Check for existing open alert ─────────────────────
        cursor.execute("""
            SELECT id, severity FROM alerts
            WHERE resource_id = %s
              AND metric_name = %s
              AND status      = 'active'
            LIMIT 1
        """, (aws_resource_id, metric_name))
        existing = cursor.fetchone()

        if existing:
            # Escalate severity if needed (WARNING → CRITICAL)
            if existing["severity"] != severity and severity == "CRITICAL":
                cursor.execute("""
                    UPDATE alerts
                    SET severity      = %s,
                        current_value = %s,
                        threshold     = %s
                    WHERE id = %s
                """, (severity, metric_value, threshold_value, existing["id"]))
                logger.debug(f"Escalated alert {existing['id']} to CRITICAL")
            already_open += 1
            continue

        # ── Insert new alert ──────────────────────────────────
        cursor.execute("""
            INSERT INTO alerts
                (resource_id, metric_name, severity,
                 environment, status, triggered_at,
                 current_value, threshold)
            VALUES (%s, %s, %s, %s, 'active', %s, %s, %s)
        """, (
            aws_resource_id,
            metric_name,
            severity,
            environment,
            datetime.utcnow(),
            metric_value,
            threshold_value,
        ))

        new_alert_id = cursor.lastrowid
        new_alerts  += 1

        # ── Publish to Redis for real-time WebSocket push ─────
        try:
            publish_alert(
                alert_id   = new_alert_id,
                severity   = severity,
                metric     = metric_name,
                value      = metric_value,
                threshold  = threshold_value,
                account_id = aws_account_id,
            )
        except Exception as e:
            logger.warning(f"Alert publish failed: {e}")

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(
        f"Alert evaluation complete — "
        f"new: {new_alerts}, resolved: {resolved}, "
        f"already open: {already_open}"
    )