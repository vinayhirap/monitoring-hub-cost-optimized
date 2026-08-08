# app/aws/collector_direct.py
"""
Live data collector for frontend detail pages.

MIGRATION NOTE: EC2 / EBS / RDS metrics, and the subset of ALB metrics that
YACE scrapes (RequestCount, TargetResponseTime, HealthyHostCount,
UnHealthyHostCount, HTTPCode_Target_2XX/4XX/5XX_Count, ActiveConnectionCount)
now come from VictoriaMetrics (fed by YACE) instead of direct CloudWatch
GetMetricData calls. ECS, Lambda, S3, and the two ALB metrics YACE does NOT
scrape (HTTPCode_ELB_5XX_Count, NewConnectionCount) remain on boto3/GMD since
there is no YACE job for them.

Two GMD helpers (unchanged, still used for the boto3 fallback paths):
  _gmd_snapshot(cw, queries)  — latest single value per metric (for list views)
  _gmd_series(cw, queries)    — time-series arrays (for chart/detail views)
"""
import boto3, logging, time, math
from datetime import datetime, timedelta, timezone
from app.clients.vm_client import vm_query, vm_query_all, vm_query_range

logger = logging.getLogger(__name__)

_cache: dict = {}
_CACHE_TTL   = 60


def _cached(key: str, fn):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < _CACHE_TTL:
        return _cache[key]["data"]
    result = fn()
    _cache[key] = {"data": result, "ts": now}
    return result


def get_session(region=None):
    return boto3.Session(region_name=region)


def _smart_period(hours: int) -> int:
    """CloudWatch max 1440 datapoints/request. Period must be multiple of 60."""
    period = math.ceil(hours * 3600 / 1440)
    period = max(60, period)
    return math.ceil(period / 60) * 60


# ── GMD core helpers (still used for ECS / Lambda / uncovered-ALB) ──────

def _make_query(qid, namespace, metric_name, dimensions, stat, period=60):
    return {
        "Id": qid,
        "MetricStat": {
            "Metric": {
                "Namespace":  namespace,
                "MetricName": metric_name,
                "Dimensions": dimensions,
            },
            "Period": period,
            "Stat":   stat,
        },
        "ReturnData": True,
    }


def _safe_qid(s: str) -> str:
    """
    AWS GetMetricData query IDs must match ^[a-z][a-zA-Z0-9_]*$ — no hyphens,
    no dots, must start with a lowercase letter. Resource IDs (i-xxxx,
    vol-xxxx, cluster/service names) commonly contain hyphens, so any qid
    built from a raw resource_id needs to go through this first.
    """
    import re
    s = re.sub(r'[^a-zA-Z0-9_]', '_', s)
    if not s or not s[0].islower():
        s = 'q' + s
    return s


def _gmd_snapshot(cw, queries, minutes=3):
    """Fetch latest single value for each query. Returns {query_id: float}."""
    if not queries:
        return {}
    end   = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    out   = {}
    try:
        for i in range(0, len(queries), 500):
            chunk = queries[i:i + 500]
            resp  = cw.get_metric_data(
                MetricDataQueries=chunk,
                StartTime=start,
                EndTime=end,
                ScanBy="TimestampDescending",
            )
            for r in resp.get("MetricDataResults", []):
                vals = r.get("Values", [])
                out[r["Id"]] = vals[0] if vals else 0.0
    except Exception as e:
        logger.error(f"GMD snapshot failed: {e}")
    return out


def _gmd_series(cw, queries, hours=6):
    """Fetch time-series arrays for each query. Returns {query_id: [{t,v},...]}."""
    if not queries:
        return {}
    end    = datetime.now(timezone.utc)
    start  = end - timedelta(hours=hours)
    period = _smart_period(hours)
    out    = {}

    adjusted = []
    for q in queries:
        q2 = dict(q)
        q2["MetricStat"] = dict(q["MetricStat"])
        q2["MetricStat"]["Period"] = period
        adjusted.append(q2)

    try:
        for i in range(0, len(adjusted), 500):
            chunk = adjusted[i:i + 500]
            resp  = cw.get_metric_data(
                MetricDataQueries=chunk,
                StartTime=start,
                EndTime=end,
                ScanBy="TimestampAscending",
            )
            for r in resp.get("MetricDataResults", []):
                timestamps = r.get("Timestamps", [])
                values     = r.get("Values", [])
                out[r["Id"]] = [
                    {"t": t.isoformat(), "v": round(v, 4)}
                    for t, v in zip(timestamps, values)
                ]
    except Exception as e:
        logger.error(f"GMD series failed: {e}")
    return out


# ── EC2 ───────────────────────────────────────────────────────────────

def collect_ec2_instances(region=None) -> list:
    return _cached(f"ec2_{region}", lambda: _ec2_raw(region))

