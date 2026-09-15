"""Integration test for the topic-tagging wiring inside
app.pipeline.legiscan.ingest_state_bills. DB-backed, network stubbed via a
fake LegiScanClient (monkeypatched in) -- same style as test_legiscan_votes.py.
"""

from sqlalchemy import select

from app.models import BillTag, Entity, Tag
from app.models.tag import GOVERNANCE_SLUG
import app.pipeline.legiscan as legiscan_module


class FakeLegiScanClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_master_list(self, state):
        return [{"bill_id": 1, "number": "HB 1", "title": "A Bill", "url": "https://example.com", "status": "1"}]

    def get_bill(self, bill_id):
        return {
            "bill_id": bill_id,
            "bill_number": "HB 1",
            "title": "A Bill About Housing",
            "status": 1,
            "session": {"session_name": "2026 Regular Session"},
            "sponsors": [],
            "votes": [],
            "subjects": [{"subject_id": 1, "subject_name": "AFFORDABLE HOUSING"}],
        }


def test_ingest_state_bills_tags_from_subjects(monkeypatch, db_session):
    housing = Tag(slug="housing", label="Housing", active=True)
    governance = Tag(slug=GOVERNANCE_SLUG, label="Governance", active=True)
    db_session.add_all([housing, governance])
    db_session.commit()
    from app.models import SubjectMapping

    db_session.add(SubjectMapping(raw_subject="AFFORDABLE HOUSING", tag_id=housing.id))
    db_session.commit()

    monkeypatch.setattr(legiscan_module, "LegiScanClient", FakeLegiScanClient)

    legiscan_module.ingest_state_bills(db_session, state="FL", sync_votes=False)

    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    tags = db_session.execute(select(BillTag).where(BillTag.bill_entity_id == entity.id)).scalars().all()
    assert len(tags) == 1
    assert tags[0].tag_id == housing.id
    assert tags[0].tag_source == "legiscan"
    assert tags[0].raw_subject == "AFFORDABLE HOUSING"


def test_ingest_state_bills_survives_missing_tag_seed_data(monkeypatch, db_session, caplog):
    """No Tag rows seeded at all -- assign_tags_for_bill raises RuntimeError
    looking up Governance, and ingestion must keep going rather than losing
    the bill/sponsor/vote data it already wrote for this bill."""
    monkeypatch.setattr(legiscan_module, "LegiScanClient", FakeLegiScanClient)

    written = legiscan_module.ingest_state_bills(db_session, state="FL", sync_votes=False)

    assert len(written) == 1
    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    assert entity.bill.bill_number == "HB 1"
    assert db_session.execute(select(BillTag)).first() is None
