# app/ws/publisher.py
from __future__ import annotations
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)
_client = None


def get_redis():
    global _client
    if _client is None:
        try:
            import redis  # lazy import — avoids startup warning
            _client = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
            _client.ping()
            logger.info("Redis publisher connected")
        except Exception as e:
            logger.warning(f"Redis publisher unavailable: {e}")
            _client = None
    return _client


def publish(channel: str, data: dict):
    r = get_redis()
    if r is None:
        return
    try:
        r.publish(f"channel:{channel}", json.dumps(data))
    except Exception as e:
        logger.error(f"Redis publish error: {e}")
        global _client
        _client = None  # reset so next call retries


def publish_metric_update(account_id: int, service: str, cpu: float, memory: float):
    publish("overview", {
        "type": "metric_update",
        "account_id": account_id,
        "service": service,
        "cpu": round(cpu, 2),
        "memory": round(memory, 2),
    })


def publish_alert(alert_id: int, severity: str, metric: str,
                  value: float, threshold: float, account_id: int):
    publish("alerts", {
        "type": "new_alert",
        "alert_id": alert_id,
        "severity": severity,
        "metric": metric,
        "value": round(value, 2),
        "threshold": round(threshold, 2),
        "account_id": account_id,
    })