def _ec2_raw(region) -> list:
    try:
        ec2 = get_session(region).client("ec2")
        instances = []
        for r in ec2.describe_instances()["Reservations"]:
            for inst in r["Instances"]:
                instances.append(inst)

        # One VM call per metric gets EVERY instance's current value at once —
        # no need to loop per-instance like the old GMD approach.
        cpu_map    = vm_query_all("aws_ec2_cpuutilization_average", "dimension_InstanceId")
        netin_map  = vm_query_all("aws_ec2_network_in_average",      "dimension_InstanceId")
        netout_map = vm_query_all("aws_ec2_network_out_average",     "dimension_InstanceId")

        out = []
        for inst in instances:
            iid   = inst["InstanceId"]
            state = inst["State"]["Name"]
            tags  = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
            out.append({
                "instance_id":       iid,
                "name":              tags.get("Name", iid),
                "instance_type":     inst.get("InstanceType", ""),
                "state":             state,
                "region":            region,
                "availability_zone": inst.get("Placement", {}).get("AvailabilityZone", ""),
                "private_ip":        inst.get("PrivateIpAddress", "—"),
                "launch_time":       inst["LaunchTime"].isoformat() if inst.get("LaunchTime") else "",
                "cpu_utilization":   round(cpu_map.get(iid, 0.0), 2),
                "network_in_kb":     round(netin_map.get(iid, 0.0) / 1024, 2),
                "network_out_kb":    round(netout_map.get(iid, 0.0) / 1024, 2),
                "uptime_days":       _calc_uptime(inst.get("LaunchTime")),
                "tags":              tags,
            })
        running = [i for i in instances if i["State"]["Name"] == "running"]
        logger.info(f"EC2: {len(out)} in {region} ({len(running)} running, via VM)")
        return out
    except Exception as e:
        logger.error(f"EC2 [{region}]: {e}"); return []


# ── EBS ───────────────────────────────────────────────────────────────

def collect_ebs_volumes(region=None) -> list:
    return _cached(f"ebs_{region}", lambda: _ebs_raw(region))

def _ebs_raw(region) -> list:
    try:
        ec2  = get_session(region).client("ec2")
        vols = ec2.describe_volumes().get("Volumes", [])

        read_ops_map  = vm_query_all("aws_ebs_volume_read_ops_sum",     "dimension_VolumeId")
        write_ops_map = vm_query_all("aws_ebs_volume_write_ops_sum",    "dimension_VolumeId")
        read_b_map    = vm_query_all("aws_ebs_volume_read_bytes_sum",   "dimension_VolumeId")
        write_b_map   = vm_query_all("aws_ebs_volume_write_bytes_sum",  "dimension_VolumeId")
        queue_map     = vm_query_all("aws_ebs_volume_queue_length_average", "dimension_VolumeId")

        out = []
        for v in vols:
            vid         = v["VolumeId"]
            tags        = {t["Key"]: t["Value"] for t in v.get("Tags", [])}
            attachments = v.get("Attachments", [])
            attached_to = attachments[0].get("InstanceId", "") if attachments else ""
            out.append({
                "volume_id":         vid,
                "name":              tags.get("Name", vid),
                "state":             v.get("State", ""),
                "size_gb":           v.get("Size", 0),
                "volume_type":       v.get("VolumeType", ""),
                "iops":              v.get("Iops"),
                "throughput":        v.get("Throughput"),
                "encrypted":         v.get("Encrypted", False),
                "availability_zone": v.get("AvailabilityZone", ""),
                "attached_to":       attached_to,
                "create_time":       v["CreateTime"].isoformat() if v.get("CreateTime") else "",
                "region":            region,
                "tags":              tags,
                "read_ops":          round(read_ops_map.get(vid,  0.0), 2),
                "write_ops":         round(write_ops_map.get(vid, 0.0), 2),
                "read_bytes_kb":     round(read_b_map.get(vid,    0.0) / 1024, 2),
                "write_bytes_kb":    round(write_b_map.get(vid,   0.0) / 1024, 2),
                "queue_length":      round(queue_map.get(vid,     0.0), 4),
            })
        return out
    except Exception as e:
        logger.error(f"EBS [{region}]: {e}"); return []


# ── RDS (discovery only — no CW metrics fetched here) ───────────────────

def collect_rds_instances(region=None) -> list:
    return _cached(f"rds_{region}", lambda: _rds_raw(region))

def _rds_raw(region) -> list:
    try:
        rds = get_session(region).client("rds")
        out = []
        for db in rds.describe_db_instances()["DBInstances"]:
            out.append({
                "db_instance_id":    db["DBInstanceIdentifier"],
                "identifier":        db["DBInstanceIdentifier"],
                "engine":            db.get("Engine", ""),
                "engine_version":    db.get("EngineVersion", ""),
                "instance_class":    db.get("DBInstanceClass", ""),
                "status":            db.get("DBInstanceStatus", ""),
                "region":            region,
                "multi_az":          db.get("MultiAZ", False),
                "allocated_storage": db.get("AllocatedStorage"),
                "endpoint":          db.get("Endpoint", {}).get("Address", ""),
            })
        return out
    except Exception as e:
        logger.error(f"RDS [{region}]: {e}"); return []


