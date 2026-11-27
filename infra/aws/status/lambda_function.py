"""Public status page for Sunshine Ledger, published from AWS (Sunshine $100 gate).

Every 15 minutes (EventBridge Scheduler) this reads:
  * the independent uptime metric: Route 53 health checkers outside the home
    network -> `SunshineLedger/Uptime Healthy` (1 up / 0 down, every 5 minutes,
    written by infra/aws/uptime-bridge);
  * the alarm history of `sunshine-ledger-api-down` (incidents);
  * the site's own data freshness (`/health/data`, `/sources/status`), best effort,
and writes `status.json` and `index.html` to a private S3 bucket that CloudFront
serves. Nothing here is reachable from the internet except those two files, so a
traffic spike can't use up the account's Lambda concurrency (the failover
Lambda needs it).

Missing data is never counted as down: a 5-minute period with no reading is
"no data", and each window reports its coverage. (On 2026-11-26 a renamed metric
left a 5-hour gap while the site was up.)
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.request

NAMESPACE = "SunshineLedger/Uptime"
METRIC = "Healthy"
CHECK = os.environ.get("CHECK_NAME", "sunshine-ledger-api")
ALARM = os.environ.get("ALARM_NAME", "sunshine-ledger-api-down")
BUCKET = os.environ.get("STATUS_BUCKET", "")
API = os.environ.get("API_BASE", "https://sunshineledger-api.josephbernal.com")
SITE = os.environ.get("SITE_URL", "https://sunshineledger.josephbernal.com")
PERIOD = 300
WINDOWS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}

# Context for alarm periods that a reader would otherwise misread. Keyed by the
# UTC start of the ALARM state (minute precision). Keep each note factual.
INCIDENT_NOTES = {
    "2026-11-26T14:10": "Monitoring fault, not an outage: a renamed uptime metric left the alarm "
                        "without data. The site stayed up; the backup server answered read-only "
                        "until 19:13 UTC.",
}


def uptime(points: dict[dt.datetime, float], now: dt.datetime, days: int) -> dict:
    """Share of 5-minute periods up, over the periods that have a reading."""
    start = now - dt.timedelta(days=days)
    expected = int(days * 86400 / PERIOD)
    seen = [v for t, v in points.items() if start <= t < now]
    up = sum(1 for v in seen if v >= 1)
    return {
        "uptime_pct": round(100 * up / len(seen), 3) if seen else None,
        "coverage_pct": round(100 * min(len(seen), expected) / expected, 1),
        "down_periods": len(seen) - up,
    }


def incidents(history: list[dict], now: dt.datetime) -> list[dict]:
    """ALARM periods from StateUpdate history items (oldest first)."""
    out, open_at = [], None
    for item in sorted(history, key=lambda h: h["Timestamp"]):
        data = json.loads(item.get("HistoryData") or "{}")
        new = (data.get("newState") or {}).get("stateValue")
        ts = item["Timestamp"].astimezone(dt.timezone.utc)
        if new == "ALARM" and open_at is None:
            open_at = ts
        elif new != "ALARM" and open_at is not None:
            out.append((open_at, ts))
            open_at = None
    if open_at is not None:
        out.append((open_at, None))
    result = []
    for start, end in out:
        key = start.strftime("%Y-%m-%dT%H:%M")
        result.append({
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes") if end else None,
            "minutes": round(((end or now) - start).total_seconds() / 60),
            "note": INCIDENT_NOTES.get(key),
        })
    return list(reversed(result))


def current_state(points: dict[dt.datetime, float], now: dt.datetime) -> str:
    recent = [v for t, v in sorted(points.items()) if t >= now - dt.timedelta(minutes=20)]
    if not recent:
        return "unknown"
    return "up" if recent[-1] >= 1 else "down"


def build(points, history, freshness, now) -> dict:
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "site": SITE,
        "method": ("Route 53 health checkers outside our network request the API's /health every 30 s; "
                   "a 5-minute period counts as up when more than 18% of checkers succeed. Periods "
                   "without a reading are excluded and shown as coverage."),
        "current": current_state(points, now),
        "measured_since": min(points).isoformat(timespec="minutes") if points else None,
        "windows": {name: uptime(points, now, days) for name, days in WINDOWS.items()},
        "incidents": incidents(history, now),
        "data": freshness,
    }


def render_html(s: dict) -> str:
    e = html.escape
    def pct(v):
        return "no data" if v is None else f"{v:.2f}%"

    rows = "".join(
        f"<tr><td>{e(k)}</td><td>{pct(w['uptime_pct'])}</td><td>{w['coverage_pct']:.1f}%</td></tr>"
        for k, w in s["windows"].items())
    inc = "".join(
        f"<li>{e(i['start'])} to {e(i['end'] or 'now')} ({i['minutes']} min)"
        f"{(' &mdash; ' + e(i['note'])) if i['note'] else ''}</li>" for i in s["incidents"]) or "<li>None recorded.</li>"
    d = s["data"]
    data = (f"<p>Last data update: {e(str(d.get('last_ingest_at') or 'unknown'))}. "
            f"Sources fresh: {e(str(d.get('sources_fresh', '?')))} of {e(str(d.get('sources_total', '?')))}.</p>"
            if d.get("reachable") else "<p>The site's data status could not be read just now.</p>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunshine Ledger status</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;color:#1e293b}}
table{{border-collapse:collapse}}td,th{{padding:.25rem .75rem;border-bottom:1px solid #e2e8f0;text-align:left}}</style></head><body>
<h1>Sunshine Ledger status</h1>
<p><strong>Now: {e(s['current'])}</strong> (checked {e(s['generated_at'])} UTC). <a href="{e(s['site'])}">Go to the site</a>.</p>
<h2>Uptime</h2><p>Measured since {e(s['measured_since'] or 'not yet')} UTC; a window that started earlier counts only the time measured (see Coverage).</p><table><tr><th>Window</th><th>Up</th><th>Coverage</th></tr>{rows}</table>
<p>{e(s['method'])}</p>
<h2>Incidents (alarm periods)</h2><ul>{inc}</ul>
<h2>Data freshness</h2>{data}
<p>This page is published from Amazon Web Services, separately from the site, so it stays up when the site does not.
Raw data: <a href="status.json">status.json</a>.</p></body></html>"""


