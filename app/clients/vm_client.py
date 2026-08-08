# app/clients/vm_client.py
import os
import datetime
import logging
import requests

logger = logging.getLogger(__name__)

VM_URL = os.environ.get("VM_URL", "http://localhost")


def vm_query_all(promql: str, dim_label: str) -> dict:
    """
    Instant query returning ALL matching series at once, keyed by the given
    dimension label. Used for list/snapshot views where we want e.g. every
    EC2 instance's current CPU in a single VM call instead of one call per
    instance (VM handles this natively — YACE already scrapes every
    resource into one metric name).
    Returns: {dimension_value: float_value}
    """
    out = {}
    try:
        r = requests.get(f"{VM_URL}/api/v1/query", params={"query": promql}, timeout=5)
        r.raise_for_status()
        for series in r.json().get("data", {}).get("result", []):
            label_val = series.get("metric", {}).get(dim_label)
            if label_val is not None:
                out[label_val] = float(series["value"][1])
    except Exception as e:
        logger.warning(f"VM query_all failed [{promql}]: {e}")
    return out


def vm_query(promql: str) -> float | None:
    """
    Instant query. Returns the single latest value for a PromQL expression,
    or None if no series matched.
    """
    try:
        r = requests.get(f"{VM_URL}/api/v1/query", params={"query": promql}, timeout=5)
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        if not result:
            return None
        return float(result[0]["value"][1])
    except Exception as e:
        logger.warning(f"VM query failed [{promql}]: {e}")
        return None


def vm_query_range(promql: str, start: int, end: int, step: str = "60s") -> list[dict]:
    """
    Range query. Returns [{"t": iso_timestamp, "v": value}, ...] sorted oldest->newest.
    Matches the shape collector_direct.py's series functions already return.
    """
    try:
        r = requests.get(f"{VM_URL}/api/v1/query_range", params={
            "query": promql, "start": start, "end": end, "step": step
        }, timeout=10)
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        if not result:
            return []
        points = result[0].get("values", [])
        return sorted(
            [
                {
                    "t": datetime.datetime.utcfromtimestamp(p[0]).isoformat(),
                    "v": round(float(p[1]), 2),
                }
                for p in points
            ],
            key=lambda x: x["t"],
        )
    except Exception as e:
        logger.warning(f"VM query_range failed [{promql}]: {e}")
        return []