# ── S3 (unchanged — not in YACE config) ─────────────────────────────────

def collect_s3_buckets(region=None) -> list:
    return _cached("s3_global", lambda: _s3_raw())

def _s3_raw() -> list:
    try:
        s3  = boto3.client("s3")
        out = []
        for b in s3.list_buckets().get("Buckets", []):
            name          = b["Name"]
            bucket_region = "us-east-1"
            versioning    = "Disabled"
            public_access = False
            try:
                loc = s3.get_bucket_location(Bucket=name)
                bucket_region = loc.get("LocationConstraint") or "us-east-1"
            except Exception: pass
            try:
                v = s3.get_bucket_versioning(Bucket=name)
                versioning = v.get("Status", "Disabled") or "Disabled"
            except Exception: pass
            try:
                cfg = s3.get_public_access_block(Bucket=name).get("PublicAccessBlockConfiguration", {})
                public_access = not all([
                    cfg.get("BlockPublicAcls",      True),
                    cfg.get("BlockPublicPolicy",     True),
                    cfg.get("RestrictPublicBuckets", True),
                ])
            except Exception: pass
            cd = b.get("CreationDate", "")
            out.append({
                "bucket_name":   name,
                "name":          name,
                "region":        bucket_region,
                "creation_date": cd.isoformat() if hasattr(cd, "isoformat") else str(cd),
                "versioning":    versioning,
                "public_access": public_access,
                "object_count":  None,
                "size_bytes":    None,
            })
        logger.info(f"S3: {len(out)} buckets")
        return out
    except Exception as e:
        logger.error(f"S3: {e}"); return []


# ── S3 metric series (unchanged — not in YACE config) ────────────────────

def get_s3_metric_series(bucket_name: str, hours: int = 24) -> dict:
    try:
        cw            = boto3.client("cloudwatch", region_name="us-east-1")
        end           = datetime.now(timezone.utc)
        effective_hrs = max(hours, 24 * 14)
        start         = end - timedelta(hours=effective_hrs)
        period        = max(_smart_period(effective_hrs), 86400)

        def storage_series(metric, storage_type="StandardStorage"):
            dims = [
                {"Name": "BucketName",  "Value": bucket_name},
                {"Name": "StorageType", "Value": storage_type},
            ]
            from botocore.exceptions import ClientError
            try:
                r = cw.get_metric_statistics(
                    Namespace="AWS/S3", MetricName=metric, Dimensions=dims,
                    StartTime=start, EndTime=end, Period=period,
                    Statistics=["Average"],
                )
                return sorted(
                    [{"t": p["Timestamp"].isoformat(), "v": round(p["Average"], 2)} for p in r["Datapoints"]],
                    key=lambda x: x["t"]
                )
            except ClientError:
                return []

        def request_series(metric):
            dims = [
                {"Name": "BucketName", "Value": bucket_name},
                {"Name": "FilterId",   "Value": "EntireBucket"},
            ]
            try:
                r = cw.get_metric_statistics(
                    Namespace="AWS/S3", MetricName=metric, Dimensions=dims,
                    StartTime=end - timedelta(hours=min(hours, 168)),
                    EndTime=end, Period=max(_smart_period(hours), 300),
                    Statistics=["Sum"],
                )
                return sorted(
                    [{"t": p["Timestamp"].isoformat(), "v": round(p["Sum"], 2)} for p in r["Datapoints"]],
                    key=lambda x: x["t"]
                )
            except Exception:
                return []

        return {
            "bucket_name":    bucket_name,
            "bucket_size":    storage_series("BucketSizeBytes", "StandardStorage"),
            "object_count":   storage_series("NumberOfObjects", "AllStorageTypes"),
            "all_requests":   request_series("AllRequests"),
            "get_requests":   request_series("GetRequests"),
            "put_requests":   request_series("PutRequests"),
            "errors_4xx":     request_series("4xxErrors"),
            "errors_5xx":     request_series("5xxErrors"),
            "bytes_download": request_series("BytesDownloaded"),
            "bytes_upload":   request_series("BytesUploaded"),
            "period_hours":   hours,
            "note": "Storage metrics: daily. Request metrics require per-bucket CW config.",
        }
    except Exception as e:
        logger.error(f"S3 metrics [{bucket_name}]: {e}")
        return {"bucket_name": bucket_name, "bucket_size": [], "object_count": [],
                "all_requests": [], "get_requests": [], "put_requests": [],
                "errors_4xx": [], "errors_5xx": [], "bytes_download": [],
                "bytes_upload": [], "period_hours": hours, "note": str(e)}


# ── ELB (discovery only — no CW metrics fetched here) ────────────────────

def collect_elb(region=None) -> list:
    return _cached(f"elb_{region}", lambda: _elb_raw(region))

