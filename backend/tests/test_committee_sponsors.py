"""Committee sponsors (LegiScan `committee_sponsor: 1`) are flagged, so the
site can label them as committees rather than people. Shapes from HB 1389
in the 2026 Regular Session dataset (checked 2026-09-26)."""

from sqlalchemy import select

from app.models import Entity, Relationship
from app.pipeline.legiscan import mark_committee_sponsors

HB1389_SPONSORS = [
    {"people_id": 19345, "name": "Commerce Committee", "sponsor_type_id": 1, "committee_sponsor": 1,
     "committee_id": 3668, "role": "Rep"},
    {"people_id": 24994, "name": "Mike Redondo", "sponsor_type_id": 1, "committee_sponsor": 0,
     "committee_id": 0, "role": "Rep", "district": "HD-118", "party": "R"},
]


def _person(db_session, people_id: str, name: str, attributes: dict) -> Entity:
    entity = Entity(entity_type="person", name=name, jurisdiction_level="state", jurisdiction_name="FL",
                    external_ids={"legiscan_people_id": people_id}, attributes=attributes)
    db_session.add(entity)
    db_session.flush()
    return entity


def test_nightly_ingest_flags_committee_sponsors(monkeypatch, db_session):
    import app.pipeline.legiscan as legiscan_module

    class IngestClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_master_list(self, state):
            return [{"bill_id": 2044116, "number": "HB 1389", "change_hash": "eea7", "status": "4"}]

        def get_bill(self, bill_id):
            return {"bill_id": bill_id, "bill_number": "H1389", "title": "Affordable Housing", "status": 4,
                    "session": {"session_name": "2026 Regular Session"}, "sponsors": HB1389_SPONSORS, "votes": []}

    monkeypatch.setattr(legiscan_module, "LegiScanClient", IngestClient)
    legiscan_module.ingest_state_bills(db_session, state="FL")

    people = {e.name: e.attributes for e in db_session.execute(select(Entity).where(Entity.entity_type == "person")).scalars()}
    assert people["Commerce Committee"].get("committee") is True
    assert "committee" not in people["Mike Redondo"]


def test_mark_committee_sponsors_backfills_from_dataset_people(db_session):
    committee = _person(db_session, "19345", "Commerce Committee", {"role": "Rep"})
    rep = _person(db_session, "24994", "Mike Redondo", {"district": "HD-118"})

    assert mark_committee_sponsors(db_session, HB1389_SPONSORS) == 1
    assert mark_committee_sponsors(db_session, HB1389_SPONSORS) == 0  # idempotent
    assert committee.attributes["committee"] is True
    assert "committee" not in rep.attributes


def test_bill_detail_marks_committee_sponsors(client, db_session, bill_factory):
    bill = bill_factory()
    committee = _person(db_session, "19345", "Commerce Committee", {"committee": True})
    rep = _person(db_session, "24994", "Mike Redondo", {"district": "HD-118"})
    for person in (committee, rep):
        db_session.add(Relationship(from_entity_id=person.id, to_entity_id=bill.id, relationship_type="sponsor"))
        db_session.flush()
    db_session.commit()

    body = client.get(f"/bills/{bill.id}").json()

    assert {s["name"]: s["is_committee"] for s in body["sponsors"]} == {"Commerce Committee": True, "Mike Redondo": False}
    assert body["primary_sponsor"] == "Mike Redondo"
