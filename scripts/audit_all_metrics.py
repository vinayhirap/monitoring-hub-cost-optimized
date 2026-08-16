#!/usr/bin/env python3
"""
audit_all_metrics.py

Full audit of every row in metric_catalog against three layers of truth:

  1. DB wiring     - is it enabled in account_metric_selections for this account?
  2. Config wiring - does the freshly-generated YACE config for its tier actually
                      include it? (calls the app's own /yace-config endpoint live,
                      so this reflects current DB state - NOT necessarily what's
                      physically deployed on the server right now)
  3. Live data     - does VictoriaMetrics actually have a matching series, and how
                      fresh is the latest sample?

This gives you the "if a resource of this type existed, would it show up" answer
(layers 1+2) separately from "is it showing data right now" (layer 3) - so an
EBS-volume-count-zero or Lambda-function-count-zero account doesn't get flagged
as broken, it gets flagged as "wired correctly, nothing to scrape yet."

IMPORTANT CAVEAT printed at the end: layer 2 reflects what the DB would generate
right now, not necessarily what's physically sitting in /etc/yace/config-*.yml on
the server. Only config-critical.yml is confirmed redeployed as of this session
(the EBS fix). If a metric shows "wired: yes" but "live: no" and it's in the
standard or trend tier, that tier's config file may simply need deploying.

Usage:
    python audit_all_metrics.py [account_id] [vm_base_url]

    account_id defaults to 5 (AuroGov Mumbai)
    vm_base_url defaults to http://13.127.154.112
"""
import sys
import re
import time
import requests
import yaml
from dotenv import load_dotenv
load_dotenv()
from app.db import get_connection

APP_BASE = "http://127.0.0.1:8000"
TIER_BY_INTERVAL = {60: "critical", 300: "standard", 900: "trend"}
STAT_SUFFIXES = ["average", "sum", "maximum", "minimum", "samplecount",
                 "p50", "p90", "p95", "p99", "describe"]


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def strip_stat_suffix(vm_name: str) -> str:
    """vm_name like aws_ebs_volume_read_ops_average -> ebs_volume_read_ops"""
    n = vm_name
    if n.startswith("aws_"):
        n = n[4:]
    for suf in STAT_SUFFIXES:
        if n.endswith("_" + suf):
            n = n[: -(len(suf) + 1)]
            break
    return n