def _elb_raw(region) -> list:
    try:
        elb = get_session(region).client("elbv2")
        out = []
        for lb in elb.describe_load_balancers().get("LoadBalancers", []):
            ct = lb.get("CreatedTime", "")
            out.append({
                "name":               lb.get("LoadBalancerName", ""),
                "load_balancer_arn":  lb.get("LoadBalancerArn", ""),
                "dns_name":           lb.get("DNSName", ""),
                "type":               lb.get("Type", ""),
                "scheme":             lb.get("Scheme", ""),
                "state":              lb.get("State", {}).get("Code", ""),
                "region":             region,
                "availability_zones": [az["ZoneName"] for az in lb.get("AvailabilityZones", [])],
                "created_time":       ct.isoformat() if hasattr(ct, "isoformat") else str(ct),
            })
        logger.info(f"ELB: {len(out)} in {region}")
        return out
    except Exception as e:
        logger.error(f"ELB [{region}]: {e}"); return []


# ── ECS (unchanged — not in YACE config) ─────────────────────────────────

def collect_ecs_clusters(region=None) -> list:
    return _cached(f"ecs_{region}", lambda: _ecs_raw(region))

def _ecs_raw(region) -> list:
    try:
        ecs = get_session(region).client("ecs")
        cw  = get_session(region).client("cloudwatch")
        cluster_arns = ecs.list_clusters().get("clusterArns", [])
        if not cluster_arns:
            return []
        clusters = ecs.describe_clusters(clusters=cluster_arns, include=["STATISTICS"]).get("clusters", [])

        queries  = []
        qid_map  = {}
        svc_data = {}

        for c in clusters:
            cname    = c["clusterName"]
            svc_arns = ecs.list_services(cluster=cname).get("serviceArns", [])
            svcs     = []
            if svc_arns:
                svcs = ecs.describe_services(cluster=cname, services=svc_arns[:10]).get("services", [])
            svc_data[cname] = svcs

            for s in svcs:
                sname = s["serviceName"]
                dims  = [
                    {"Name": "ClusterName", "Value": cname},
                    {"Name": "ServiceName", "Value": sname},
                ]
                for metric, key in [("CPUUtilization", "cpu"), ("MemoryUtilization", "mem")]:
                    qid = _safe_qid(f"{cname}__{sname}__{key}")
                    queries.append(_make_query(qid, "AWS/ECS", metric, dims, "Average"))
                    qid_map[qid] = (cname, sname, key)

        snap = _gmd_snapshot(cw, queries, minutes=6)
        metrics = {}
        for qid, val in snap.items():
            cname, sname, key = qid_map[qid]
            metrics.setdefault((cname, sname), {})[key] = val

        out = []
        for c in clusters:
            cname    = c["clusterName"]
            services = []
            for s in svc_data.get(cname, []):
                sname = s["serviceName"]
                m     = metrics.get((cname, sname), {})
                services.append({
                    "service_name":    sname,
                    "service_arn":     s["serviceArn"],
                    "status":          s.get("status", ""),
                    "desired_count":   s.get("desiredCount", 0),
                    "running_count":   s.get("runningCount", 0),
                    "pending_count":   s.get("pendingCount", 0),
                    "task_definition": s.get("taskDefinition", "").split("/")[-1],
                    "launch_type":     s.get("launchType", "FARGATE"),
                    "cpu_utilization": round(m.get("cpu", 0.0), 2),
                    "mem_utilization": round(m.get("mem", 0.0), 2),
                })
            out.append({
                "cluster_name":         cname,
                "cluster_arn":          c["clusterArn"],
                "status":               c.get("status", ""),
                "registered_instances": c.get("registeredContainerInstancesCount", 0),
                "running_tasks":        c.get("runningTasksCount", 0),
                "pending_tasks":        c.get("pendingTasksCount", 0),
                "active_services":      c.get("activeServicesCount", 0),
                "region":               region,
                "services":             services,
            })
        logger.info(f"ECS: {len(out)} clusters in {region} (1 GMD call)")
        return out
    except Exception as e:
        logger.warning(f"ECS [{region}]: {e}"); return []


# ── Lambda (unchanged — not in YACE config) ──────────────────────────────

def collect_lambda_functions(region=None) -> list:
    return _cached(f"lambda_{region}", lambda: _lambda_raw(region))

def _lambda_raw(region) -> list:
    try:
        lmb = get_session(region).client("lambda")
        out = []
        for page in lmb.get_paginator("list_functions").paginate():
            for fn in page["Functions"]:
                out.append({
                    "function_name": fn["FunctionName"],
                    "function_arn":  fn.get("FunctionArn", ""),
                    "runtime":       fn.get("Runtime", ""),
                    "memory_size":   fn.get("MemorySize", 0),
                    "timeout":       fn.get("Timeout", 0),
                    "last_modified": fn.get("LastModified", ""),
                    "code_size":     fn.get("CodeSize"),
                    "region":        region,
                })
        return out
    except Exception as e:
        logger.warning(f"Lambda [{region}]: {e}"); return []


