"""Sunshine Ledger pilot-light control: starts and stops the AWS standby.

Deployed as the Lambda `sunshine-ledger-standby-control` (us-east-2, Python
3.12, handler control_lambda.handler). Invoked by:

* the SNS topic `sunshine-ledger-uptime-alerts`, which carries the
  `sunshine-ledger-api-down` alarm's ALARM and OK notifications (and this
  function's own emails, which it ignores);
* one-off EventBridge Scheduler schedules it creates itself
  ({"action": "stop-if-ok"} / {"action": "start-if-alarm"});
* the weekly EventBridge Scheduler schedule ({"action": "refresh"}).

The instance (tags project=sunshine-ledger, role=standby) reads its own
`standby-mode` tag on boot; see scripts/standby/standby-boot.sh. The tag
`automation=disabled` on the instance turns off alarm-driven starts (emails
still go out), e.g. during maintenance at home.

The decisions live in `decide()`, a pure function, so they can be tested
without AWS (scripts/standby/test_control_lambda.py).
"""

from __future__ import annotations

import datetime as dt
import json
import os

ALARM_NAME = os.environ.get("ALARM_NAME", "sunshine-ledger-api-down")
TOPIC_ARN = os.environ.get("TOPIC_ARN", "")
SCHEDULER_ROLE_ARN = os.environ.get("SCHEDULER_ROLE_ARN", "")
FAILBACK_DELAY_MINUTES = int(os.environ.get("FAILBACK_DELAY_MINUTES", "10"))
START_RETRY_MINUTES = 3


def parse_event(event: dict) -> tuple[str, str | None]:
    """Return (kind, detail): ("alarm", "ALARM"|"OK"|...), ("action", name) or ("ignore", why)."""
    if "action" in event:
        return "action", event["action"]
    records = event.get("Records") or []
    if not records or "Sns" not in records[0]:
        return "ignore", "unrecognised event"
    try:
        message = json.loads(records[0]["Sns"]["Message"])
    except (ValueError, TypeError):
        return "ignore", "not an alarm notification"
    if not isinstance(message, dict) or message.get("AlarmName") != ALARM_NAME:
        return "ignore", "not the uptime alarm"
    return "alarm", message.get("NewStateValue")


def decide(kind: str, detail: str | None, instance: dict | None, alarm_state: str) -> list[tuple]:
    """What to do. instance = {"id", "state", "mode", "automation"} or None.

    Returns a list of steps: ("start", mode), ("retag", mode), ("stop",),
    ("schedule", action, minutes), ("notify", subject, message).
    """
    if kind == "ignore":
        return []
    if instance is None:
        return [("notify", "no standby instance", f"{kind} {detail}: no instance tagged role=standby was found.")]

    state, mode = instance["state"], instance.get("mode") or "refresh"
    disabled = instance.get("automation") == "disabled"

    if (kind, detail) in {("alarm", "ALARM"), ("action", "start-if-alarm")}:
        if kind == "action" and alarm_state != "ALARM":
            return []  # recovered before the retry
        if disabled:
            return [("notify", "failover NOT started (automation disabled)",
                     f"The uptime alarm is in ALARM. The standby is {state}; automation=disabled, so nothing was started.")]
        if state == "stopped":
            return [("retag", "failover"), ("start", "failover"),
                    ("notify", "failover started", "The uptime alarm fired; starting the standby. It serves last night's backup read-only in ~15 min.")]
        if state in {"pending", "running"}:
            if mode == "failover":
                return []
            return [("retag", "failover"),
                    ("notify", "refresh switched to failover", "The uptime alarm fired during a refresh; the standby will serve once the refresh finishes.")]
        # stopping / shutting-down: cannot start yet; try again shortly.
        return [("schedule", "start-if-alarm", START_RETRY_MINUTES),
                ("notify", "failover delayed", f"The standby is {state}; retrying the start in {START_RETRY_MINUTES} min.")]

    if (kind, detail) == ("alarm", "OK"):
        if state in {"pending", "running"} and mode == "failover":
            return [("schedule", "stop-if-ok", FAILBACK_DELAY_MINUTES),
                    ("notify", "home is back; stopping soon",
                     f"The uptime alarm is OK. The standby stops in {FAILBACK_DELAY_MINUTES} min if it stays OK.")]
        return []

    if (kind, detail) == ("action", "stop-if-ok"):
        if alarm_state == "OK" and state in {"pending", "running"} and mode == "failover":
            return [("stop",), ("retag", "refresh"),
                    ("notify", "failover ended", "Home has been healthy for the failback delay; the standby is stopping.")]
        return []

    if (kind, detail) == ("action", "refresh"):
        if state != "stopped":
            return [("notify", "weekly refresh skipped", f"The standby is {state} (mode {mode}).")]
        if alarm_state == "ALARM":
            return [("notify", "weekly refresh skipped", "The uptime alarm is in ALARM; not refreshing during an outage.")]
        return [("retag", "refresh"), ("start", "refresh")]

    return [("notify", "unknown event", f"{kind} {detail}")]


# ---------------------------------------------------------------- AWS side

def _clients():
    import boto3  # available in the Lambda runtime
    return boto3.client("ec2"), boto3.client("cloudwatch"), boto3.client("sns"), boto3.client("scheduler")


def _find_instance(ec2) -> dict | None:
    resp = ec2.describe_instances(Filters=[
        {"Name": "tag:project", "Values": ["sunshine-ledger"]},
        {"Name": "tag:role", "Values": ["standby"]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
    ])
    found = [i for r in resp["Reservations"] for i in r["Instances"]]
    if not found:
        return None
    inst = found[0]
    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
    return {"id": inst["InstanceId"], "state": inst["State"]["Name"],
            "mode": tags.get("standby-mode"), "automation": tags.get("automation")}


def handler(event, _context):
    kind, detail = parse_event(event)
    if kind == "ignore":
        print(f"ignored: {detail}")
        return {"steps": []}
    ec2, cw, sns, scheduler = _clients()
    instance = _find_instance(ec2)
    alarms = cw.describe_alarms(AlarmNames=[ALARM_NAME])["MetricAlarms"]
    alarm_state = alarms[0]["StateValue"] if alarms else "INSUFFICIENT_DATA"
    steps = decide(kind, detail, instance, alarm_state)
    print(json.dumps({"kind": kind, "detail": detail, "instance": instance, "alarm": alarm_state, "steps": steps}))
    for step in steps:
        if step[0] == "retag":
            ec2.create_tags(Resources=[instance["id"]], Tags=[{"Key": "standby-mode", "Value": step[1]}])
        elif step[0] == "start":
            ec2.start_instances(InstanceIds=[instance["id"]])
        elif step[0] == "stop":
            ec2.stop_instances(InstanceIds=[instance["id"]])
        elif step[0] == "schedule":
            at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=step[2])
            scheduler.create_schedule(
                Name=f"sunshine-standby-{step[1]}-{at:%Y%m%d%H%M%S}",
                ScheduleExpression=f"at({at:%Y-%m-%dT%H:%M:%S})",
                FlexibleTimeWindow={"Mode": "OFF"},
                ActionAfterCompletion="DELETE",
                Target={"Arn": os.environ["FUNCTION_ARN"], "RoleArn": SCHEDULER_ROLE_ARN,
                        "Input": json.dumps({"action": step[1]})},
            )
        elif step[0] == "notify" and TOPIC_ARN:
            sns.publish(TopicArn=TOPIC_ARN, Subject=f"Sunshine standby: {step[1]}"[:100], Message=step[2])
    return {"steps": steps}
