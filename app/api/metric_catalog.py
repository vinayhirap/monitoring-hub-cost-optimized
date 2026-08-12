# app/api/metric_catalog.py
"""
CloudWatch metric catalog + per-account metric selection.

  GET  /api/metric-catalog                  full catalog, filterable/searchable
  GET  /api/metric-catalog/services          distinct services for filter chips
  GET  /api/metric-catalog/default-template  recommended metric ids (onboarding default)
  GET  /api/account-metrics/{account_id}     catalog merged with this account's enabled flags
  PUT  /api/account-metrics/{account_id}     replace this account's full selection
  POST /api/account-metrics/{account_id}/apply-default   reset to recommended template
  POST /api/account-metrics/{account_id}/discover        live ListMetrics for a directory namespace
  GET  /api/account-metrics/{account_id}/yace-config      generate a YACE discovery config.yml for this account's selection
"""
from fastapi import APIRouter, HTTPException, Body, Query, Response
from app.db import get_connection
import datetime
import json
import logging
import yaml

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Metric Catalog"])


def _ser(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ser(i) for i in obj]
    return obj


def _write_audit(actor, action, detail):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_logs (actor, action, payload) VALUES (%s,%s,%s)",
            (actor, action, json.dumps({"detail": detail}))
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        logger.warning(f"Audit: {e}")


# ── Catalog browsing ─────────────────────────────────────────────

@router.get("/api/metric-catalog")
def get_catalog(
    category: str = Query(None, description="core | extended | directory"),
    service:  str = Query(None, description="service key, e.g. ec2"),
    search:   str = Query(None, description="matches metric name, service, or description"),
):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    clauses, params = [], []
    if category:
        clauses.append("category = %s"); params.append(category)
    if service:
        clauses.append("service = %s"); params.append(service)
    if search:
        clauses.append("(metric_name LIKE %s OR display_service LIKE %s OR description LIKE %s)")
        like = f"%{search}%"
        params += [like, like, like]
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur.execute(f"""
        SELECT id, service, namespace, display_service, metric_name,
               statistic, unit, category, description, is_default, enabled
        FROM metric_catalog
        {where}
        ORDER BY category = 'core' DESC, category = 'extended' DESC,
                 display_service, metric_name
    """, params)
    rows = cur.fetchall(); cur.close(); conn.close()

    # Group by service for the frontend accordion
    grouped = {}
    for r in rows:
        key = r["service"]
        if key not in grouped:
            grouped[key] = {
                "service":         key,
                "display_service": r["display_service"],
                "namespace":       r["namespace"],
                "category":        r["category"],
                "metrics":         [],
            }
        if r["metric_name"]:  # skip the '' directory placeholder row itself
            grouped[key]["metrics"].append(_ser({
                "id": r["id"], "metric_name": r["metric_name"],
                "statistic": r["statistic"], "unit": r["unit"],
                "description": r["description"], "is_default": bool(r["is_default"]),
            }))
        else:
            grouped[key]["directory_id"] = r["id"]

    return sorted(grouped.values(), key=lambda g: (g["category"] != "core", g["category"] != "extended", g["display_service"] or ""))


@router.get("/api/metric-catalog/services")
def get_services():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT service, display_service, namespace, category, COUNT(*) AS metric_count
        FROM metric_catalog
        WHERE metric_name != '' OR metric_name IS NULL
        GROUP BY service, display_service, namespace, category
        ORDER BY category = 'core' DESC, category = 'extended' DESC, display_service
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [_ser(r) for r in rows]


@router.get("/api/metric-catalog/default-template")
def get_default_template():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, service, display_service, metric_name
        FROM metric_catalog
        WHERE is_default = 1
        ORDER BY display_service, metric_name
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [_ser(r) for r in rows]


# ── Per-account selection ────────────────────────────────────────

def _default_metric_ids(cur) -> list:
    cur.execute("SELECT id FROM metric_catalog WHERE is_default = 1")
    return [r[0] for r in cur.fetchall()]


def seed_account_defaults(account_id: int):
    """Called by admin/accounts.py right after a new account is onboarded."""
    conn = get_connection(); cur = conn.cursor()
    ids = _default_metric_ids(cur)
    for mid in ids:
        cur.execute("""
            INSERT IGNORE INTO account_metric_selections
                (aws_account_id, metric_id, enabled, source)
            VALUES (%s, %s, 1, 'template')
        """, (account_id, mid))
    conn.commit(); cur.close(); conn.close()
    return len(ids)