# ── Metric series — EC2 (now VM-backed) ──────────────────────────────────

def get_ec2_metric_series(instance_id, region=None, hours=6) -> dict:
    try:
        end    = datetime.now(timezone.utc)
        start  = end - timedelta(hours=hours)
        period = _smart_period(hours)
        dim    = f'dimension_InstanceId="{instance_id}"'

        def s(yace_metric):
            return vm_query_range(
                f'{yace_metric}{{{dim}}}',
                start=int(start.timestamp()), end=int(end.timestamp()),
                step=f"{period}s",
            )
        return {
            "instance_id":  instance_id,
            "cpu":          s("aws_ec2_cpuutilization_average"),
            "network_in":   s("aws_ec2_network_in_average"),
            "network_out":  s("aws_ec2_network_out_average"),
            "disk_read":    s("aws_ec2_disk_read_bytes_sum"),
            "disk_write":   s("aws_ec2_disk_write_bytes_sum"),
            "period_hours": hours,
            "period_secs":  period,
        }
    except Exception as e:
        logger.warning(f"EC2 series [{instance_id}]: {e}")
        return {"instance_id": instance_id, "cpu": [], "network_in": [],
                "network_out": [], "disk_read": [], "disk_write": []}


# ── Metric series — EBS (now VM-backed) ──────────────────────────────────

def _get_ebs_metric_series(volume_id, region=None, hours=6) -> dict:
    try:
        end    = datetime.now(timezone.utc)
        start  = end - timedelta(hours=hours)
        period = _smart_period(hours)
        dim    = f'dimension_VolumeId="{volume_id}"'

        def s(yace_metric):
            return vm_query_range(
                f'{yace_metric}{{{dim}}}',
                start=int(start.timestamp()), end=int(end.timestamp()),
                step=f"{period}s",
            )
        return {
            "volume_id":    volume_id,
            "read_ops":     s("aws_ebs_volume_read_ops_sum"),
            "write_ops":    s("aws_ebs_volume_write_ops_sum"),
            "read_bytes":   s("aws_ebs_volume_read_bytes_sum"),
            "write_bytes":  s("aws_ebs_volume_write_bytes_sum"),
            "queue_length": s("aws_ebs_volume_queue_length_average"),
            "period_hours": hours,
            "period_secs":  period,
        }
    except Exception as e:
        logger.warning(f"EBS series [{volume_id}]: {e}")
        return {"volume_id": volume_id, "read_ops": [], "write_ops": [],
                "read_bytes": [], "write_bytes": [], "queue_length": []}


# ── Metric series — Lambda (unchanged — not in YACE config) ─────────────

def _get_lambda_metric_series(function_name, region=None, hours=6) -> dict:
    try:
        cw   = boto3.client("cloudwatch", region_name=region)
        dims = [{"Name": "FunctionName", "Value": function_name}]
        queries = [
            _make_query("invocations", "AWS/Lambda", "Invocations", dims, "Sum"),
            _make_query("errors",      "AWS/Lambda", "Errors",      dims, "Sum"),
            _make_query("duration",    "AWS/Lambda", "Duration",    dims, "Average"),
            _make_query("throttles",   "AWS/Lambda", "Throttles",   dims, "Sum"),
            _make_query("concurrent",  "AWS/Lambda", "ConcurrentExecutions", dims, "Average"),
        ]
        s = _gmd_series(cw, queries, hours)
        return {
            "function_name": function_name,
            "invocations":   s.get("invocations", []),
            "errors":        s.get("errors", []),
            "duration":      s.get("duration", []),
            "throttles":     s.get("throttles", []),
            "concurrent":    s.get("concurrent", []),
            "period_hours":  hours,
            "period_secs":   _smart_period(hours),
        }
    except Exception as e:
        logger.warning(f"Lambda series [{function_name}]: {e}")
        return {"function_name": function_name, "invocations": [], "errors": [],
                "duration": [], "throttles": [], "concurrent": []}


# ── Metric series — RDS (now VM-backed) ──────────────────────────────────

def _get_rds_metric_series(db_id, region=None, hours=6) -> dict:
    try:
        end    = datetime.now(timezone.utc)
        start  = end - timedelta(hours=hours)
        period = _smart_period(hours)
        dim    = f'dimension_DBInstanceIdentifier="{db_id}"'

        def s(yace_metric):
            return vm_query_range(
                f'{yace_metric}{{{dim}}}',
                start=int(start.timestamp()), end=int(end.timestamp()),
                step=f"{period}s",
            )
        return {
            "db_id":           db_id,
            "cpu":             s("aws_rds_cpuutilization_average"),
            "free_storage":    s("aws_rds_free_storage_space_average"),
            "db_connections":  s("aws_rds_database_connections_average"),
            "read_iops":       s("aws_rds_read_iops_average"),
            "write_iops":      s("aws_rds_write_iops_average"),
            "read_latency":    s("aws_rds_read_latency_average"),
            "write_latency":   s("aws_rds_write_latency_average"),
            "freeable_memory": s("aws_rds_freeable_memory_average"),
            "period_hours":    hours,
            "period_secs":     period,
        }
    except Exception as e:
        logger.warning(f"RDS series [{db_id}]: {e}")
        return {"db_id": db_id, "cpu": [], "free_storage": [], "db_connections": [],
                "read_iops": [], "write_iops": [], "read_latency": [],
                "write_latency": [], "freeable_memory": []}


