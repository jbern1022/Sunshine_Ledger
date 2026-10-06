"""Monthly LegiScan ledger and the 70%/90% ntfy warnings."""

from datetime import date

import pytest

import app.pipeline.legiscan as legiscan
from app.config import settings
from app.pipeline import usage_alerts


@pytest.fixture(autouse=True)
def fresh_counters(monkeypatch):
    monkeypatch.setattr(legiscan, "API_CALLS", legiscan.API_CALLS.__class__())
    monkeypatch.setattr(legiscan, "_RECORDED", legiscan._RECORDED.__class__())
    monkeypatch.setattr(settings, "legiscan_monthly_limit", 100)


def test_records_only_new_calls(db_session):
    legiscan.API_CALLS.update({"getBill": 3, "getMasterList": 1})
    assert legiscan.record_api_usage(db_session) == 4
    assert legiscan.record_api_usage(db_session) == 0  # already recorded
    legiscan.API_CALLS["getBill"] += 2
    assert legiscan.record_api_usage(db_session) == 2
    assert legiscan.month_to_date(db_session) == 6


def test_report_adds_the_month_to_date(db_session):
    legiscan.API_CALLS["getBill"] = 5
    report = legiscan.report_api_usage(db_session)
    assert report.startswith("LegiScan API calls this run: 5 (getBill 5)")
    assert report.endswith("LegiScan calls this month (our ledger): 5 of 100")


def test_alerts_once_per_level_per_month(db_session):
    sent = []
    legiscan.API_CALLS["getBill"] = 69
    legiscan.record_api_usage(db_session)
    assert usage_alerts.check_monthly_usage(db_session, send=sent.append) is None

    legiscan.API_CALLS["getBill"] = 75
    legiscan.record_api_usage(db_session)
    assert usage_alerts.check_monthly_usage(db_session, send=sent.append) == 70
    assert usage_alerts.check_monthly_usage(db_session, send=sent.append) is None
    assert "75 of 100 (70%+)" in sent[0]

    legiscan.API_CALLS["getBill"] = 95
    legiscan.record_api_usage(db_session)
    assert usage_alerts.check_monthly_usage(db_session, send=sent.append) == 90
    assert len(sent) == 2


def test_a_new_month_alerts_again(db_session, monkeypatch):
    sent = []
    legiscan.API_CALLS["getBill"] = 95
    legiscan.record_api_usage(db_session)
    assert usage_alerts.check_monthly_usage(db_session, send=sent.append) == 90

    monkeypatch.setattr(legiscan, "month_start", lambda today=None: date(2099, 1, 1))
    monkeypatch.setattr(usage_alerts, "month_start", lambda today=None: date(2099, 1, 1))
    legiscan.API_CALLS["getBill"] = 190  # 95 new calls, in the new month
    legiscan.record_api_usage(db_session)
    assert usage_alerts.check_monthly_usage(db_session, send=sent.append) == 90
    assert len(sent) == 2


def test_a_failed_send_is_retried_next_run(db_session):
    legiscan.API_CALLS["getBill"] = 80
    legiscan.record_api_usage(db_session)

    def down(message):
        raise ConnectionError("ntfy down")

    assert usage_alerts.check_monthly_usage(db_session, send=down) is None
    assert usage_alerts.check_monthly_usage(db_session, send=lambda m: None) == 70


def test_budget_cap_never_exceeds_what_is_left(db_session):
    legiscan.API_CALLS["getBill"] = 90  # 10 of 100 left
    legiscan.record_api_usage(db_session)
    assert legiscan.remaining_monthly_calls(db_session) == 10
    assert legiscan.cap_to_monthly_budget(db_session, 1500) == 10
    assert legiscan.cap_to_monthly_budget(db_session, 4) == 4


def test_budget_cap_is_zero_when_over_and_refuses_with_a_reserve(db_session):
    legiscan.API_CALLS["getBill"] = 120  # over the limit
    legiscan.record_api_usage(db_session)
    assert legiscan.remaining_monthly_calls(db_session) == 0
    assert legiscan.cap_to_monthly_budget(db_session, 10) == 0
    with pytest.raises(legiscan.MonthlyBudgetExceeded):
        legiscan.cap_to_monthly_budget(db_session, 10, reserve=2)


def test_budget_cap_reserves_calls_for_the_fixed_cost(db_session):
    legiscan.API_CALLS["getBill"] = 98  # 2 left; the dataset alone costs 2
    legiscan.record_api_usage(db_session)
    with pytest.raises(legiscan.MonthlyBudgetExceeded):
        legiscan.cap_to_monthly_budget(db_session, 50, reserve=3)
    assert legiscan.cap_to_monthly_budget(db_session, 50, reserve=2) == 0
