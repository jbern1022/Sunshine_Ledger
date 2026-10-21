"""Integration test for the topic-tagging wiring inside
app.pipeline.legistar.ingest_local_bills. DB-backed, network stubbed via a
fake LegistarClient and a fake Ollama client."""

import pytest
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


def test_derived_item_type_reads_broward_titles():
    from app.pipeline.legistar import derived_item_type

    assert derived_item_type("MOTION TO ENACT Ordinance, the title of which is as follows:\n\nAN ORDINANCE OF THE BOARD") == "Ordinance"
    assert derived_item_type("MOTION TO ADOPT Resolution directing the County Administrator to publish Notice") == "Resolution"
    assert derived_item_type("MOTION TO APPROVE travel outside the continental United States for two County employees") == "Motion"
    assert derived_item_type("COUNTY ADMINISTRATOR'S REPORT") == "Motion"
    # A direction to draft one is not the instrument itself.
    assert derived_item_type("MOTION TO DIRECT County Attorney\u2019s Office to draft an Ordinance establishing a moratorium") == "Motion"
    assert derived_item_type("MOTION TO DIRECT County Attorney\u2019s Office to draft a Resolution amending the Code") == "Motion"
    assert derived_item_type("A. MOTION TO ADOPT Resolution amending the Administrative Code") == "Resolution"
    assert derived_item_type("MOTION TO DIRECT staff " + "x " * 100 + "pursuant to Resolution 5") == "Motion"


def test_broward_items_get_a_derived_kind_and_keep_the_source_type(monkeypatch, db_session):
    from app.pipeline.item_kind import backfill_item_types, item_kind

    class Fake(FakeLegistarClient):
        def get_matters(self, *, top):
            return [{**super().get_matters(top=top)[0], "MatterTypeName": "Consent Item",
                     "MatterTitle": "MOTION TO ENACT Ordinance, the title of which is as follows: AN ORDINANCE"}]

    monkeypatch.setattr(legistar_module, "LegistarClient", Fake)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="broward", limit=1)

    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    assert entity.attributes["item_type"] == "Ordinance"
    assert entity.attributes["source_item_type"] == "Consent Item"
    assert item_kind(entity.attributes["item_type"]) == "legislation"
    # The backfill, which copies the source's own type, must not overwrite it.
    assert backfill_item_types(db_session) == 0
    assert entity.attributes["item_type"] == "Ordinance"


def test_legistar_text_backfill_marks_no_text_and_skips_it_until_recheck(monkeypatch, db_session, bill_factory):
    from datetime import date, timedelta

    import app.pipeline.bill_text as bt

    e = bill_factory(bill_number="26-1")
    e.external_ids = {"legistar_matter_id": "1", "legistar_client": "fortlauderdale"}
    e.bill.source_system = "legistar"
    db_session.commit()
    calls = []
    monkeypatch.setattr(bt, "_legistar_text_for", lambda entity: calls.append(1) or None)

    assert bt.backfill_legistar_texts(db_session) == (0, 1)
    assert e.attributes["text_checked_at"] == date.today().isoformat()
    assert bt.backfill_legistar_texts(db_session) == (0, 0)  # not retried tonight
    assert len(calls) == 1

    e.attributes = {**e.attributes, "text_checked_at": (date.today() - timedelta(days=15)).isoformat()}
    db_session.commit()
    bt.backfill_legistar_texts(db_session)
    assert len(calls) == 2  # due for a re-check


@pytest.mark.parametrize(
    ("client", "jurisdiction", "county", "committee_sponsors"),
    [
        ("coralgables", "Coral Gables", "Miami-Dade County", False),
        ("keywest", "Key West", "Monroe County", False),
        ("delraybeach", "Delray Beach", "Palm Beach County", True),
        ("hollywoodfl", "Hollywood", "Broward County", False),
        ("clearwater", "Clearwater", "Pinellas County", False),
        ("miramar", "Miramar", "Broward County", False),
        ("doral", "Doral", "Miami-Dade County", True),
        ("hallandalebeach", "Hallandale Beach", "Broward County", False),
        ("coconutcreek", "Coconut Creek", "Broward County", True),
        ("pinecrest", "Pinecrest", "Miami-Dade County", False),
        ("margatefl", "Margate", "Broward County", False),
        ("deltona", "Deltona", "Volusia County", True),
        ("cityofedgewater", "Edgewater", "Volusia County", False),
        ("cityofnorthport", "North Port", "Sarasota County", False),
        ("venice", "Venice", "Sarasota County", False),
    ],
)
def test_city_registry_entries_ingest(monkeypatch, db_session, client, jurisdiction, county, committee_sponsors):
    monkeypatch.setattr(legistar_module, "LegistarClient", FakeClientWithBodySponsors)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name=client, limit=1)

    entity = db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalar_one()
    assert (entity.jurisdiction_name, entity.jurisdiction_level) == (jurisdiction, "city")
    assert entity.bill.geo_scope_names == [county]
    body = _sponsors(db_session)["City Commission Regular Meeting"]
    assert bool(body.attributes.get("committee")) is committee_sponsors


