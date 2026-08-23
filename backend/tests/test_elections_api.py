"""Election calendar tests (BRD 5.8).

The date arithmetic matters less than the constraint: BRD 5.8 allows
surfacing the calendar "without scoring or predictive claims at MVP", so
these also pin what the endpoint must NOT return.
"""

import datetime as dt

from app.data.elections import FLORIDA_2026, get_calendar


def test_returns_calendar_with_official_source(client):
    body = client.get("/elections", params={"state": "FL"}).json()
    assert body["state"] == "FL"
    assert body["source"]["url"].startswith("https://dos.fl.gov/")
    assert body["events"]


def test_unknown_state_404s(client):
    """Better a clear 404 than an empty calendar that reads as 'no elections'."""
    assert client.get("/elections", params={"state": "ZZ"}).status_code == 404


def test_defaults_to_configured_state(client):
    assert client.get("/elections").json()["state"] == "FL"


def test_marks_past_events_as_past(client):
    """A calendar still advertising a finished election as upcoming is worse
    than no calendar."""
    body = client.get("/elections", params={"state": "FL", "today": "2026-08-23"}).json()
    by_label = {e["label"]: e for e in body["events"]}

    assert by_label["Primary Election"]["is_past"] is True
    assert by_label["General Election"]["is_past"] is False


def test_next_event_is_the_soonest_upcoming_one(client):
    body = client.get("/elections", params={"state": "FL", "today": "2026-08-23"}).json()
    # Primary has passed; the next thing on the calendar is the general
    # registration deadline, not the general election itself.
    assert body["next_event"]["label"] == "Voter registration deadline (General)"
    assert body["next_event"]["is_past"] is False


def test_next_event_is_null_once_everything_has_passed(client):
    body = client.get("/elections", params={"state": "FL", "today": "2027-01-01"}).json()
    assert body["next_event"] is None
    assert all(e["is_past"] for e in body["events"])


def test_days_away_counts_from_the_given_date(client):
    body = client.get("/elections", params={"state": "FL", "today": "2026-11-01"}).json()
    general = next(e for e in body["events"] if e["label"] == "General Election")
    assert general["days_away"] == 2


def test_response_makes_no_predictive_or_candidate_claims(client):
    """BRD 5.8 permits the calendar but rules out scoring and prediction,
    and the Roadmap gates electioneering-adjacent work behind a legal review
    that hasn't happened. Nothing about candidates, parties, or outcomes
    belongs in this payload."""
    body = client.get("/elections", params={"state": "FL"}).json()
    blob = str(body).lower()
    for banned in ("candidate", "incumbent", "party", "poll", "forecast", "likely", "competitive", "seat"):
        assert banned not in blob, f"election payload should not mention {banned!r}"


def test_calendar_dates_fall_on_expected_weekdays():
    """Guards against transcription slips in hand-entered data: Florida holds
    elections on Tuesdays, closes registration on the Monday 29 days before,
    and runs early voting Saturday to Saturday."""
    events = {e.label: e.date for e in FLORIDA_2026.events}

    assert events["Primary Election"].weekday() == 1
    assert events["General Election"].weekday() == 1
    assert events["Voter registration deadline (Primary)"].weekday() == 0
    assert events["Voter registration deadline (General)"].weekday() == 0
    assert (events["Primary Election"] - events["Voter registration deadline (Primary)"]).days == 29
    assert (events["General Election"] - events["Voter registration deadline (General)"]).days == 29


def test_events_are_chronological():
    dates = [e.date for e in FLORIDA_2026.events]
    assert dates == sorted(dates)


def test_get_calendar_is_case_insensitive():
    assert get_calendar("fl") is FLORIDA_2026
    assert get_calendar("ZZ") is None


def test_verify_by_is_set_so_stale_data_is_visible():
    """No machine-readable feed backs this, so the re-check date has to be
    part of the payload rather than tribal knowledge."""
    assert isinstance(FLORIDA_2026.verify_by, dt.date)