@router.get("/api/account-metrics/{account_id}")
def get_account_metrics(account_id: int):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM aws_accounts WHERE id = %s", (account_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    cur.execute("""
        SELECT mc.id, mc.service, mc.namespace, mc.display_service, mc.metric_name,
               mc.statistic, mc.unit, mc.category, mc.description, mc.is_default,
               COALESCE(ams.enabled, 0) AS enabled,
               ams.source
        FROM metric_catalog mc
        LEFT JOIN account_metric_selections ams
               ON ams.metric_id = mc.id AND ams.aws_account_id = %s
        WHERE mc.metric_name != '' OR mc.metric_name IS NULL
        ORDER BY mc.category = 'core' DESC, mc.category = 'extended' DESC,
                 mc.display_service, mc.metric_name
    """, (account_id,))
    rows = cur.fetchall(); cur.close(); conn.close()

    grouped = {}
    for r in rows:
        key = r["service"]
        if key not in grouped:
            grouped[key] = {
                "service": key, "display_service": r["display_service"],
                "namespace": r["namespace"], "category": r["category"],
                "metrics": [],
            }
        if r["metric_name"]:
            grouped[key]["metrics"].append(_ser({
                "id": r["id"], "metric_name": r["metric_name"],
                "statistic": r["statistic"], "unit": r["unit"],
                "description": r["description"], "is_default": bool(r["is_default"]),
                "enabled": bool(r["enabled"]),
            }))
        else:
            grouped[key]["directory_id"] = r["id"]

    return sorted(grouped.values(), key=lambda g: (g["category"] != "core", g["category"] != "extended", g["display_service"] or ""))


@router.put("/api/account-metrics/{account_id}")
def set_account_metrics(account_id: int, payload: dict = Body(...)):
    """
    Full-replace selection for this account.
    Body: { "enabled_metric_ids": [1, 2, 3, ...] }
    """
    enabled_ids = set(int(i) for i in payload.get("enabled_metric_ids", []))

    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM aws_accounts WHERE id = %s", (account_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    cur.execute("SELECT metric_id FROM account_metric_selections WHERE aws_account_id = %s", (account_id,))
    existing_ids = {r["metric_id"] for r in cur.fetchall()}
    cur.close()

    cur = conn.cursor()
    to_add    = enabled_ids - existing_ids
    to_enable = enabled_ids & existing_ids
    to_remove = existing_ids - enabled_ids

    for mid in to_add:
        cur.execute("""
            INSERT INTO account_metric_selections (aws_account_id, metric_id, enabled, source)
            VALUES (%s, %s, 1, 'manual')
        """, (account_id, mid))
    if to_enable:
        cur.execute(f"""
            UPDATE account_metric_selections SET enabled = 1
            WHERE aws_account_id = %s AND metric_id IN ({','.join(['%s']*len(to_enable))})
        """, (account_id, *to_enable))
    if to_remove:
        cur.execute(f"""
            UPDATE account_metric_selections SET enabled = 0
            WHERE aws_account_id = %s AND metric_id IN ({','.join(['%s']*len(to_remove))})
        """, (account_id, *to_remove))

    conn.commit(); cur.close(); conn.close()

    _write_audit("admin", "Account metric selection updated",
                 f"account={account_id} enabled={len(enabled_ids)} added={len(to_add)} removed={len(to_remove)}")
    return {"status": "saved", "enabled_count": len(enabled_ids)}


@router.post("/api/account-metrics/{account_id}/apply-default")
def apply_default_template(account_id: int):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM aws_accounts WHERE id = %s", (account_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    cur.close(); conn.close()

    count = seed_account_defaults(account_id)

    # Disable anything currently enabled that isn't part of the default set
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        UPDATE account_metric_selections ams
        JOIN metric_catalog mc ON mc.id = ams.metric_id
        SET ams.enabled = (mc.is_default = 1)
        WHERE ams.aws_account_id = %s
    """, (account_id,))
    conn.commit(); cur.close(); conn.close()

    _write_audit("admin", "Applied default metric template", f"account={account_id}")
    return {"status": "applied", "default_metric_count": count}


