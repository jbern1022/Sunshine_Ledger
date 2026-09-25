"""DatasetClient: sync_state_bill_history fed from a LegiScan session
dataset zip instead of per-bill API calls. File layout and JSON shapes as
in the real FL 2026 datasets (checked 2026-09-25)."""

import io
import json
import zipfile

from sqlalchemy import select

from app.models import Entity, Event, Relationship
from app.pipeline.legiscan import sync_state_bill_history
from app.pipeline.legiscan_dataset import DatasetClient

ROOT = "FL/2026-2026_Regular_Session"

BILL = {
    "bill_id": 2044116,
    "session": {"session_id": 2220, "session_name": "2026 Regular Session"},
    "change_hash": "eea7",
    "history": [{"date": "2026-01-09", "action": "Filed", "chamber": "H", "importance": 1}],
    "amendments": [{"amendment_id": 680391, "adopted": 1, "chamber": "H", "date": "2026-03-12",
                    "title": "House Floor Amendment #680391"}],
    "votes": [{"roll_call_id": 1700001, "date": "2026-03-04", "desc": "House: Third Reading RCS#662",
               "yea": 76, "nay": 29, "nv": 0, "absent": 0, "total": 105, "passed": 1, "chamber": "H"}],
    "supplements": [],
}
ROLL_CALL = {"roll_call_id": 1700001, "votes": [{"people_id": 1622, "vote_id": 1, "vote_text": "Yea"}]}
PERSON = {"people_id": 1622, "name": "Mike Redondo", "district": "HD-118", "role": "Rep", "party": "R"}


def dataset_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{ROOT}/bill/HB1389.json", json.dumps({"bill": BILL}))
        z.writestr(f"{ROOT}/vote/1700001.json", json.dumps({"roll_call": ROLL_CALL}))
        z.writestr(f"{ROOT}/people/Mike_Redondo.json", json.dumps({"person": PERSON}))
        z.writestr(f"{ROOT}/README.md", "not json")
    return buf.getvalue()


class RecordingApi:
    """A real-client stand-in that records every call the dataset didn't cover."""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def get_bill(self, bill_id):
        self.calls.append(("getBill", bill_id))
        return {"bill_id": bill_id, "history": [], "amendments": [], "votes": [], "supplements": []}

    def get_roll_call(self, roll_call_id):
        self.calls.append(("getRollCall", roll_call_id))
        return {"roll_call_id": roll_call_id, "votes": []}


def make_state_bill(db_session, legiscan_id: str) -> Entity:
    entity = Entity(entity_type="bill", name="Affordable Housing", jurisdiction_level="state",
                    jurisdiction_name="FL",
                    external_ids={"legiscan_id": legiscan_id, "legiscan_change_hash": "eea7"}, attributes={})
    db_session.add(entity)
    db_session.flush()
    return entity


def test_parses_bills_roll_calls_people_and_sessions():
    client = DatasetClient(dataset_zip(), fallback=RecordingApi())

    assert list(client.bills) == [2044116]
    assert list(client.roll_calls) == [1700001]
    assert client.people == [PERSON]
    assert client.get_sessions("FL") == [{"session_id": 2220}]


def test_history_backfill_from_dataset_makes_no_api_calls(db_session):
    bill = make_state_bill(db_session, "2044116")
    api = RecordingApi()
    client = DatasetClient(dataset_zip(), fallback=api)

    processed, roll_calls = sync_state_bill_history(db_session, state="FL", client=client)

    assert (processed, roll_calls) == (1, 1)
    assert api.calls == []
    assert client.fallback_calls == 0
    types = [e.event_type for e in db_session.execute(select(Event).where(Event.entity_id == bill.id)).scalars()]
    assert sorted(types) == ["AMENDED", "action", "vote"]
    voted = db_session.execute(select(Relationship).where(Relationship.relationship_type == "voted")).scalar_one()
    assert voted.attributes["vote"] == "Yea"


def test_bill_missing_from_the_dataset_falls_back_to_the_api(db_session):
    make_state_bill(db_session, "999")
    api = RecordingApi()
    client = DatasetClient(dataset_zip(), fallback=api)

    sync_state_bill_history(db_session, state="FL", client=client)

    assert api.calls == [("getBill", 999)]
    assert client.fallback_calls == 1


def test_ingest_session_dataset_creates_bills_with_everything_from_the_zip(monkeypatch, db_session):
    import app.pipeline.legiscan as legiscan_module
    import app.pipeline.legiscan_dataset as dataset_module
    from app.models import Bill

    special = {**BILL, "bill_id": 2100001, "bill_number": "H0001B", "title": "Property Tax Relief",
               "status": 4, "session": {"session_id": 2259, "session_name": "2026 Fourth Special Session"},
               "sponsors": [{"people_id": 1622, "name": "Mike Redondo", "sponsor_type_id": 1}]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("FL/2026-2026_4th_Special_Session/bill/H0001B.json", json.dumps({"bill": special}))
        z.writestr("FL/2026-2026_4th_Special_Session/vote/1700001.json", json.dumps({"roll_call": ROLL_CALL}))
        z.writestr("FL/2026-2026_4th_Special_Session/people/Mike_Redondo.json", json.dumps({"person": PERSON}))
    api = RecordingApi()
    monkeypatch.setattr(legiscan_module, "LegiScanClient", lambda *a, **k: api)
    monkeypatch.setattr(dataset_module, "fetch_session_dataset", lambda client, state, name: buf.getvalue())

    written = legiscan_module.ingest_session_dataset(db_session, session_name="2026 Fourth Special Session", state="FL")

    assert len(written) == 1
    bill = db_session.execute(select(Bill).where(Bill.bill_number == "H0001B")).scalar_one()
    assert bill.session == "2026 Fourth Special Session"
    assert bill.introduced_date is not None
    types = sorted(e.event_type for e in db_session.execute(select(Event).where(Event.entity_id == bill.entity_id)).scalars())
    assert types == ["AMENDED", "action", "vote"]
    assert api.calls == []  # everything came from the dataset
