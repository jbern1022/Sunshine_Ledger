"""Tests for the standby control decisions (no AWS needed).

Run: python3 -m unittest scripts/standby/test_control_lambda.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from control_lambda import decide, parse_event  # noqa: E402


def sns(message):
    return {"Records": [{"Sns": {"Message": message if isinstance(message, str) else json.dumps(message)}}]}


def inst(state="stopped", mode="refresh", automation=None):
    return {"id": "i-1", "state": state, "mode": mode, "automation": automation}


def kinds(steps):
    return [s[0] for s in steps]


class ParseEvent(unittest.TestCase):
    def test_alarm_transition(self):
        self.assertEqual(parse_event(sns({"AlarmName": "sunshine-ledger-api-down", "NewStateValue": "ALARM"})),
                         ("alarm", "ALARM"))

    def test_own_email_and_other_alarms_are_ignored(self):
        # The function publishes to the same topic it listens on: no loops.
        self.assertEqual(parse_event(sns("Home is back; the standby is stopping."))[0], "ignore")
        self.assertEqual(parse_event(sns({"AlarmName": "something-else", "NewStateValue": "ALARM"}))[0], "ignore")

    def test_scheduler_action(self):
        self.assertEqual(parse_event({"action": "refresh"}), ("action", "refresh"))


class Decide(unittest.TestCase):
    def test_alarm_starts_a_stopped_standby_in_failover_mode(self):
        steps = decide("alarm", "ALARM", inst(), "ALARM")
        self.assertEqual(steps[:2], [("retag", "failover"), ("start", "failover")])

    def test_alarm_with_automation_disabled_only_emails(self):
        self.assertEqual(kinds(decide("alarm", "ALARM", inst(automation="disabled"), "ALARM")), ["notify"])

    def test_alarm_during_refresh_retags_without_starting(self):
        self.assertEqual(kinds(decide("alarm", "ALARM", inst("running", "refresh"), "ALARM")), ["retag", "notify"])

    def test_alarm_while_already_failing_over_is_a_no_op(self):
        self.assertEqual(decide("alarm", "ALARM", inst("running", "failover"), "ALARM"), [])

    def test_alarm_while_stopping_retries_later(self):
        steps = decide("alarm", "ALARM", inst("stopping", "failover"), "ALARM")
        self.assertEqual(steps[0][:2], ("schedule", "start-if-alarm"))

    def test_start_retry_does_nothing_once_recovered(self):
        self.assertEqual(decide("action", "start-if-alarm", inst(), "OK"), [])

    def test_ok_schedules_a_delayed_stop_instead_of_stopping(self):
        steps = decide("alarm", "OK", inst("running", "failover"), "OK")
        self.assertEqual(steps[0][:2], ("schedule", "stop-if-ok"))
        self.assertNotIn("stop", kinds(steps))

    def test_ok_never_interrupts_a_refresh(self):
        self.assertEqual(decide("alarm", "OK", inst("running", "refresh"), "OK"), [])

    def test_delayed_stop_only_if_still_ok(self):
        self.assertEqual(kinds(decide("action", "stop-if-ok", inst("running", "failover"), "OK")),
                         ["stop", "retag", "notify"])
        self.assertEqual(decide("action", "stop-if-ok", inst("running", "failover"), "ALARM"), [])

    def test_weekly_refresh_starts_only_a_stopped_standby_outside_an_outage(self):
        self.assertEqual(decide("action", "refresh", inst(), "OK"), [("retag", "refresh"), ("start", "refresh")])
        self.assertEqual(kinds(decide("action", "refresh", inst(), "ALARM")), ["notify"])
        self.assertEqual(kinds(decide("action", "refresh", inst("running", "failover"), "OK")), ["notify"])

    def test_missing_instance_is_reported(self):
        self.assertEqual(kinds(decide("alarm", "ALARM", None, "ALARM")), ["notify"])


if __name__ == "__main__":
    unittest.main()
