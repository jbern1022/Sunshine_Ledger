from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import ElectionWinner, Entity
from app.promises.winners import (
    WinnersError,
    import_winners,
    link_people,
    mark_incumbents,
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
    assert result == {"linked": 1, "linked_variant": 0, "no_match": 1, "ambiguous": 0}
    w12 = db_session.execute(select(ElectionWinner).where(ElectionWinner.district == 12)).scalar_one()
    w45 = db_session.execute(select(ElectionWinner).where(ElectionWinner.district == 45)).scalar_one()
    assert w12.person_entity_id == jane.id
    assert w45.person_entity_id is None


def test_link_people_leaves_two_candidates_unlinked(db_session):
    import_winners(db_session, parse_csv(CSV), cycle=2026, source_url="u", certified=False, now=NOW)
    _person(db_session, "Jane Smith", "SD-012")
    _person(db_session, "Smith, Jane", "SD-012")
    assert link_people(db_session, cycle=2026)["ambiguous"] == 1


@pytest.mark.parametrize(
    "printed,clean",
    [
        ("Boyd, Jim President", "Boyd, Jim"),
        ("Rodriguez, Ana Maria President Pro Tempore", "Rodriguez, Ana Maria"),
        ("DiCeglie, Nick Majority (Republican) Leader", "DiCeglie, Nick"),
        ("Driskell, Lori Minority (Democratic) Leader", "Driskell, Lori"),
        ("Perez, Daniel Speaker", "Perez, Daniel"),
        ("Salzman, Michelle", "Salzman, Michelle"),
    ],
)
def test_leadership_titles_printed_after_a_name_are_dropped(printed, clean):
    """The Senate roster prints leadership titles after the name; the 2026-11-25
    load stored 'Boyd, Jim President' as a winner's name."""
    from app.promises.winners import parse_csv

    rows = parse_csv(f'chamber,district,name\nsenate,20,"{printed}"\n')
    assert rows[0]["name"] == clean


# -- Name variants within a seat, and incumbency (2026-11-26) -----------------------------------------
# The six real cases from production: incumbents left unlinked, so they looked like new members.

def _winner_csv(name, office="Representative in the Legislature", district="54"):
    quoted = name.replace('"', '""')  # CSV: a quote inside a quoted field is doubled
    return f'Office,District,Candidate,Party\n{office},{district},"{quoted}",REP\n'


@pytest.mark.parametrize("winner,person", [
    ('Maggard, Randall Scott "Randy"', "Randy Maggard"),   # quoted nickname
    ('Yeager, Bradford Troy "Brad"', "Brad Yeager"),
    ("Fabricio, Tom", "Thomas Fabricio"),                  # first-name prefix
    ("Bernard, Mack", "Mackenson Bernard"),
    ("Rizo, Alex", "Alejandro Rizo"),                      # common nickname table
    ("Busatta, Demi", "Demi Busatta Cabrera"),             # compound surname
])
def test_name_variants_link_within_the_same_seat(db_session, winner, person):
    import_winners(db_session, parse_csv(_winner_csv(winner)), cycle=2026, source_url="u", certified=False, now=NOW)
    p = _person(db_session, person, "HD-54")
    result = link_people(db_session, cycle=2026)
    assert result["linked_variant"] == 1
    assert db_session.execute(select(ElectionWinner)).scalar_one().person_entity_id == p.id


@pytest.mark.parametrize("winner,person,district", [
    ("Smith, Jane", "John Smith", "HD-54"),      # same surname, different first name
    ("Fabricio, Tom", "Thomas Fabricio", "HD-55"),  # a variant, but another seat
    ("Rizo, Alex", "Alex Rodriguez", "HD-54"),   # same first name, different surname
])
def test_variants_never_link_across_names_or_seats(db_session, winner, person, district):
    import_winners(db_session, parse_csv(_winner_csv(winner)), cycle=2026, source_url="u", certified=False, now=NOW)
    _person(db_session, person, district)
    link_people(db_session, cycle=2026)
    assert db_session.execute(select(ElectionWinner)).scalar_one().person_entity_id is None


def test_two_variant_candidates_stay_unlinked(db_session):
    import_winners(db_session, parse_csv(_winner_csv("Fabricio, Tom")), cycle=2026, source_url="u", certified=False, now=NOW)
    _person(db_session, "Thomas Fabricio", "HD-54")
    _person(db_session, "Tommy Fabricio", "HD-54")
    assert link_people(db_session, cycle=2026)["ambiguous"] == 1


def test_mark_incumbents(db_session):
    csv = ("Office,District,Candidate,Party\n"
           "Representative in the Legislature,1,\"Old, Ann\",REP\n"      # re-elected
           "Representative in the Legislature,2,\"New, Bea\",DEM\n"      # seat had someone else
           "Representative in the Legislature,3,\"Fresh, Cy\",REP\n"     # no record of the seat
           "Representative in the Legislature,4,\"Late, Di\",REP\n")     # person created after the election
    import_winners(db_session, parse_csv(csv), cycle=2026, source_url="u", certified=False, now=NOW)
    before = datetime(2026, 1, 5, tzinfo=timezone.utc)
    for name, seat in (("Ann Old", "HD-1"), ("Zed Gone", "HD-2")):
        _person(db_session, name, seat).created_at = before
    _person(db_session, "Di Late", "HD-4")  # created now, i.e. after election day
    link_people(db_session, cycle=2026)
    assert mark_incumbents(db_session, cycle=2026) == {"incumbent": 1, "new": 1, "unknown": 2}
    got = {w.district: w.incumbent for w in db_session.execute(select(ElectionWinner)).scalars()}
    assert got == {1: True, 2: False, 3: None, 4: None}


def test_mark_incumbents_never_overwrites_the_source(db_session):
    import_winners(db_session, parse_csv(CSV), cycle=2026, source_url="u", certified=False, now=NOW)  # CSV says yes / no
    link_people(db_session, cycle=2026)
    mark_incumbents(db_session, cycle=2026)
    got = {w.district: w.incumbent for w in db_session.execute(select(ElectionWinner)).scalars()}
    assert got == {12: True, 45: False}
