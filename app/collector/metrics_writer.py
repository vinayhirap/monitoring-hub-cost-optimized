# app/collector/metrics_writer.py
"""
Writes metric datapoints to the partitioned metrics table.
Handles duplicate detection — skips if same resource+metric
was written within the last 55 seconds (avoids duplicate
datapoints from overlapping collection cycles).
"""
import logging
from datetime import datetime
from app.db import get_connection

logger = logging.getLogger(__name__)


def write_metric(resource_db_id: int, metric_name: str, metric_value: float):
    """
    Write a single metric datapoint.
    resource_db_id: resources.id (integer PK, not AWS resource string)
    metric_name:    lowercase metric name e.g. 'cpuutilization'
    metric_value:   float value
    """
    if resource_db_id is None or metric_value is None:
        return

    conn   = get_connection()
    cursor = conn.cursor()

    try:
        # Skip if we already wrote this metric in the last 55 seconds
        # (prevents duplicate datapoints from fast collection cycles)
        cursor.execute("""
            SELECT id FROM metrics
            WHERE resource_id       = %s
              AND metric_name       = %s
              AND metric_timestamp  >= DATE_SUB(NOW(), INTERVAL 55 SECOND)
            LIMIT 1
        """, (resource_db_id, metric_name))

        if cursor.fetchone():
            return  # Already written recently

        cursor.execute("""
            INSERT INTO metrics
                (resource_id, metric_name, metric_value, metric_timestamp)
            VALUES (%s, %s, %s, %s)
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
    Write multiple metric datapoints in a single transaction.
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
            INSERT IGNORE INTO metrics
                (resource_id, metric_name, metric_value, metric_timestamp)
            VALUES (%s, %s, %s, %s)
        """, [
            (r_id, name, round(float(val), 6), now)
            for r_id, name, val in datapoints
            if r_id is not None and val is not None
        ])
        conn.commit()
        logger.debug(f"Batch wrote {cursor.rowcount} metrics")

    except Exception as e:
        logger.error(f"metrics_writer batch error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()