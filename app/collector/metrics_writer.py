# app/collector/metrics_writer.py
"""
Maintains the `metrics` table as a single-row-per-(resource, metric)
LAST-VALUE CACHE for alert_evaluator.py's threshold joins.

All historical/time-series data lives in VictoriaMetrics — that's the
system of record and the only place range queries or graphs should read
from (see app/clients/vm_client.py). This table never stores history;
every write is an upsert that overwrites the previous value in place, so
its row count stays equal to the number of distinct (resource, metric)
pairs being alerted on, not the number of datapoints collected over time.

Requires a UNIQUE KEY on (resource_id, metric_name) — see
db/migrations for the migration that adds it and collapses any old
history rows down to one per pair.
"""
import logging
from datetime import datetime
from app.db import get_connection

logger = logging.getLogger(__name__)


def write_metric(resource_db_id: int, metric_name: str, metric_value: float):
    """
    Upsert a single metric's latest value.
    resource_db_id: resources.id (integer PK, not AWS resource string)
    metric_name:    lowercase metric name e.g. 'cpuutilization'
    metric_value:   float value
    """
    if resource_db_id is None or metric_value is None:
        return

    conn   = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO metrics
                (resource_id, metric_name, metric_value, metric_timestamp)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                metric_value     = VALUES(metric_value),
                metric_timestamp = VALUES(metric_timestamp)
        """, (
            resource_db_id,
            metric_name,
            round(float(metric_value), 6),
            datetime.utcnow(),
        ))
        conn.commit()

    except Exception as e:
        logger.error(f"metrics_writer error [{resource_db_id}/{metric_name}]: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def write_metrics_batch(datapoints: list):
    """
    Upsert multiple metrics' latest values in a single transaction.
    datapoints: list of (resource_db_id, metric_name, metric_value) tuples
    More efficient than calling write_metric() in a loop.
    """
    if not datapoints:
        return

    conn   = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.utcnow()
        cursor.executemany("""
            INSERT INTO metrics
                (resource_id, metric_name, metric_value, metric_timestamp)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                metric_value     = VALUES(metric_value),
                metric_timestamp = VALUES(metric_timestamp)
        """, [
            (r_id, name, round(float(val), 6), now)
            for r_id, name, val in datapoints
            if r_id is not None and val is not None
        ])
        conn.commit()
        logger.debug(f"Batch upserted {cursor.rowcount} metrics")

    except Exception as e:
        logger.error(f"metrics_writer batch error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()