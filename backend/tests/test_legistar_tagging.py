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


def test_ingest_fort_lauderdale_is_a_registry_entry_only(monkeypatch, db_session):
    monkeypatch.setattr(legistar_module, "LegistarClient", FakeLegistarClient)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="fortlauderdale", limit=1)

    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    assert entity.jurisdiction_name == "Fort Lauderdale"
    assert entity.external_ids["legistar_client"] == "fortlauderdale"
    assert entity.bill.geo_scope_names == ["Broward County"]
    from app.models import SourceCheck

    assert db_session.execute(select(SourceCheck).where(SourceCheck.source_key == "legistar_fortlauderdale")).scalar_one()


def test_ingest_a_county_client_stores_county_level(monkeypatch, db_session):
    from app.models import Source

    monkeypatch.setattr(legistar_module, "LegistarClient", FakeLegistarClient)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="broward", limit=1)

    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    assert entity.jurisdiction_level == "county"
    assert entity.jurisdiction_name == "Broward County"
    assert entity.bill.geo_scope_type == "county"
    assert entity.bill.geo_scope_names == ["Broward County"]
    assert db_session.execute(select(Source)).scalar_one().publisher == "Broward County Commission (Legistar)"


class FakeClientWithBodySponsors(FakeLegistarClient):
    def get_sponsors(self, matter_id):
        return [
            {"MatterSponsorName": "City Commission Regular Meeting", "MatterSponsorBodyId": 138, "MatterSponsorNameId": None},
            {"MatterSponsorName": "Jane Councilmember", "MatterSponsorBodyId": None, "MatterSponsorNameId": 7},
        ]


def _sponsors(db_session):
    return {p.name: p for p in db_session.execute(select(Entity).where(Entity.entity_type == "person")).scalars()}


def test_fort_lauderdale_body_sponsors_are_stored_as_committees_not_people(monkeypatch, db_session):
    monkeypatch.setattr(legistar_module, "LegistarClient", FakeClientWithBodySponsors)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="fortlauderdale", limit=1)

    people = _sponsors(db_session)
    assert people["City Commission Regular Meeting"].attributes == {"committee": True}
    assert people["Jane Councilmember"].attributes == {}


def test_other_clients_keep_body_sponsors_as_before(monkeypatch, db_session):
    # Jacksonville lists offices ("Mayor", "President") as body sponsors; those
    # are not committees, so the option is per client.
    monkeypatch.setattr(legistar_module, "LegistarClient", FakeClientWithBodySponsors)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="jaxcityc", limit=1)

    assert _sponsors(db_session)["City Commission Regular Meeting"].attributes == {}
