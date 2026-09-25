"""Tests for sync_state_bill_history: the one-off amendments + votes backfill
for state bills ingest_state_bills never revisits. LegiScan is stubbed; the
getBill shape matches HB 1389 as fetched live on 2026-09-25 (3 amendments,
7 roll calls)."""

from sqlalchemy import select

from app.models import Entity, Event
from app.pipeline.legiscan import sync_state_bill_history


class FakeLegiScanClient:
    def __init__(self, bills: dict[int, dict]):
        self.bills = bills
        self.get_bill_calls: list[int] = []
        self.roll_call_calls: list[int] = []

    def get_bill(self, bill_id: int) -> dict:
        self.get_bill_calls.append(bill_id)
        return self.bills[bill_id]

    def get_roll_call(self, roll_call_id: int) -> dict:
        self.roll_call_calls.append(roll_call_id)
        return {"roll_call_id": roll_call_id, "votes": [{"people_id": 1, "vote_text": "Yea"}]}

    def get_sessions(self, state: str) -> list[dict]:
        return [{"session_id": 2200}]

    def get_session_people(self, session_id: int) -> list[dict]:
        return [{"people_id": 1, "name": "Mike Redondo", "district": "HD-118", "role": "Rep", "party": "R"}]


HB1389 = {
    "amendments": [
        {"amendment_id": 208403, "adopted": 0, "chamber": "H", "date": "2026-02-10",
         "title": "House Committee Amendment #208403", "description": ""},
        {"amendment_id": 668106, "adopted": 0, "chamber": "S", "date": "2026-03-06",
         "title": "Senate Floor Amendment (Delete All) #668106", "description": ""},
        {"amendment_id": 680391, "adopted": 1, "chamber": "H", "date": "2026-03-12",
         "title": "House Floor Amendment #680391 to Amendment (668106)", "description": ""},
    ],
    "votes": [
        {"roll_call_id": 1700001, "date": "2026-03-04", "desc": "House: Third Reading RCS#662",
         "yea": 76, "nay": 29, "nv": 0, "absent": 0, "total": 105, "passed": 1, "chamber": "H"},
        {"roll_call_id": 1700002, "date": "2026-03-13", "desc": "Senate: Third Reading RCS#3",
         "yea": 35, "nay": 0, "nv": 0, "absent": 0, "total": 35, "passed": 1, "chamber": "S"},
    ],
}


def make_state_bill(db_session, legiscan_id: str, change_hash: str = "abc") -> Entity:
    entity = Entity(
        entity_type="bill",
        name="Affordable Housing",
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_id": legiscan_id, "legiscan_change_hash": change_hash},
        attributes={},
    )
    db_session.add(entity)
    db_session.flush()
    return entity


def events(db_session, entity: Entity, event_type: str) -> list[Event]:
    return db_session.execute(
        select(Event).where(Event.entity_id == entity.id, Event.event_type == event_type)
    ).scalars().all()


def test_stores_amendments_and_votes_from_one_getbill_call(db_session):
    bill = make_state_bill(db_session, "2044116")
    client = FakeLegiScanClient({2044116: HB1389})

    processed, roll_calls = sync_state_bill_history(db_session, state="FL", client=client)

    assert (processed, roll_calls) == (1, 2)
    assert client.get_bill_calls == [2044116]
    amendments = events(db_session, bill, "AMENDED")
    assert {a.attributes["amendment_id"] for a in amendments} == {208403, 668106, 680391}
    assert [a.attributes["adopted"] for a in sorted(amendments, key=lambda a: a.attributes["amendment_id"])] == [
        False, False, True,
    ]
    assert len(events(db_session, bill, "vote")) == 2
    assert bill.external_ids["legiscan_history_hash"] == "abc"


def test_rerun_skips_bills_already_synced_at_their_current_hash(db_session):
    make_state_bill(db_session, "2044116")
    sync_state_bill_history(db_session, state="FL", client=FakeLegiScanClient({2044116: HB1389}))

    client = FakeLegiScanClient({2044116: HB1389})
    processed, roll_calls = sync_state_bill_history(db_session, state="FL", client=client)

    assert (processed, roll_calls) == (0, 0)
    assert client.get_bill_calls == []


def test_resyncs_a_bill_whose_change_hash_moved_on_without_duplicating(db_session):
    bill = make_state_bill(db_session, "2044116")
    sync_state_bill_history(db_session, state="FL", client=FakeLegiScanClient({2044116: HB1389}))
    bill.external_ids = {**bill.external_ids, "legiscan_change_hash": "def"}
    db_session.flush()

    client = FakeLegiScanClient({2044116: HB1389})
    processed, roll_calls = sync_state_bill_history(db_session, state="FL", client=client)

    assert (processed, roll_calls) == (1, 0)  # roll calls already recorded: no getRollCall
    assert len(events(db_session, bill, "AMENDED")) == 3
    assert bill.external_ids["legiscan_history_hash"] == "def"


def test_limit_caps_the_bills_fetched(db_session):
    make_state_bill(db_session, "1")
    make_state_bill(db_session, "2")
    client = FakeLegiScanClient({1: {"amendments": [], "votes": []}, 2: {"amendments": [], "votes": []}})

    processed, _ = sync_state_bill_history(db_session, state="FL", limit=1, client=client)

    assert processed == 1
    assert len(client.get_bill_calls) == 1