# ── Metric series — ELB (SPLIT: covered metrics via VM, rest via boto3) ─
# Your YACE config scrapes RequestCount, TargetResponseTime, HealthyHostCount,
# UnHealthyHostCount, HTTPCode_Target_2XX/4XX/5XX_Count, ActiveConnectionCount.
# It does NOT scrape HTTPCode_ELB_5XX_Count or NewConnectionCount — those two
# stay on boto3 until/unless you add them to the YACE job yourself.
# Dimension label assumed as "dimension_LoadBalancer" — verify with:
#   curl "http://<vm-host>/api/v1/series?match[]=aws_applicationelb_request_count_sum"

def _get_elb_metric_series(lb_name: str, region=None, hours=6) -> dict:
    try:
        elbv2 = boto3.client("elbv2", region_name=region)

        lb_dim = lb_name
        try:
            lbs = elbv2.describe_load_balancers(Names=[lb_name]).get("LoadBalancers", [])
            if lbs:
                arn    = lbs[0]["LoadBalancerArn"]
                lb_dim = arn.split("loadbalancer/")[-1]
        except Exception:
            pass

        end    = datetime.now(timezone.utc)
        start  = end - timedelta(hours=hours)
        period = _smart_period(hours)
        dim    = f'dimension_LoadBalancer="{lb_dim}"'

        def vm_series(yace_metric):
            return vm_query_range(
                f'{yace_metric}{{{dim}}}',
                start=int(start.timestamp()), end=int(end.timestamp()),
                step=f"{period}s",
            )

        # Boto3 fallback only for the two metrics YACE doesn't scrape
        cw   = boto3.client("cloudwatch", region_name=region)
        dims = [{"Name": "LoadBalancer", "Value": lb_dim}]
        ns   = "AWS/ApplicationELB"
        gmd_queries = [
            _make_query("errors_elb_5xx", ns, "HTTPCode_ELB_5XX_Count", dims, "Sum"),
            _make_query("new_conns",      ns, "NewConnectionCount",     dims, "Sum"),
        ]
        gmd = _gmd_series(cw, gmd_queries, hours)

        return {
            "lb_name":            lb_name,
            "requests":           vm_series("aws_applicationelb_request_count_sum"),
            "errors_5xx":         vm_series("aws_applicationelb_httpcode_target_5_xx_count_sum"),
            "errors_4xx":         vm_series("aws_applicationelb_httpcode_target_4_xx_count_sum"),
            "errors_elb_5xx":     gmd.get("errors_elb_5xx", []),   # boto3 — not in YACE
            "latency":            vm_series("aws_applicationelb_target_response_time_average"),
            "healthy_hosts":      vm_series("aws_applicationelb_healthy_host_count_average"),
            "unhealthy_hosts":    vm_series("aws_applicationelb_un_healthy_host_count_average"),
            "active_connections": vm_series("aws_applicationelb_active_connection_count_average"),
            "new_connections":    gmd.get("new_conns", []),        # boto3 — not in YACE
            "period_hours":       hours,
            "period_secs":        period,
        }
    except Exception as e:
        logger.warning(f"ELB series [{lb_name}]: {e}")
        return {"lb_name": lb_name, "requests": [], "errors_5xx": [], "errors_4xx": [],
                "errors_elb_5xx": [], "latency": [], "healthy_hosts": [],
                "unhealthy_hosts": [], "active_connections": [], "new_connections": []}


# ── Metric series — ECS (unchanged — not in YACE config) ────────────────

