import json
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.federal.roster import HOUSE_SEATS, confirm_same_person, florida_members, import_roster
from app.models import Entity, OfficeTenure

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "congress_legislators_sample.json").read_text())
TODAY = date(2026, 11, 10)


def test_only_florida_members_are_taken():
    fl = florida_members(SAMPLE)
    assert len(fl) == 2 and all(m["terms"][-1]["state"] == "FL" for m in fl)


def test_import_creates_people_keyed_on_bioguide_with_one_tenure_per_term(db_session):
    out = import_roster(db_session, SAMPLE, today=TODAY)
    assert out["members"] == 2 and out["people_created"] == 2
    bilirakis = db_session.execute(
        select(Entity).where(Entity.external_ids["bioguide_id"].as_string() == "B001257")
    ).scalar_one()
    assert bilirakis.jurisdiction_level == "federal" and bilirakis.attributes["chamber"] == "us_house"
    tenures = db_session.execute(
        select(OfficeTenure).where(OfficeTenure.person_entity_id == bilirakis.id).order_by(OfficeTenure.start_date)
    ).scalars().all()
    assert len(tenures) >= 10
    assert tenures[0].start_date.year == 2007 and tenures[0].district == 9
    assert {t.district for t in tenures} == {9, 12}  # he changed districts in 2013
    current, previous = tenures[-1], tenures[0]
    assert current.end_date is None and current.scheduled_end is not None  # sitting: open-ended
    assert previous.end_date == previous.scheduled_end  # a finished term is closed


def test_import_is_idempotent(db_session):
    import_roster(db_session, SAMPLE, today=TODAY)
    n = db_session.execute(select(OfficeTenure)).scalars().all().__len__()
    out = import_roster(db_session, SAMPLE, today=TODAY)
    assert out["people_created"] == 0 and out["tenures_added"] == 0
    assert db_session.execute(select(OfficeTenure)).scalars().all().__len__() == n


def test_senate_tenures_have_no_district(db_session):
    import_roster(db_session, SAMPLE, today=TODAY)
    sen = db_session.execute(select(OfficeTenure).where(OfficeTenure.office_type == "us_senate")).scalars().all()
    assert sen and all(t.district is None and t.senate_class in (1, 2, 3) for t in sen)


def test_vacant_districts_are_reported(db_session):
    out = import_roster(db_session, SAMPLE, today=TODAY)
    assert len(out["vacant_districts"]) == HOUSE_SEATS - 1  # the sample holds one House member


def test_same_name_state_legislator_is_a_candidate_never_linked(db_session):
    state = Entity(entity_type="person", name="Gus Bilirakis", jurisdiction_level="state", jurisdiction_name="FL",
                   external_ids={"legiscan_people_id": "1"}, attributes={"district": "HD-45"})
    db_session.add(state)
    db_session.flush()
    out = import_roster(db_session, SAMPLE, today=TODAY)
    assert out["possible_state_matches"][0]["candidates"][0]["id"] == str(state.id)
    fed = db_session.execute(select(Entity).where(Entity.external_ids["bioguide_id"].as_string() == "B001257")).scalar_one()
    assert fed.id != state.id and "same_person_as" not in (fed.attributes or {})
    # a person confirms it; only then is it recorded, on both
    confirm_same_person(db_session, "B001257", state.id)
    assert fed.attributes["same_person_as"] == str(state.id) and state.attributes["same_person_as"] == str(fed.id)
    again = import_roster(db_session, SAMPLE, today=TODAY)
    assert again["possible_state_matches"] == []  # already resolved
    assert fed.attributes["same_person_as"] == str(state.id)  # a refresh keeps it
