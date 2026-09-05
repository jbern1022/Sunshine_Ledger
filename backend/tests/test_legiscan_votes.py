"""Tests for LegiScan vote syncing (app.pipeline.legiscan._sync_bill_votes).

DB-backed (Event/Relationship rows are real, per-test-transaction-rolled-back
via db_session), but the LegiScan API itself is stubbed -- the actual live
API shape was verified by hand against real endpoints before writing this
(getBill's votes array, getRollCall's per-legislator votes), not guessed.
"""

from datetime import date

from sqlalchemy import select

from app.models import Entity, Event, Relationship
from app.pipeline.legiscan import _sync_bill_votes


class FakeLegiScanClient:
    """Stands in for LegiScanClient.get_roll_call -- the one network call
    _sync_bill_votes makes when fetch_individual=True."""

    def __init__(self, roll_calls: dict[int, dict]):
        self.roll_calls = roll_calls
        self.calls: list[int] = []

    def get_roll_call(self, roll_call_id: int) -> dict:
        self.calls.append(roll_call_id)
        return self.roll_calls[roll_call_id]


def make_bill_entity(db_session) -> Entity:
    entity = Entity(
        entity_type="bill",
        name="Test Bill",
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_id": "999"},
        attributes={},
    )
    db_session.add(entity)
    db_session.flush()
    return entity


ROLL_CALL_SUMMARY = {
    "roll_call_id": 1644238,
    "date": "2026-02-25",
    "desc": "House: Third Reading RCS#549",
    "yea": 82,
    "nay": 30,
    "nv": 5,
    "absent": 0,
    "total": 117,
    "passed": 1,
    "chamber": "H",
    "url": "https://legiscan.com/FL/rollcall/H0033/id/1644238",
}

PEOPLE_BY_ID = {
    "19426": {"name": "Jane Smith", "district": "HD-010", "role": "Rep", "party": "D"},
    "19490": {"name": "John Doe", "district": "HD-020", "role": "Rep", "party": "R"},
}

ROLL_CALL_DETAIL = {
    "roll_call_id": 1644238,
    "votes": [
        {"people_id": 19426, "vote_id": 1, "vote_text": "Yea"},
        {"people_id": 19490, "vote_id": 2, "vote_text": "Nay"},
        {"people_id": 99999, "vote_id": 1, "vote_text": "Yea"},  # not in the roster
    ],
}


def test_stores_a_vote_event_with_the_real_getbill_field_shape(db_session):
    entity = make_bill_entity(db_session)
    client = FakeLegiScanClient({1644238: ROLL_CALL_DETAIL})

    fetched = _sync_bill_votes(
        db_session,
        bill_entity=entity,
        votes=[ROLL_CALL_SUMMARY],
        client=client,
        state="FL",
        people_by_id=PEOPLE_BY_ID,
        fetch_individual=False,
    )
    db_session.commit()

    assert fetched == 0  # fetch_individual=False -- no getRollCall call
    assert client.calls == []

    event = db_session.execute(select(Event).where(Event.entity_id == entity.id)).scalar_one()
    assert event.event_type == "vote"
    assert event.event_date == date(2026, 2, 25)
    assert event.title == "House: Third Reading RCS#549"
    assert event.attributes["roll_call_id"] == "1644238"
    assert event.attributes["yea"] == 82
    assert event.attributes["nay"] == 30
    assert event.attributes["passed"] is True
    assert event.source_id is not None


def test_fetches_and_stores_individual_votes_when_requested(db_session):
    entity = make_bill_entity(db_session)
    client = FakeLegiScanClient({1644238: ROLL_CALL_DETAIL})

    fetched = _sync_bill_votes(
        db_session,
        bill_entity=entity,
        votes=[ROLL_CALL_SUMMARY],
        client=client,
        state="FL",
        people_by_id=PEOPLE_BY_ID,
        fetch_individual=True,
    )
    db_session.commit()

    assert fetched == 1
    assert client.calls == [1644238]

    votes = db_session.execute(
        select(Relationship).where(Relationship.relationship_type == "voted")
    ).scalars().all()
    # Only 2 of the 3 roll-call entries are in the roster; the unknown
    # people_id (99999) must be skipped rather than recorded under no name.
    assert len(votes) == 2
    by_vote = {v.attributes["vote"] for v in votes}
    assert by_vote == {"Yea", "Nay"}

    jane = db_session.execute(
        select(Entity).where(Entity.external_ids["legiscan_people_id"].as_string() == "19426")
    ).scalar_one()
    assert jane.name == "Jane Smith"


def test_reuses_an_existing_person_entity_instead_of_duplicating(db_session):
    entity = make_bill_entity(db_session)
    existing = Entity(
        entity_type="person",
        name="Jane Smith",
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_people_id": "19426"},
        attributes={"district": "HD-010"},
    )
    db_session.add(existing)
    db_session.flush()

    client = FakeLegiScanClient({1644238: ROLL_CALL_DETAIL})
    _sync_bill_votes(
        db_session,
        bill_entity=entity,
        votes=[ROLL_CALL_SUMMARY],
        client=client,
        state="FL",
        people_by_id=PEOPLE_BY_ID,
        fetch_individual=True,
    )
    db_session.commit()

    people = db_session.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.external_ids["legiscan_people_id"].as_string() == "19426",
        )
    ).scalars().all()
    assert len(people) == 1
    assert people[0].id == existing.id


def test_is_idempotent_and_does_not_re_spend_api_quota(db_session):
    entity = make_bill_entity(db_session)
    client = FakeLegiScanClient({1644238: ROLL_CALL_DETAIL})

    _sync_bill_votes(
        db_session, bill_entity=entity, votes=[ROLL_CALL_SUMMARY], client=client,
        state="FL", people_by_id=PEOPLE_BY_ID, fetch_individual=True,
    )
    db_session.commit()

    second_fetch_count = _sync_bill_votes(
        db_session, bill_entity=entity, votes=[ROLL_CALL_SUMMARY], client=client,
        state="FL", people_by_id=PEOPLE_BY_ID, fetch_individual=True,
    )
    db_session.commit()

    assert second_fetch_count == 0
    assert client.calls == [1644238]  # only the first call actually happened

    events = db_session.execute(select(Event).where(Event.entity_id == entity.id)).scalars().all()
    votes = db_session.execute(
        select(Relationship).where(Relationship.relationship_type == "voted")
    ).scalars().all()
    assert len(events) == 1
    assert len(votes) == 2


def test_skips_a_roll_call_with_no_parseable_date_without_wasting_a_roll_call_fetch(db_session):
    entity = make_bill_entity(db_session)
    client = FakeLegiScanClient({1644238: ROLL_CALL_DETAIL})
    bad_summary = {**ROLL_CALL_SUMMARY, "date": None}

    fetched = _sync_bill_votes(
        db_session, bill_entity=entity, votes=[bad_summary], client=client,
        state="FL", people_by_id=PEOPLE_BY_ID, fetch_individual=True,
    )
    db_session.commit()

    assert fetched == 0
    assert client.calls == []
    assert db_session.execute(select(Event).where(Event.entity_id == entity.id)).first() is None


def test_ignores_a_vote_row_missing_the_roll_call_id(db_session):
    entity = make_bill_entity(db_session)
    client = FakeLegiScanClient({})

    fetched = _sync_bill_votes(
        db_session, bill_entity=entity, votes=[{"date": "2026-02-25", "desc": "x"}], client=client,
        state="FL", people_by_id=PEOPLE_BY_ID, fetch_individual=True,
    )

    assert fetched == 0
    assert db_session.execute(select(Event).where(Event.entity_id == entity.id)).first() is None
