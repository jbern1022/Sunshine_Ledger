"""Tests for the Miami iQM2 scraper (app.pipeline.miami_iqm2). Pure-function
/ HTML-parsing coverage only -- no DB, no network. This is explicitly the
most fragile ingestion path in the repo (undocumented page structure that
could change without notice), which makes it the one most worth pinning
down with tests rather than the one to skip because it's "just a scraper"."""

from datetime import date

from app.pipeline.miami_iqm2 import IQM2Client, _parse_date_text, _split_sponsors

_FULL_RECORD_HTML = """
<html><body>
<span id="ContentPlaceholder1_lblLegiFileType">Resolution</span>
<span id="ContentPlaceholder1_lblResNum">R-26-0123</span>
<span id="ContentPlaceholder1_lblStatus">Adopted</span>
<a id="ContentPlaceholder1_lnkDate">Jul 23, 2026 10:00 AM</a>
<span id="ContentPlaceholder1_lblLegiFileTitle">A resolution approving the annual budget.</span>
<table id="tblLegiFileInfo">
  <tr><th>Department:</th><td>Office of the City Clerk</td></tr>
  <tr><th>Sponsors:</th><td>Ralph Rosado; Joe Carollo</td></tr>
</table>
</body></html>
"""

_MINIMAL_RECORD_HTML = """
<html><body>
<span id="ContentPlaceholder1_lblLegiFileTitle">Untitled but real record.</span>
</body></html>
"""

_NOT_A_RECORD_HTML = """
<html><body><p>This ID has no legislation content.</p></body></html>
"""


def _client() -> IQM2Client:
    # Construction doesn't hit the network -- httpx.Client() is lazy.
    return IQM2Client()


def test_parse_extracts_all_fields_from_a_full_record():
    record = _client()._parse(_FULL_RECORD_HTML, legi_file_id=19601)

    assert record == {
        "legi_file_id": 19601,
        "number": "R-26-0123",
        "type": "Resolution",
        "status": "Adopted",
        "date_text": "Jul 23, 2026 10:00 AM",
        "title": "A resolution approving the annual budget.",
        "department": "Office of the City Clerk",
        "sponsors": "Ralph Rosado; Joe Carollo",
    }


def test_parse_returns_none_when_the_id_is_not_a_legislation_record():
    # This is the guard that makes find_recent_ids' gap-skipping correct --
    # the ID space isn't contiguous, and other content types share it.
    assert _client()._parse(_NOT_A_RECORD_HTML, legi_file_id=19602) is None


def test_parse_falls_back_gracefully_when_optional_fields_are_missing():
    record = _client()._parse(_MINIMAL_RECORD_HTML, legi_file_id=19603)

    assert record is not None
    assert record["title"] == "Untitled but real record."
    assert record["number"] == "19603"  # falls back to the ID itself
    assert record["type"] is None
    assert record["status"] == "Unknown"
    assert record["date_text"] is None
    assert record["department"] is None
    assert record["sponsors"] == ""


def test_parse_date_text_extracts_a_date_from_surrounding_text():
    # Real field value confirmed live against miamifl.iqm2.com: abbreviated
    # month name plus a trailing time-of-day, e.g. "Jul 23, 2026 10:00 AM".
    # The regex uses search(), not fullmatch(), specifically to tolerate that
    # trailing text -- this pins the real format down rather than a guess.
    assert _parse_date_text("Jul 23, 2026 10:00 AM") == date(2026, 7, 23)


def test_parse_date_text_none():
    assert _parse_date_text(None) is None


def test_parse_date_text_malformed():
    assert _parse_date_text("no date here") is None


def test_split_sponsors_handles_semicolon_separated_names():
    assert _split_sponsors("Ralph Rosado; Joe Carollo") == ["Ralph Rosado", "Joe Carollo"]


def test_split_sponsors_does_not_split_on_commas_inside_a_single_title():
    # Documented gotcha in the source: "Commissioner, District Four Ralph
    # Rosado" contains a comma that is part of one person's title, not a
    # separator between two people.
    assert _split_sponsors("Commissioner, District Four Ralph Rosado") == [
        "Commissioner, District Four Ralph Rosado"
    ]


def test_split_sponsors_empty_string_returns_no_sponsors():
    assert _split_sponsors("") == []


def test_split_sponsors_strips_whitespace_and_drops_empty_segments():
    assert _split_sponsors(" Ralph Rosado ;; Joe Carollo ") == ["Ralph Rosado", "Joe Carollo"]
