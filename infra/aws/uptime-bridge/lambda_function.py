"""Deployed as Lambda `sunshine-ledger-uptime-bridge` (us-east-2), every 5 minutes via EventBridge Scheduler.
Env: HEALTH_CHECK_ID, CHECK_NAME. CHECK_NAME MUST equal the dimension the alarm `sunshine-ledger-api-down`
watches (`sunshine-ledger-api`): changing it silently starves the alarm, which reads missing data as
breaching (the 2026-11-26 false failover). Source of truth: this file (docs/AWS_INVENTORY.md).

Bridge a Route 53 health check into a CloudWatch metric in this Region.

Route 53 publishes health-check metrics only in us-east-1, which the project's
managed policy does not let us alarm on. This function reads the check's
status from the global Route 53 API and writes 1 (healthy) or 0 (unhealthy)
to SunshineLedger/Uptime in the function's own Region, where an alarm emails.
"""
import os

import boto3

route53 = boto3.client("route53")
cloudwatch = boto3.client("cloudwatch")

HEALTH_CHECK_ID = os.environ["HEALTH_CHECK_ID"]
CHECK_NAME = os.environ.get("CHECK_NAME", "sunshine-ledger-api")


def lambda_handler(event, context):
    observations = route53.get_health_check_status(HealthCheckId=HEALTH_CHECK_ID)["HealthCheckObservations"]
    total = len(observations)
    ok = sum(1 for o in observations if o["StatusReport"]["Status"].startswith("Success"))
    # Same rule as Route 53 itself: healthy when more than 18% of checkers succeed.
    # (Was ">= 50%" until 2026-11-26. With the pilot-light standby also on the tunnel,
    # Cloudflare sends roughly half the checkers to it; its answers count as down by
    # design, so 50% left the alarm stuck in ALARM and the standby never failed back.
    # During a real outage every checker fails, so this still reads 0.)
    healthy = 1 if total and ok / total > 0.18 else 0
    cloudwatch.put_metric_data(
        Namespace="SunshineLedger/Uptime",
        MetricData=[{"MetricName": "Healthy", "Dimensions": [{"Name": "Check", "Value": CHECK_NAME}],
                     "Value": healthy, "Unit": "Count"}],
    )
    print(f"{CHECK_NAME}: {ok}/{total} checkers OK -> healthy={healthy}")
    return {"healthy": healthy, "ok": ok, "total": total}