def _get_ecs_metric_series(cluster_name: str, service_name: str = None,
                           region=None, hours=6) -> dict:
    try:
        cw   = boto3.client("cloudwatch", region_name=region)
        dims = (
            [{"Name": "ClusterName", "Value": cluster_name},
             {"Name": "ServiceName", "Value": service_name}]
            if service_name
            else [{"Name": "ClusterName", "Value": cluster_name}]
        )
        queries = [
            _make_query("cpu", "AWS/ECS", "CPUUtilization",    dims, "Average"),
            _make_query("mem", "AWS/ECS", "MemoryUtilization", dims, "Average"),
        ]
        ci_ns = "ECS/ContainerInsights"
        queries += [
            _make_query("running",  ci_ns, "RunningTaskCount",  dims, "Average"),
            _make_query("pending",  ci_ns, "PendingTaskCount",  dims, "Average"),
            _make_query("desired",  ci_ns, "DesiredTaskCount",  dims, "Average"),
            _make_query("cpu_res",  ci_ns, "CpuReserved",       dims, "Average"),
            _make_query("mem_res",  ci_ns, "MemoryReserved",    dims, "Average"),
        ]
        s = _gmd_series(cw, queries, hours)
        return {
            "cluster_name":       cluster_name,
            "service_name":       service_name,
            "cpu_utilization":    s.get("cpu", []),
            "mem_utilization":    s.get("mem", []),
            "running_task_count": s.get("running", []),
            "pending_task_count": s.get("pending", []),
            "desired_task_count": s.get("desired", []),
            "cpu_reserved":       s.get("cpu_res", []),
            "mem_reserved":       s.get("mem_res", []),
            "period_hours":       hours,
            "period_secs":        _smart_period(hours),
        }
    except Exception as e:
        logger.warning(f"ECS series [{cluster_name}/{service_name}]: {e}")
        return {"cluster_name": cluster_name, "service_name": service_name,
                "cpu_utilization": [], "mem_utilization": [],
                "running_task_count": [], "pending_task_count": [],
                "desired_task_count": [], "cpu_reserved": [], "mem_reserved": []}


# ── check_and_write_alerts (SPLIT: ec2/ebs/rds via VM, lambda via GMD) ──

def check_and_write_alerts(account_id: int, region: str, thresholds: list) -> list:
    """
    Evaluates thresholds against current data.
    ec2/ebs/rds thresholds are checked against VictoriaMetrics.
    lambda (and anything else not in YACE) still uses the boto3 GMD batch.
    Writes breaches to alerts table. Returns list of breach dicts.
    """
    from app.db import get_connection

    cw = boto3.client("cloudwatch", region_name=region)

    ec2_instances = collect_ec2_instances(region)
    ebs_volumes   = collect_ebs_volumes(region)
    rds_instances = collect_rds_instances(region)
    lambda_funcs  = collect_lambda_functions(region)

    SERVICE_RESOURCES = {
        "ec2":    [(i["instance_id"], [{"Name": "InstanceId",           "Value": i["instance_id"]}]) for i in ec2_instances if i["state"] == "running"],
        "ebs":    [(v["volume_id"],   [{"Name": "VolumeId",             "Value": v["volume_id"]}])   for v in ebs_volumes   if v["state"] == "in-use"],
        "rds":    [(d["db_instance_id"], [{"Name": "DBInstanceIdentifier","Value": d["db_instance_id"]}]) for d in rds_instances],
        "lambda": [(f["function_name"],  [{"Name": "FunctionName",      "Value": f["function_name"]}])    for f in lambda_funcs],
    }
    NAMESPACE_MAP = {
        "ec2": "AWS/EC2", "ebs": "AWS/EBS",
        "rds": "AWS/RDS", "lambda": "AWS/Lambda",
        "alb": "AWS/ApplicationELB",
    }

    # svc -> dimension label YACE uses for this resource type
    VM_DIM_LABEL = {
        "ec2": "dimension_InstanceId",
        "ebs": "dimension_VolumeId",
        "rds": "dimension_DBInstanceIdentifier",
    }
    # Explicit map, NOT a generic snake_case conversion — YACE special-cases
    # acronyms (CPUUtilization -> cpuutilization, not c_p_u_utilization).
    # Extend this table if you threshold on new metrics that YACE scrapes.
    VM_METRIC_STUB = {
        ("ec2", "CPUUtilization"):      "aws_ec2_cpuutilization",
        ("ec2", "StatusCheckFailed"):   "aws_ec2_status_check_failed",
        ("ebs", "VolumeQueueLength"):   "aws_ebs_volume_queue_length",
        ("ebs", "BurstBalance"):        "aws_ebs_burst_balance",
        ("rds", "CPUUtilization"):      "aws_rds_cpuutilization",
        ("rds", "FreeStorageSpace"):    "aws_rds_free_storage_space",
    }
    STAT_SUFFIX = {"Average": "average", "Sum": "sum", "Maximum": "maximum"}

    vm_lookups  = []   # (t_idx, resource_id, promql)
    gmd_queries = []
    qid_map     = {}

    for t_idx, t in enumerate(thresholds):
        svc       = (t.get("service") or t.get("resource_type") or "").lower()
        namespace = NAMESPACE_MAP.get(svc, t.get("namespace", "AWS/EC2"))
        metric    = t["metric_name"]
        stat      = t.get("statistic") or "Average"
        resources = SERVICE_RESOURCES.get(svc, []) or [("account", [])]
        stub      = VM_METRIC_STUB.get((svc, metric))

        if svc in VM_DIM_LABEL and stub:
            dim_label   = VM_DIM_LABEL[svc]
            yace_metric = f"{stub}_{STAT_SUFFIX.get(stat, 'average')}"
            for resource_id, dims in resources:
                vm_lookups.append((t_idx, resource_id, f'{yace_metric}{{{dim_label}="{resource_id}"}}'))
        else:
            for resource_id, dims in resources:
                qid = _safe_qid(f"t{t_idx}__{resource_id}")
                gmd_queries.append(_make_query(qid, namespace, metric, dims, stat))
                qid_map[qid] = (resource_id, t_idx)

    all_vals = {}  # (t_idx, resource_id) -> value

    for t_idx, resource_id, promql in vm_lookups:
        val = vm_query(promql)
        if val is not None:
            all_vals[(t_idx, resource_id)] = val

    gmd_snap = _gmd_snapshot(cw, gmd_queries, minutes=3)
    for qid, val in gmd_snap.items():
        resource_id, t_idx = qid_map[qid]
        all_vals[(t_idx, resource_id)] = val

    breaches = []
    conn     = get_connection()
    cur      = conn.cursor()

    def breached(v, threshold, comp):
        return (
            (comp == ">"  and v >  threshold) or
            (comp == "<"  and v <  threshold) or
            (comp == ">=" and v >= threshold) or
            (comp == "<=" and v <= threshold)
        )

    for (t_idx, resource_id), val in all_vals.items():
        t         = thresholds[t_idx]
        comp      = t["comparison"]
        warn_val  = float(t["warning_value"])
        crit_val  = float(t["critical_value"])
        metric    = t["metric_name"]
        svc       = (t.get("service") or t.get("resource_type") or "").lower()

        if breached(val, crit_val, comp):
            severity = "CRITICAL"
        elif breached(val, warn_val, comp):
            severity = "WARNING"
        else:
            continue

        threshold_val = crit_val if severity == "CRITICAL" else warn_val
        breaches.append({
            "metric":    metric,
            "service":   svc,
            "resource":  resource_id,
            "value":     round(val, 4),
            "threshold": threshold_val,
            "severity":  severity,
        })
        try:
            cur.execute("""
                INSERT INTO alerts
                  (resource_id, metric_name, severity, status,
                   current_value, threshold, value,
                   triggered_at, environment)
                SELECT %s,%s,%s,'active',%s,%s,%s,NOW(),'PROD'
                FROM DUAL
                WHERE NOT EXISTS (
                  SELECT 1 FROM alerts
                  WHERE resource_id=%s AND metric_name=%s
                    AND status='active'
                    AND triggered_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)
                )
            """, (resource_id, metric, severity,
                  round(val, 4), threshold_val, round(val, 4),
                  resource_id, metric))
        except Exception as db_err:
            logger.warning(f"Alert insert [{resource_id}/{metric}]: {db_err}")

    conn.commit()
    cur.close()
    conn.close()
    return breaches