def test_adopted_instrument_reads_clearwater_action_item_titles():
    from app.pipeline.legistar import adopted_instrument

    assert adopted_instrument("Adopt Ordinance 9931-26 on second reading, amending Clearwater Code of Ordinances") == "Ordinance"
    assert adopted_instrument("Approve the DDB annual operating budget for Fiscal Year 2026-27 and adopt Resolution 26-02.") == "Resolution"
    # Mentioning one is not adopting one.
    assert adopted_instrument("Provide direction on Referendum Petition 26-01 which is a citizens petition to repeal Ordinance 9907-26.") is None
    assert adopted_instrument("Case 225-26 - Accept the Nuisance Abatement Lien for respondent(s) Randy Rainbolt") is None
    assert adopted_instrument("") is None


def test_clearwater_action_items_read_their_kind_from_the_title(monkeypatch, db_session):
    from app.pipeline.item_kind import backfill_item_types, item_kind

    class Fake(FakeLegistarClient):
        def get_matters(self, *, top):
            base = {**super().get_matters(top=top)[0], "MatterTypeName": "Action Item"}
            return [
                {**base, "MatterId": 1, "MatterFile": "ID#26-1100", "MatterTitle": "Adopt Ordinance 9931-26 on second reading, amending the Code"},
                {**base, "MatterId": 2, "MatterFile": "ID#26-1122", "MatterTitle": "Approve payment of $130,529.41 to settle claim 25000218"},
            ]

    monkeypatch.setattr(legistar_module, "LegistarClient", Fake)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="clearwater", limit=2)

    by_file = {e.bill.bill_number: e for e in db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalars()}
    adopted, other = by_file["ID#26-1100"], by_file["ID#26-1122"]
    assert adopted.attributes["item_type"] == "Ordinance" and item_kind(adopted.attributes["item_type"]) == "legislation"
    assert adopted.attributes["source_item_type"] == "Action Item"
    assert other.attributes["item_type"] == "Action Item" and item_kind(other.attributes["item_type"]) == "other"
    assert backfill_item_types(db_session) == 0
    assert adopted.attributes["item_type"] == "Ordinance"


def test_placeholder_titles_are_never_shown_and_all_placeholder_matters_are_skipped(monkeypatch, db_session):
    from app.pipeline.legistar import _bill_title, is_placeholder_title

    assert is_placeholder_title("[Enter Text Here]") and is_placeholder_title("  Enter title here. ")
    assert not is_placeholder_title("Enter into an agreement with Acme") and not is_placeholder_title(None)
    # A placeholder name yields to a real title; with nothing real left it is "Matter N".
    assert _bill_title({"MatterId": 7, "MatterName": "[Enter Text Here]", "MatterTitle": "Approve the lease"}) == "Approve the lease"
    assert _bill_title({"MatterId": 7, "MatterName": "[Enter Text Here]", "MatterTitle": None}) == "Matter 7"

    class Fake(FakeLegistarClient):
        def get_matters(self, *, top):
            base = super().get_matters(top=top)[0]
            return [
                {**base, "MatterId": 1, "MatterName": "[Enter Text Here]", "MatterTitle": "[Enter Text Here]", "MatterFile": "26-1"},
                {**base, "MatterId": 2, "MatterName": None, "MatterTitle": "Approve the lease", "MatterFile": "26-2"},
            ]

    monkeypatch.setattr(legistar_module, "LegistarClient", Fake)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))
    written = legistar_module.ingest_local_bills(db_session, client_name="keywest", limit=2)
    assert [e.bill.bill_number for e in written] == ["26-2"]


def test_a_duplicated_sponsor_relationship_does_not_stop_the_nightly(monkeypatch, db_session):
    """Key West's nightly died on 2026-10-14 with 'Multiple rows were found' when a
    person already had two sponsor rows on one matter. Re-ingest must go on."""
    from app.models import Relationship

    class Fake(FakeLegistarClient):
        def get_sponsors(self, matter_id):
            return [{"MatterSponsorName": "Mayor Jane Doe", "MatterSponsorNameId": 5}]

    monkeypatch.setattr(legistar_module, "LegistarClient", Fake)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))

    legistar_module.ingest_local_bills(db_session, client_name="keywest", limit=1)
    rel = db_session.execute(select(Relationship).where(Relationship.relationship_type == "sponsor")).scalar_one()
    db_session.add(Relationship(from_entity_id=rel.from_entity_id, to_entity_id=rel.to_entity_id,
                                relationship_type="sponsor", source_id=rel.source_id))
    # A second same-name person (e.g. from an earlier overlapping seed run) must not break it either.
    person = db_session.get(Entity, rel.from_entity_id)
    db_session.add(Entity(entity_type="person", name=person.name, jurisdiction_level="city",
                          jurisdiction_name=person.jurisdiction_name, external_ids={}, attributes={}))
    db_session.commit()

    legistar_module.ingest_local_bills(db_session, client_name="keywest", limit=1)  # must not raise


def test_a_matter_with_a_null_file_number_falls_back_to_its_id(monkeypatch, db_session):
    """Hollywood's planning-board items have MatterFile null; the seed run of
    2026-10-16 died on bills.bill_number NOT NULL."""

    class Fake(FakeLegistarClient):
        def get_matters(self, *, top):
            return [{**super().get_matters(top=top)[0], "MatterId": 21301, "MatterFile": None, "MatterTypeName": "Planning - HPB"}]

    monkeypatch.setattr(legistar_module, "LegistarClient", Fake)
    monkeypatch.setattr(topic_tagging_ollama_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("[]"))
    written = legistar_module.ingest_local_bills(db_session, client_name="hollywoodfl", limit=1)
    assert written[0].bill.bill_number == "21301"
