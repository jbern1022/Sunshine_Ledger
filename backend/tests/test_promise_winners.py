from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import ElectionWinner, Entity
from app.promises.winners import (
    WinnersError,
    import_winners,
    link_people,
    name_key,
    parse_chamber,
    parse_csv,
    parse_district,
)

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
CSV = """Office,District,Candidate,Party,Incumbent
State Senator,SD-012,"Smith, Jane A.",REP,yes
Representative in the Legislature,45,John Q. Public,DEM,no
"""


def test_parse_chamber_and_district():
    assert parse_chamber("State Senator") == "senate"
    assert parse_chamber("Representative in the Legislature") == "house"
    assert parse_chamber("HD") == "house"
    assert parse_district("SD-012") == 12
    assert parse_district("HD 45") == 45
    with pytest.raises(WinnersError):
        parse_chamber("Governor")
    with pytest.raises(WinnersError):
        parse_district("at large")


def test_name_key_ignores_order_case_accents_and_suffixes():
    assert name_key("Smith, Jane A.") == name_key("jane smith") == name_key("Jané Smith Jr.")
    assert name_key("Jane Smith") != name_key("Janet Smith")


def test_parse_csv_reads_aliases_and_values():
    rows = parse_csv(CSV)
    assert rows[0] == {"chamber": "senate", "district": 12, "name": "Smith, Jane A.", "party": "REP", "incumbent": True}
    assert rows[1]["chamber"] == "house" and rows[1]["incumbent"] is False


def test_parse_csv_rejects_missing_columns_and_duplicate_seats():
    with pytest.raises(WinnersError, match="missing column"):
        parse_csv("chamber,district\nhouse,1\n")
    with pytest.raises(WinnersError, match="twice"):
        parse_csv("chamber,district,name\nhouse,1,A B\nhouse,1,C D\n")


def test_import_then_certify_records_changes(db_session):
    rows = parse_csv(CSV)
    counts = import_winners(db_session, rows, cycle=2026, source_url="https://x/unofficial", certified=False, now=NOW)
    assert counts["created"] == 2
    again = import_winners(db_session, rows, cycle=2026, source_url="https://x/unofficial", certified=False, now=NOW)
    assert again["unchanged"] == 2

    rows[1]["name"] = "John Quincy Public"
    counts = import_winners(db_session, rows, cycle=2026, source_url="https://x/certified", certified=True, now=NOW)
    assert counts["changed"] == 2  # both move to certified; one also changed name
    w = db_session.execute(select(ElectionWinner).where(ElectionWinner.district == 45)).scalar_one()
    assert w.result_status == "certified"
    assert w.name == "John Quincy Public"
    assert w.change_log[-1]["changes"]["name"]["from"] == "John Q. Public"


def test_certified_is_never_set_back_to_unofficial(db_session):
    rows = parse_csv(CSV)
    import_winners(db_session, rows, cycle=2026, source_url="u", certified=True, now=NOW)
    counts = import_winners(db_session, rows, cycle=2026, source_url="u2", certified=False, now=NOW)
    assert counts["skipped_certified"] == 2
    assert all(w.result_status == "certified" for w in db_session.execute(select(ElectionWinner)).scalars())


def _person(db, name, district):
    e = Entity(entity_type="person", name=name, jurisdiction_level="state", jurisdiction_name="FL",
               external_ids={}, attributes={"district": district, "role": "Rep"})
    db.add(e)
    db.flush()
    return e


def test_link_people_needs_seat_and_name(db_session):
    import_winners(db_session, parse_csv(CSV), cycle=2026, source_url="u", certified=False, now=NOW)
    jane = _person(db_session, "Jane Smith", "SD-012")
    _person(db_session, "John Public", "HD-99")  # right name, wrong seat: must not link
    result = link_people(db_session, cycle=2026)
    assert result == {"linked": 1, "no_match": 1, "ambiguous": 0}
    w12 = db_session.execute(select(ElectionWinner).where(ElectionWinner.district == 12)).scalar_one()
    w45 = db_session.execute(select(ElectionWinner).where(ElectionWinner.district == 45)).scalar_one()
    assert w12.person_entity_id == jane.id
    assert w45.person_entity_id is None


def test_link_people_leaves_two_candidates_unlinked(db_session):
    import_winners(db_session, parse_csv(CSV), cycle=2026, source_url="u", certified=False, now=NOW)
    _person(db_session, "Jane Smith", "SD-012")
    _person(db_session, "Smith, Jane", "SD-012")
    assert link_people(db_session, cycle=2026)["ambiguous"] == 1