def main():
    account_id = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    vm_base = sys.argv[2] if len(sys.argv) > 2 else "http://13.127.154.112"

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    print(f"=== Full metric_catalog listing ({'/'.join(['all namespaces'])}) ===\n")
    cur.execute("""
        SELECT id, namespace, service, metric_name, statistic, category,
               is_default, default_interval
        FROM metric_catalog
        ORDER BY namespace, metric_name
    """)
    catalog = cur.fetchall()
    print(f"Total rows in metric_catalog: {len(catalog)}")

    real_metrics = [r for r in catalog if r["metric_name"]]
    placeholder_rows = [r for r in catalog if not r["metric_name"]]
    print(f"Rows with a real metric_name: {len(real_metrics)}")
    print(f"Placeholder/directory rows (no metric_name yet, not discoverable target): "
          f"{len(placeholder_rows)}\n")

    cur.execute("""
        SELECT metric_id, enabled FROM account_metric_selections
        WHERE aws_account_id = %s
    """, (account_id,))
    selections = {r["metric_id"]: bool(r["enabled"]) for r in cur.fetchall()}
    cur.close(); conn.close()

    # ---- Layer 2: pull fresh generated config per tier, build (namespace, metric_name) set
    tier_metric_sets = {}
    for tier in ["critical", "standard", "trend"]:
        try:
            resp = requests.get(
                f"{APP_BASE}/api/account-metrics/{account_id}/yace-config",
                params={"tier": tier, "download": "false"},
                timeout=15,
            )
            if resp.status_code != 200:
                tier_metric_sets[tier] = set()
                continue
            cfg = yaml.safe_load(resp.text)
            s = set()
            for job in cfg.get("discovery", {}).get("jobs", []):
                ns = job.get("type")
                for m in job.get("metrics", []):
                    s.add((ns, m.get("name")))
            tier_metric_sets[tier] = s
        except Exception as e:
            print(f"WARNING: failed to fetch tier={tier} config: {e}")
            tier_metric_sets[tier] = set()

    # ---- Layer 3: pull live VM series names, build normalized lookup
    print(f"Fetching live series list from {vm_base} ...")
    lv_resp = requests.get(f"{vm_base}/api/v1/label/__name__/values", timeout=15)
    lv_resp.raise_for_status()
    vm_names = lv_resp.json().get("data", [])
    vm_norm_map = {}  # normalized -> list of actual vm metric names
    for name in vm_names:
        if not name.startswith("aws_"):
            continue
        stripped = strip_stat_suffix(name)
        vm_norm_map.setdefault(normalize(stripped), []).append(name)

    print(f"Live 'aws_*' series names on VM: {sum(1 for n in vm_names if n.startswith('aws_'))}\n")

    # ---- Build rows
    print(f"{'ns':<26}{'metric':<28}{'tier':<10}{'enabled':<9}{'wired':<7}{'live':<6}"
          f"{'series':<8}{'latency_s':<10}latest")
    print("-" * 130)

    rows_out = []
    now = time.time()

    for r in real_metrics:
        ns, mname, mid = r["namespace"], r["metric_name"], r["id"]
        interval = r["default_interval"] or 300
        tier = TIER_BY_INTERVAL.get(interval, "standard")
        enabled = selections.get(mid, False)
        wired = (ns, mname) in tier_metric_sets.get(tier, set())

        prefix = ns.split("/", 1)[1] if "/" in ns else ns
        target_norm = normalize(prefix + mname)
        matches = vm_norm_map.get(target_norm, [])

        live = False
        series_count = 0
        latency_s = None
        latest_val = None

        if matches:
            # query the first match as instant query for freshness/value
            try:
                q_resp = requests.get(
                    f"{vm_base}/api/v1/query",
                    params={"query": matches[0]},
                    timeout=15,
                )
                q_resp.raise_for_status()
                result = q_resp.json().get("data", {}).get("result", [])
                series_count = len(result)
                if result:
                    live = True
                    ts_vals = [(float(res["value"][0]), res["value"][1]) for res in result]
                    latest_ts, latest_val = max(ts_vals, key=lambda x: x[0])
                    latency_s = round(now - latest_ts, 1)
            except Exception:
                pass

        rows_out.append({
            "namespace": ns, "metric": mname, "tier": tier, "enabled": enabled,
            "wired": wired, "live": live, "series": series_count,
            "latency_s": latency_s, "latest": latest_val,
        })

        print(f"{ns:<26}{mname:<28}{tier:<10}{str(enabled):<9}{str(wired):<7}"
              f"{str(live):<6}{series_count:<8}{str(latency_s):<10}{latest_val}")

    # ---- Summary
    enabled_rows = [r for r in rows_out if r["enabled"]]
    wired_not_live = [r for r in rows_out if r["enabled"] and r["wired"] and not r["live"]]
    enabled_not_wired = [r for r in rows_out if r["enabled"] and not r["wired"]]
    wired_no_enable = [r for r in rows_out if r["wired"] and not r["enabled"]]

    print("\n=== SUMMARY ===")
    print(f"Total real metrics in catalog: {len(rows_out)}")
    print(f"Enabled for account {account_id}: {len(enabled_rows)}")
    print(f"Enabled + correctly wired into their tier's generated config: "
          f"{sum(1 for r in enabled_rows if r['wired'])}")
    print(f"Enabled + wired + live data on VM right now: "
          f"{sum(1 for r in enabled_rows if r['wired'] and r['live'])}")

    if enabled_not_wired:
        print(f"\nANOMALY - enabled but NOT appearing in its tier's generated config "
              f"({len(enabled_not_wired)}) - this should not happen, investigate:")
        for r in enabled_not_wired:
            print(f"  {r['namespace']} / {r['metric']} (tier={r['tier']})")

    if wired_not_live:
        print(f"\nWired correctly but no live data right now ({len(wired_not_live)}):")
        print("  For each: either (a) no resource of that type currently exists in the "
              "account, which is fine, or (b) that tier's config file on the server "
              "hasn't been redeployed with current selections yet.")
        by_tier = {}
        for r in wired_not_live:
            by_tier.setdefault(r["tier"], []).append(f"{r['namespace']}/{r['metric']}")
        for tier, items in by_tier.items():
            print(f"  [{tier}] ({len(items)}): {', '.join(items)}")

    print("\nCAVEAT: 'wired' reflects what the DB would generate right NOW via the API, "
          "not necessarily what's physically deployed in /etc/yace/config-<tier>.yml on "
          "the server. Only config-critical.yml is confirmed redeployed this session. "
          "If a 'standard' or 'trend' tier metric shows wired=True but live=False, and "
          "you know the resource exists, check whether that tier's config file has ever "
          "been deployed at all.")


if __name__ == "__main__":
    main()
