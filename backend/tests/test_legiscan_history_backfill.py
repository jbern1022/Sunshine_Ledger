"""Tests for sync_state_bill_history: the one-off amendments + votes backfill
for state bills ingest_state_bills never revisits. LegiScan is stubbed; the
getBill shape matches HB 1389 as fetched live on 2026-09-25 (3 amendments,
7 roll calls)."""

from sqlalchemy import select

from app.models import Entity, Event
from app.pipeline.legiscan import sync_bill_actions, sync_state_bill_history


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


HISTORY = [
    {"date": "2026-01-09", "action": "Filed", "chamber": "H", "chamber_id": 27, "importance": 1},
    {"date": "2026-01-13", "action": "1st Reading (Original Filed Version)", "chamber": "H",
     "chamber_id": 27, "importance": 0},
    {"date": "2026-01-15", "action": "Referred to Housing, Agriculture & Tourism Subcommittee",
     "chamber": "H", "chamber_id": 27, "importance": 1},
    {"date": "2026-06-26", "action": "Approved by Governor", "chamber": "", "chamber_id": 0,
     "importance": 1},
]

HB1389 = {
    "history": HISTORY,
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
    assert len(events(db_session, bill, "action")) == 4
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


def test_sync_bill_actions_maps_chambers_and_keeps_order(db_session):
    bill = make_state_bill(db_session, "2044116")

    assert sync_bill_actions(db_session, bill_entity=bill, history=HISTORY) == 4

    actions = sorted(events(db_session, bill, "action"), key=lambda e: e.attributes["seq"])
    assert [a.title for a in actions] == [
        "Filed",
        "1st Reading (Original Filed Version)",
        "Referred to Housing, Agriculture & Tourism Subcommittee",
        "Approved by Governor",
    ]
    assert [a.attributes["chamber"] for a in actions] == ["House", "House", "House", None]
    assert [a.attributes["importance"] for a in actions] == [True, False, True, True]


def test_sync_bill_actions_is_idempotent_and_appends_new_entries(db_session):
    bill = make_state_bill(db_session, "2044116")
    sync_bill_actions(db_session, bill_entity=bill, history=HISTORY[:2])

    assert sync_bill_actions(db_session, bill_entity=bill, history=HISTORY[:2]) == 0
    assert sync_bill_actions(db_session, bill_entity=bill, history=HISTORY) == 2
    assert len(events(db_session, bill, "action")) == 4


def test_sync_bill_actions_keeps_a_genuinely_repeated_action(db_session):
    bill = make_state_bill(db_session, "2044116")
    referral = {"date": "2026-01-15", "action": "Referred to Rules", "chamber": "S", "importance": 1}

    assert sync_bill_actions(db_session, bill_entity=bill, history=[referral, referral]) == 2
    assert sync_bill_actions(db_session, bill_entity=bill, history=[referral, referral]) == 0


def test_sync_bill_actions_skips_entries_without_date_or_text(db_session):
    bill = make_state_bill(db_session, "2044116")
    history = [{"date": "", "action": "Filed"}, {"date": "2026-01-09", "action": "  "}]

    assert sync_bill_actions(db_session, bill_entity=bill, history=history) == 0


def test_nightly_ingest_stores_history_and_marks_the_bill_synced(monkeypatch, db_session):
    import app.pipeline.legiscan as legiscan_module

    class IngestClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_master_list(self, state):
            return [{"bill_id": 2044116, "number": "HB 1389", "change_hash": "eea7", "status": "4"}]

        def get_bill(self, bill_id):
            return {"bill_id": bill_id, "bill_number": "H1389", "title": "Affordable Housing", "status": 4,
                    "session": {"session_name": "2026 Regular Session"}, "sponsors": [], "votes": [],
                    "history": HISTORY, "amendments": HB1389["amendments"]}

    monkeypatch.setattr(legiscan_module, "LegiScanClient", IngestClient)

    legiscan_module.ingest_state_bills(db_session, state="FL")

    bill = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    assert len(events(db_session, bill, "action")) == 4
    assert len(events(db_session, bill, "AMENDED")) == 3
    assert bill.external_ids["legiscan_history_hash"] == "eea7"


def test_backfill_stores_new_staff_analyses_from_the_same_getbill(monkeypatch, db_session):
    import base64

    import app.pipeline.staff_analysis as staff_module
    from app.models import StaffAnalysis

    monkeypatch.setattr(staff_module, "extract_analysis_pdf_text", lambda raw: "Analysis text")
    bill = make_state_bill(db_session, "2044116")
    db_session.add(StaffAnalysis(entity_id=bill.id, legiscan_supplement_id=500, source_url="https://x", text="old"))
    db_session.flush()
    supplements = [
        {"supplement_id": 500, "title": "Analysis", "description": "Housing Subcommittee"},  # stored already
        {"supplement_id": 501, "title": "Analysis", "description": "Commerce Committee", "date": "2026-02-24",
         "state_link": "https://flsenate.gov/a.pdf"},
        {"supplement_id": 502, "title": "Vote Record", "description": "not an analysis"},
    ]
    client = FakeLegiScanClient({2044116: {**HB1389, "supplements": supplements}})
    fetched_docs = []
    client.get_supplement = lambda sid: fetched_docs.append(sid) or {
        "mime": "application/pdf", "doc": base64.b64encode(b"%PDF").decode()
    }

    sync_state_bill_history(db_session, state="FL", client=client)

    assert fetched_docs == [501]
    stored = db_session.execute(
        select(StaffAnalysis).where(StaffAnalysis.legiscan_supplement_id == 501)
    ).scalar_one()
    assert stored.committee == "Commerce Committee"
    assert stored.text == "Analysis text"
    assert len(events(db_session, bill, "AMENDED")) == 3  # committed before the analysis step
