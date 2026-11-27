"""Run: python3 -m unittest infra/aws/status/test_lambda_function.py (no AWS, no boto3, no network)."""

import datetime as dt
import importlib.util
import json
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("status_fn", pathlib.Path(__file__).with_name("lambda_function.py"))
fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 27, 4, 0, tzinfo=UTC)


def series(hours, value=1.0, end=NOW):
    return {end - dt.timedelta(minutes=5 * i): value for i in range(1, hours * 12 + 1)}


def hist(ts, new):
    return {"Timestamp": ts, "HistoryData": json.dumps({"newState": {"stateValue": new}})}


class Uptime(unittest.TestCase):
    def test_missing_data_is_not_down(self):
        points = series(12)  # half of the last 24 h has readings, all up
        w = fn.uptime(points, NOW, 1)
        self.assertEqual((w["uptime_pct"], w["coverage_pct"], w["down_periods"]), (100.0, 50.0, 0))

    def test_down_periods_count(self):
        points = series(24)
        for t in list(points)[:6]:
            points[t] = 0.0
        w = fn.uptime(points, NOW, 1)
        self.assertEqual(w["down_periods"], 6)
        self.assertAlmostEqual(w["uptime_pct"], round(100 * 282 / 288, 3))

    def test_no_data_at_all(self):
        self.assertEqual(fn.uptime({}, NOW, 7)["uptime_pct"], None)

    def test_current_state(self):
        self.assertEqual(fn.current_state(series(1), NOW), "up")
        self.assertEqual(fn.current_state({NOW - dt.timedelta(minutes=5): 0.0}, NOW), "down")
        self.assertEqual(fn.current_state({NOW - dt.timedelta(hours=2): 1.0}, NOW), "unknown")


class Incidents(unittest.TestCase):
    def test_pairs_alarm_periods_and_attaches_notes(self):
        h = [hist(dt.datetime(2026, 11, 26, 14, 10, 16, tzinfo=UTC), "ALARM"),
             hist(dt.datetime(2026, 11, 26, 19, 49, 16, tzinfo=UTC), "OK"),
             hist(dt.datetime(2026, 11, 26, 3, 14, tzinfo=UTC), "OK")]
        out = fn.incidents(h, NOW)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["minutes"], 339)
        self.assertIn("not an outage", out[0]["note"])

    def test_open_incident(self):
        out = fn.incidents([hist(NOW - dt.timedelta(minutes=30), "ALARM")], NOW)
        self.assertEqual((out[0]["end"], out[0]["minutes"]), (None, 30))


class FakeCW:
    def __init__(self, points):
        self.points = points

    def get_metric_data(self, **_):
        ts = sorted(self.points)
        return {"MetricDataResults": [{"Timestamps": ts, "Values": [self.points[t] for t in ts]}]}

    def describe_alarm_history(self, **_):
        return {"AlarmHistoryItems": []}


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[Key] = (Body, kw.get("ContentType"))


class Handler(unittest.TestCase):
    def test_publishes_json_and_html(self):
        fn.freshness = lambda: {"reachable": False, "error": "URLError"}
        s3 = FakeS3()
        out = fn.handler({}, None, cw=FakeCW(series(48)), s3=s3, now=NOW)
        self.assertEqual(out, {"current": "up"})
        status = json.loads(s3.objects["status.json"][0])
        self.assertEqual(status["windows"]["24h"]["uptime_pct"], 100.0)
        body, ctype = s3.objects["index.html"]
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn(b"could not be read just now", body)
        self.assertEqual(status["windows"]["90d"]["coverage_pct"], 2.2)
        self.assertEqual(status["measured_since"], "2026-11-25T04:00+00:00")
        self.assertIn(b"Measured since 2026-11-25T04:00+00:00", body)


if __name__ == "__main__":
    unittest.main()
