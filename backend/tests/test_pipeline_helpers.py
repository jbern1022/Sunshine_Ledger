"""Pure-function tests for pipeline parsing/mapping logic -- no DB, no
network. These are the cheap, fast half of the suite; the API tests
cover the DB-backed half."""

from datetime import date

import pytest

from app.pipeline.gdelt import _parse_seendate
from app.pipeline.legiscan import STATUS_MAP, _parse_date
from app.pipeline.legistar import _bill_session, _bill_title
from app.pipeline.legistar import _parse_date as legistar_parse_date
from app.pipeline.legistar import ingest_local_bills


def test_legiscan_status_map_covers_known_codes():
    assert STATUS_MAP[1] == "Introduced"
    assert STATUS_MAP[4] == "Passed"
    assert STATUS_MAP[6] == "Failed"


def test_legiscan_parse_date_valid():
    assert _parse_date("2026-03-05") == date(2026, 3, 5)


def test_legiscan_parse_date_none():
    assert _parse_date(None) is None


def test_legiscan_parse_date_malformed():
    assert _parse_date("not-a-date") is None


def test_gdelt_parse_seendate_valid():
    parsed = _parse_seendate("20260305T143000Z")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 3
    assert parsed.day == 5
    assert parsed.hour == 14


def test_gdelt_parse_seendate_none():
    assert _parse_seendate(None) is None


def test_gdelt_parse_seendate_malformed():
    assert _parse_seendate("garbage") is None


def test_legistar_parse_date_valid():
    assert legistar_parse_date("2026-03-05T00:00:00") == date(2026, 3, 5)


def test_legistar_parse_date_none():
    assert legistar_parse_date(None) is None


def test_legistar_parse_date_malformed():
    assert legistar_parse_date("not-a-date") is None


def test_legistar_bill_title_prefers_matter_name():
    assert _bill_title({"MatterId": 1, "MatterName": "Real Name", "MatterTitle": "Fallback"}) == "Real Name"


def test_legistar_bill_title_falls_back_to_matter_title():
    # MatterName is null in practice for every confirmed Legistar client --
    # this is the real-world path, not the edge case.
    assert _bill_title({"MatterId": 1, "MatterName": None, "MatterTitle": "The Real Title"}) == "The Real Title"


def test_legistar_bill_title_falls_back_to_matter_id_when_both_are_missing():
    assert _bill_title({"MatterId": 42}) == "Matter 42"


def test_legistar_bill_title_truncates_to_fit_the_500_char_entity_name_column():
    # A regression guard for the real incident class this column caused:
    # nightly ingestion crashed for four consecutive nights (Aug 21-24,
    # 2026) on an over-long free-text field blowing past a DB column limit.
    # See docs/RUNBOOK.md's "Watch DB column length limits" gotcha.
    long_title = "A" * 600
    result = _bill_title({"MatterId": 1, "MatterName": long_title})
    assert len(result) == 490
    assert result.endswith("…")


def test_legistar_bill_title_exactly_at_the_limit_is_not_truncated():
    exact_title = "A" * 490
    assert _bill_title({"MatterId": 1, "MatterName": exact_title}) == exact_title


def test_legistar_bill_session_uses_the_agenda_date_year():
    assert _bill_session({"MatterAgendaDate": "2026-03-05T00:00:00"}) == "2026"


def test_legistar_bill_session_falls_back_to_current_when_missing():
    assert _bill_session({}) == "current"


def test_legistar_bill_session_falls_back_to_current_when_unparseable():
    # A real-world guard: str(...)[:4] on garbage input used to produce a
    # truthy non-year string (e.g. "abcd") that silently passed through as
    # the session label instead of falling back.
    assert _bill_session({"MatterAgendaDate": "not-a-real-date"}) == "current"


def test_ingest_local_bills_rejects_an_unsupported_client_before_touching_the_network_or_db():
    # Legistar client tokens aren't guessable from the city name (Miami is
    # "miamifl", not "miami") and a wrong one 500s with an opaque error --
    # see docs/RUNBOOK.md. This should fail fast and locally instead.
    with pytest.raises(ValueError, match="Unsupported Legistar client"):
        ingest_local_bills(None, client_name="not-a-real-client", limit=1)
