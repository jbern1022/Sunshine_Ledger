"""Integration test for the topic-tagging wiring inside
app.pipeline.legistar.ingest_local_bills. DB-backed, network stubbed via a
fake LegistarClient and a fake Ollama client."""

from sqlalchemy import select

from app.models import BillTag, Entity, Tag
import app.pipeline.legistar as legistar_module
import app.pipeline.topic_tagging_ollama as topic_tagging_ollama_module
from tests.test_topic_tagging_ollama import FakeOllamaClient


class FakeLegistarClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_matters(self, *, top):
        return [
            {
                "MatterId": 1,
                "MatterName": None,
                "MatterTitle": "An ordinance about affordable housing density bonuses",
                "MatterFile": "MIA-2026-001",
                "MatterAgendaDate": "2026-01-15",
                "MatterIntroDate": "2026-01-15",
                "MatterPassedDate": None,
                "MatterBodyName": "City Commission",
                "MatterStatusName": "Introduced",
            }
        ]

    def get_sponsors(self, matter_id):
        return []


def test_ingest_local_bills_tags_via_ollama(monkeypatch, db_session):
    housing = Tag(slug="housing", label="Housing", active=True)
    db_session.add(housing)
    db_session.commit()

    monkeypatch.setattr(legistar_module, "LegistarClient", FakeLegistarClient)
    fake_ollama = FakeOllamaClient('["housing"]')
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: fake_ollama)

    legistar_module.ingest_local_bills(db_session, client_name="miamifl", limit=1)

    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    tags = db_session.execute(select(BillTag).where(BillTag.bill_entity_id == entity.id)).scalars().all()
    assert len(tags) == 1
    assert tags[0].tag_id == housing.id
    assert tags[0].tag_source == "ollama"
    assert len(fake_ollama.calls) == 1