# ── Account summary (unchanged) ──────────────────────────────────────────

def get_account_summary(region=None) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    collectors = {
        "ec2": lambda: collect_ec2_instances(region),
        "ebs": lambda: collect_ebs_volumes(region),
        "rds": lambda: collect_rds_instances(region),
        "lmb": lambda: collect_lambda_functions(region),
        "s3":  lambda: collect_s3_buckets(region),
        "elb": lambda: collect_elb(region),
        "ecs": lambda: collect_ecs_clusters(region),
    }
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fn): key for key, fn in collectors.items()}
        for f in as_completed(futures):
            key = futures[f]
            try:
                results[key] = f.result()
            except Exception as e:
                logger.error(f"Collector [{key}]: {e}")
                results[key] = []

    ec2  = results.get("ec2", [])
    run  = [i for i in ec2 if i["state"] == "running"]
    stop = [i for i in ec2 if i["state"] == "stopped"]
    avg  = round(sum(i["cpu_utilization"] for i in run) / len(run), 2) if run else 0.0

    return {
        "ec2_total":    len(ec2),           "ec2_running":  len(run),
        "ec2_stopped":  len(stop),          "ec2_avg_cpu":  avg,
        "ebs_total":    len(results.get("ebs", [])),
        "rds_total":    len(results.get("rds", [])),
        "lambda_total": len(results.get("lmb", [])),
        "s3_total":     len(results.get("s3",  [])),
        "elb_total":    len(results.get("elb", [])),
        "ecs_total":    len(results.get("ecs", [])),
        "instances":    ec2,
        "ebs":          results.get("ebs", []),
        "rds":          results.get("rds", []),
        "lambdas":      results.get("lmb", []),
        "s3":           results.get("s3",  []),
        "elb":          results.get("elb", []),
        "ecs":          results.get("ecs", []),
    }


# ── Helpers ────────────────────────────────────────────────────────────

def _calc_uptime(lt) -> int:
    if not lt:
        return 0
    try:
        now = datetime.now(timezone.utc)
        if lt.tzinfo is None:
            lt = lt.replace(tzinfo=timezone.utc)
        return (now - lt).days
    except:
        return 0