@router.post("/api/account-metrics/{account_id}/discover")
def discover_namespace_metrics(account_id: int, namespace: str = Query(...), region: str = Query(None)):
    """
    Live CloudWatch ListMetrics call for a 'directory' namespace — used when
    a user expands a service that doesn't have a hand-curated metric list.
    Discovered metric names are cached into metric_catalog as category
    'directory' rows (still metric_name-populated) so future loads are instant.
    """
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT default_region, role_arn, external_id FROM aws_accounts WHERE id = %s", (account_id,))
    acc = cur.fetchone(); cur.close(); conn.close()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    resolved_region = region or acc.get("default_region")

    try:
        import boto3
        if acc.get("role_arn"):
            from app.aws.sts import assume_role
            session = assume_role(acc["role_arn"], acc.get("external_id"))
            cw = session.client("cloudwatch", region_name=resolved_region)
        else:
            cw = boto3.client("cloudwatch", region_name=resolved_region)

        seen = {}
        paginator = cw.get_paginator("list_metrics")
        for page in paginator.paginate(Namespace=namespace):
            for m in page.get("Metrics", []):
                seen[m["MetricName"]] = True
                if len(seen) >= 200:  # sane cap per discovery call
                    break
            if len(seen) >= 200:
                break
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Discovery failed: {str(e)}")

    if not seen:
        return {"namespace": namespace, "discovered": 0, "metrics": []}

    conn = get_connection(); cur = conn.cursor()
    display_service = None
    cur.execute("SELECT display_service, service FROM metric_catalog WHERE namespace = %s LIMIT 1", (namespace,))
    row = cur.fetchone()
    display_service, service_key = (row if row else (namespace, namespace.split("/")[-1].lower()))

    for metric_name in seen:
        cur.execute("""
            INSERT INTO metric_catalog
                (service, namespace, display_service, metric_name,
                 statistic, unit, default_interval, category, description, is_default, enabled)
            VALUES (%s,%s,%s,%s,'Average',NULL,300,'directory','Discovered via ListMetrics',0,1)
            ON DUPLICATE KEY UPDATE metric_name = VALUES(metric_name)
        """, (service_key, namespace, display_service, metric_name))
    conn.commit(); cur.close(); conn.close()

    _write_audit("admin", "Discovered namespace metrics", f"account={account_id} namespace={namespace} count={len(seen)}")
    return {"namespace": namespace, "discovered": len(seen), "metrics": sorted(seen.keys())}


# ── YACE config generation ───────────────────────────────────────

@router.get("/api/account-metrics/{account_id}/yace-config")
def generate_yace_config(account_id: int, download: bool = Query(True)):
    """
    Builds a ready-to-use YACE (yet-another-cloudwatch-exporter) discovery
    config.yml from this account's enabled metric selection, one job per
    AWS namespace. Deploy the output to that account/region's regional
    monitoring server (per the distributed collection architecture —
    CloudWatch → YACE → VictoriaMetrics, local to each account/region) and
    reload/restart YACE there. This app does not remotely push config to
    regional servers; it only generates it.
    """
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT account_name, account_id, role_arn, external_id, default_region
        FROM aws_accounts WHERE id = %s
    """, (account_id,))
    account = cur.fetchone()
    if not account:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    cur.execute("""
        SELECT mc.namespace, mc.service, mc.metric_name, mc.statistic, mc.default_interval
        FROM metric_catalog mc
        JOIN account_metric_selections ams ON ams.metric_id = mc.id
        WHERE ams.aws_account_id = %s AND ams.enabled = 1 AND mc.metric_name != ''
        ORDER BY mc.namespace, mc.metric_name
    """, (account_id,))
    rows = cur.fetchall(); cur.close(); conn.close()

    if not rows:
        raise HTTPException(status_code=400, detail="No metrics enabled for this account — nothing to generate.")

    # Group into one discovery job per namespace
    jobs_by_ns = {}
    for r in rows:
        ns = r["namespace"]
        job = jobs_by_ns.setdefault(ns, {
            "type": ns,
            "regions": [account["default_region"] or "us-east-1"],
            "period": r["default_interval"] or 300,
            "length": r["default_interval"] or 300,
            "metrics": [],
        })
        job["period"] = min(job["period"], r["default_interval"] or 300)
        job["length"] = job["period"]
        job["metrics"].append({
            "name": r["metric_name"],
            "statistics": [r["statistic"] or "Average"],
        })

    if account["role_arn"]:
        role_entry = {"roleArn": account["role_arn"]}
        if account["external_id"]:
            role_entry["externalId"] = account["external_id"]
        for job in jobs_by_ns.values():
            job["roles"] = [dict(role_entry)]  # copy per job — avoids YAML anchor/alias reuse

    config = {
        "apiVersion": "v1alpha1",
        "discovery": {"jobs": list(jobs_by_ns.values())},
    }

    header = (
        f"# YACE discovery config — generated for account "
        f"'{account['account_name']}' ({account['account_id']}), region {account['default_region']}\n"
        f"# Deploy this to the regional monitoring server for that account/region\n"
        f"# (CloudWatch -> YACE -> local VictoriaMetrics) and reload YACE.\n"
        f"# Regenerate any time the metric selection changes in Settings -> Metrics.\n\n"
    )
    yaml_text = header + yaml.dump(config, sort_keys=False, default_flow_style=False)

    headers = {}
    if download:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in account["account_name"])
        headers["Content-Disposition"] = f'attachment; filename="yace-config-{safe_name}.yml"'

    return Response(content=yaml_text, media_type="text/yaml", headers=headers)
