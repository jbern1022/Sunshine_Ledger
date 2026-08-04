"""Pure-function tests for pipeline parsing/mapping logic -- no DB, no
network. These are the cheap, fast half of the suite; the API tests
cover the DB-backed half."""

from datetime import date

from app.pipeline.gdelt import _parse_seendate
from app.pipeline.legiscan import STATUS_MAP, _parse_date


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
