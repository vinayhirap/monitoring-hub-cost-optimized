#!/usr/bin/env python3
"""
check_resource_tags.py

YACE discovers resources exclusively via the AWS Resource Groups Tagging
API (resourcegroupstaggingapi). A resource with ZERO tags is invisible to
YACE no matter how correct the config is - confirmed this session via the
"No tagged resources made it through filtering" errors for AWS/CloudFront
and AWS/WAFV2, both of which DO have resources (per resource_inventory_check.py)
but apparently none are tagged.

This queries the same Tagging API YACE uses, filtered to the namespaces
that showed resource_count > 0 in resource_inventory_check.py but live=False
in audit_all_metrics.py, and reports exactly which ARNs have tags and which
don't - so you know precisely which resources need at least one tag added
before YACE can ever discover them, versus which namespaces are a dead end
for a different reason (0 resources, already confirmed).

Note: the Tagging API's ResourceTypeFilters use short service names (e.g.
"cloudfront", "wafv2", "backup"), not CloudWatch namespace strings - mapped
below.

Usage:
    python check_resource_tags.py [region]

    region defaults to ap-south-1
"""
import sys
import boto3

region = sys.argv[1] if len(sys.argv) > 1 else "ap-south-1"

# namespace -> Tagging API resource type filter(s)
# Only the ones flagged nonzero-resources-but-not-live from resource_inventory_check.py
NAMESPACE_TO_FILTER = {
    "AWS/Backup": ["backup"],
    "AWS/CertificateManager": ["acm"],
    "AWS/CloudFront": ["cloudfront"],
    "AWS/Events": ["events"],
    "AWS/Kinesis": ["kinesis"],
    "AWS/Logs": ["logs"],
    "AWS/SNS": ["sns"],
    "AWS/SQS": ["sqs"],
    "AWS/WAFV2": ["wafv2"],
    "AWS/Lambda": ["lambda"],
    "AWS/S3": ["s3"],
}


def main():
    session = boto3.Session(region_name=region)
    tagging = session.client("resourcegroupstaggingapi")
    global_tagging = boto3.Session(region_name="us-east-1").client("resourcegroupstaggingapi")

    print(f"Checking tags via Resource Groups Tagging API (region={region})\n")

    for ns, filters in NAMESPACE_TO_FILTER.items():
        client = global_tagging if ns in ("AWS/CloudFront", "AWS/S3") else tagging
        try:
            paginator = client.get_paginator("get_resources")
            resources = []
            for page in paginator.paginate(ResourceTypeFilters=filters):
                resources.extend(page["ResourceTagMappingList"])

            print(f"{ns} ({filters[0]}): {len(resources)} tagged resource(s) visible to Tagging API")
            for r in resources:
                tag_str = ", ".join(f"{t['Key']}={t['Value']}" for t in r.get("Tags", []))
                print(f"    {r['ResourceARN']}  tags: [{tag_str}]" if tag_str
                      else f"    {r['ResourceARN']}  ** NO TAGS **")

            if not resources:
                print(f"    -> ZERO resources returned by Tagging API for this filter. "
                      f"Either every resource of this type has NO tags at all "
                      f"(most likely, given resource_inventory_check.py found some via "
                      f"direct list/describe calls), or the ResourceTypeFilter '{filters[0]}' "
                      f"is wrong for this service.")
            print()
        except Exception as e:
            print(f"{ns}: ERROR - {type(e).__name__}: {e}\n")

    print("=== TAKEAWAY ===")
    print("Any resource shown with '** NO TAGS **' or any namespace returning 0 resources")
    print("here (despite resource_inventory_check.py finding some) needs at least one tag")
    print("added in AWS before YACE can discover it. This is an AWS-side fix (console, CLI,")
    print("or IaC), not a monitoring-hub code or config change.")


if __name__ == "__main__":
    main()