def freshness() -> dict:
    def get(path):
        req = urllib.request.Request(API + path, headers={"User-Agent": "sunshine-status/1"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    try:
        health = get("/health/data")
        sources = get("/sources/status")
        sources = sources if isinstance(sources, list) else sources.get("sources", [])
        return {"reachable": True, "last_ingest_at": health.get("last_ingest_at"),
                "sources_total": len(sources), "sources_fresh": sum(1 for x in sources if not x.get("stale"))}
    except Exception as exc:  # best effort: the status page must still publish
        return {"reachable": False, "error": type(exc).__name__}


def handler(_event, _context, *, cw=None, s3=None, now=None):
    if cw is None or s3 is None:
        import boto3

        cw, s3 = boto3.client("cloudwatch"), boto3.client("s3")
    now = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0)
    start = now - dt.timedelta(days=max(WINDOWS.values()))
    points: dict[dt.datetime, float] = {}
    kwargs = {"MetricDataQueries": [{"Id": "h", "MetricStat": {
        "Metric": {"Namespace": NAMESPACE, "MetricName": METRIC, "Dimensions": [{"Name": "Check", "Value": CHECK}]},
        "Period": PERIOD, "Stat": "Minimum"}}], "StartTime": start, "EndTime": now}
    while True:
        page = cw.get_metric_data(**kwargs)
        for r in page["MetricDataResults"]:
            points.update({t.astimezone(dt.timezone.utc): v for t, v in zip(r["Timestamps"], r["Values"])})
        if not page.get("NextToken"):
            break
        kwargs["NextToken"] = page["NextToken"]
    history = cw.describe_alarm_history(AlarmName=ALARM, HistoryItemType="StateUpdate", StartDate=start,
                                        MaxRecords=100).get("AlarmHistoryItems", [])
    status = build(points, history, freshness(), now)
    s3.put_object(Bucket=BUCKET, Key="status.json", Body=json.dumps(status, indent=2).encode(),
                  ContentType="application/json", CacheControl="max-age=60")
    s3.put_object(Bucket=BUCKET, Key="index.html", Body=render_html(status).encode(),
                  ContentType="text/html; charset=utf-8", CacheControl="max-age=60")
    print(json.dumps({"current": status["current"], "windows": status["windows"]}))
    return {"current": status["current"]}
