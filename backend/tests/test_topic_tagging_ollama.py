import httpx
import pytest

from app.models import BillTag, Tag
from app.models.tag import GOVERNANCE_SLUG
from app.pipeline.summarize import OllamaError
from app.pipeline.topic_tagging_ollama import (
    _extract_json_array,
    classify_local_bill_topics,
    tag_local_bill,
)


class FakeOllamaClient:
    def __init__(self, response: str | None = None, *, raises: Exception | None = None):
        self.response = response
        self.raises = raises
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.raises:
            raise self.raises
        return self.response


# --- _extract_json_array ----------------------------------------------------


def test_extract_json_array_plain():
    assert _extract_json_array('["housing", "taxes_budget"]') == ["housing", "taxes_budget"]


def test_extract_json_array_with_surrounding_text():
    text = 'Sure, here is the answer:\n["housing"]\nHope that helps!'
    assert _extract_json_array(text) == ["housing"]


def test_extract_json_array_no_array_present():
    assert _extract_json_array("I don't know") is None


def test_extract_json_array_malformed_json():
    assert _extract_json_array("[housing, taxes_budget]") is None


# --- classify_local_bill_topics ---------------------------------------------


def test_classify_returns_valid_slugs():
    client = FakeOllamaClient('["housing", "taxes_budget"]')
    result = classify_local_bill_topics("A Bill", "About affordable housing and taxes", client=client)
    assert result == ["housing", "taxes_budget"]


def test_classify_drops_unrecognized_slugs():
    client = FakeOllamaClient('["housing", "not_a_real_category"]')
    result = classify_local_bill_topics("A Bill", "desc", client=client)
    assert result == ["housing"]


def test_classify_dedupes():
    client = FakeOllamaClient('["housing", "housing"]')
    assert classify_local_bill_topics("A Bill", "desc", client=client) == ["housing"]


def test_classify_falls_back_to_governance_when_nothing_valid():
    client = FakeOllamaClient('["not_a_real_category"]')
    assert classify_local_bill_topics("A Bill", "desc", client=client) == [GOVERNANCE_SLUG]


def test_classify_falls_back_to_governance_on_unparseable_response():
    client = FakeOllamaClient("I cannot help with that")
    assert classify_local_bill_topics("A Bill", "desc", client=client) == [GOVERNANCE_SLUG]


def test_classify_falls_back_to_governance_on_empty_array():
    client = FakeOllamaClient("[]")
    assert classify_local_bill_topics("A Bill", "desc", client=client) == [GOVERNANCE_SLUG]


def test_classify_falls_back_to_governance_on_connection_error():
    client = FakeOllamaClient(raises=httpx.ConnectError("connection refused"))
    assert classify_local_bill_topics("A Bill", "desc", client=client) == [GOVERNANCE_SLUG]


def test_classify_falls_back_to_governance_on_ollama_error():
    client = FakeOllamaClient(raises=OllamaError("bad response"))
    assert classify_local_bill_topics("A Bill", "desc", client=client) == [GOVERNANCE_SLUG]


# --- tag_local_bill (DB-backed) ---------------------------------------------


@pytest.fixture()
def housing_tag(db_session):
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    return tag


def test_tag_local_bill_creates_ollama_sourced_tags(db_session, bill_factory, housing_tag):
    entity = bill_factory()
    client = FakeOllamaClient('["housing"]')

    created = tag_local_bill(db_session, entity.id, title="A Bill", description="About housing", client=client)

    assert len(created) == 1
    assert created[0].tag_id == housing_tag.id
    assert created[0].tag_source == "ollama"
    assert created[0].raw_subject is None
    assert len(client.calls) == 1


def test_tag_local_bill_skips_already_tagged_bills(db_session, bill_factory, housing_tag):
    entity = bill_factory()
    client = FakeOllamaClient('["housing"]')

    tag_local_bill(db_session, entity.id, title="A Bill", description="About housing", client=client)
    second = tag_local_bill(db_session, entity.id, title="A Bill", description="About housing", client=client)

    assert second == []
    assert len(client.calls) == 1  # no second classification call -- the whole point of the guard
    assert db_session.query(BillTag).filter(BillTag.bill_entity_id == entity.id).count() == 1


def test_tag_local_bill_does_not_skip_a_legiscan_tagged_bill(db_session, bill_factory, housing_tag):
    """A bill could in principle already carry a legiscan-sourced tag (not
    realistic for local bills today, but the guard is specifically scoped to
    tag_source="ollama" so it doesn't accidentally suppress local
    classification because of an unrelated tag_source)."""
    entity = bill_factory()
    db_session.add(BillTag(bill_entity_id=entity.id, tag_id=housing_tag.id, tag_source="legiscan", active=True))
    db_session.commit()

    client = FakeOllamaClient('["housing"]')
    result = tag_local_bill(db_session, entity.id, title="A Bill", description="About housing", client=client)

    assert len(client.calls) == 1  # guard didn't suppress it
    assert result == []  # but assign_tags_for_bill itself is idempotent per-tag, so no duplicate row


def test_classify_prompt_names_the_kind_of_legislation():
    from app.pipeline.topic_tagging_ollama import STATE_KIND

    class Recording:
        prompt = ""

        def generate(self, prompt):
            Recording.prompt = prompt
            return '["housing"]'

    assert classify_local_bill_topics("Affordable Housing", "An act relating to housing", client=Recording(),
                                      kind=STATE_KIND) == ["housing"]
    assert "a piece of Florida state legislation" in Recording.prompt
    assert "local government" not in Recording.prompt


def test_governance_is_dropped_when_a_specific_topic_was_chosen():
    class Answer:
        def generate(self, prompt):
            return '["governance", "housing"]'

    assert classify_local_bill_topics("Affordable Housing", "", client=Answer()) == ["housing"]


def test_governance_alone_is_kept():
    class Answer:
        def generate(self, prompt):
            return '["governance"]'

    assert classify_local_bill_topics("Council Rules", "", client=Answer()) == ["governance"]


# --- quarantine, input hash and failure handling ------------------------------


def _tags(db_session, entity):
    return [(bt.tag.slug, bt.active) for bt in db_session.query(BillTag).filter(BillTag.bill_entity_id == entity.id)]


def test_unknown_slugs_are_quarantined_with_provenance_not_added_to_the_taxonomy(db_session, bill_factory, housing_tag):
    from app.models import TagQuarantine

    entity = bill_factory()
    client = FakeOllamaClient('["housing", "zoning", "Zoning", "events"]')

    tag_local_bill(db_session, entity.id, title="Rezone Main St", description="d", client=client)

    rows = db_session.query(TagQuarantine).filter(TagQuarantine.bill_entity_id == entity.id).all()
    assert sorted(r.proposed_slug for r in rows) == ["events", "zoning"]  # case-folded, deduped
    assert {r.status for r in rows} == {"pending"}
    assert rows[0].bill_title == "Rezone Main St" and rows[0].tag_source == "ollama"
    assert db_session.query(Tag).filter(Tag.slug == "zoning").count() == 0
    assert _tags(db_session, entity) == [("housing", True)]


def test_quarantine_is_not_duplicated_on_a_reclassification(db_session, bill_factory, housing_tag):
    from app.models import TagQuarantine

    entity = bill_factory()
    client = FakeOllamaClient('["housing", "zoning"]')
    tag_local_bill(db_session, entity.id, title="A", description="one", client=client)
    tag_local_bill(db_session, entity.id, title="A", description="two", client=client)  # amended

    assert db_session.query(TagQuarantine).filter(TagQuarantine.bill_entity_id == entity.id).count() == 1


def test_a_failed_call_writes_no_governance_badge_and_is_retried(db_session, bill_factory, housing_tag):
    from app.models import BillTagRun

    entity = bill_factory()
    down = FakeOllamaClient(raises=httpx.ConnectError("refused"))
    assert tag_local_bill(db_session, entity.id, title="A", description="d", client=down) == []

    assert _tags(db_session, entity) == []
    run = db_session.query(BillTagRun).filter(BillTagRun.bill_entity_id == entity.id).one()
    assert run.outcome == "failed" and "ConnectError" in run.detail

    up = FakeOllamaClient('["housing"]')
    created = tag_local_bill(db_session, entity.id, title="A", description="d", client=up)  # same input: still retried

    assert [bt.tag_id for bt in created] == [housing_tag.id]
    assert db_session.query(BillTagRun).filter(BillTagRun.bill_entity_id == entity.id).one().outcome == "ok"


def test_an_answer_with_nothing_valid_gets_governance_and_is_marked_empty(db_session, bill_factory):
    from app.models import BillTagRun

    db_session.add(Tag(slug="governance", label="Governance", active=True))
    db_session.commit()
    entity = bill_factory()

    tag_local_bill(db_session, entity.id, title="A", description="d", client=FakeOllamaClient('["zoning"]'))

    assert _tags(db_session, entity) == [("governance", True)]
    assert db_session.query(BillTagRun).filter(BillTagRun.bill_entity_id == entity.id).one().outcome == "empty"


def test_an_amended_bill_is_reclassified_and_stale_model_tags_are_hidden(db_session, bill_factory, housing_tag):
    transport = Tag(slug="education", label="Education", active=True)
    db_session.add(transport)
    db_session.commit()
    entity = bill_factory()

    tag_local_bill(db_session, entity.id, title="A", description="about housing", client=FakeOllamaClient('["housing"]'))
    again = FakeOllamaClient('["education"]')
    tag_local_bill(db_session, entity.id, title="A", description="now about buses", client=again)

    assert len(again.calls) == 1
    assert sorted(_tags(db_session, entity)) == [("education", True), ("housing", False)]


def test_unchanged_input_is_not_reclassified(db_session, bill_factory, housing_tag):
    entity = bill_factory()
    client = FakeOllamaClient('["housing"]')
    tag_local_bill(db_session, entity.id, title="A", description="d", client=client)
    tag_local_bill(db_session, entity.id, title="A", description="d", client=client)
    assert len(client.calls) == 1


def test_a_bill_tagged_before_runs_existed_is_recorded_not_reclassified(db_session, bill_factory, housing_tag):
    from app.models import BillTagRun

    entity = bill_factory()
    db_session.add(BillTag(bill_entity_id=entity.id, tag_id=housing_tag.id, tag_source="ollama", active=True))
    db_session.commit()
    client = FakeOllamaClient('["housing"]')

    assert tag_local_bill(db_session, entity.id, title="A", description="d", client=client) == []

    assert client.calls == []
    assert db_session.query(BillTagRun).filter(BillTagRun.bill_entity_id == entity.id).one().outcome == "legacy"
    # ...and a later amendment is then noticed.
    tag_local_bill(db_session, entity.id, title="A", description="changed", client=client)
    assert len(client.calls) == 1


def test_tag_quarantine_review_records_a_disposition_for_every_pending_row(db_session, bill_factory, housing_tag):
    from app.models import TagQuarantine
    from app.pipeline.tag_quarantine import pending_summary, resolve

    for _ in range(2):
        tag_local_bill(db_session, bill_factory().id, title="Rezone", description="d",
                       client=FakeOllamaClient('["housing", "zoning"]'))

    assert pending_summary(db_session)[0][:2] == ("zoning", 2)
    assert resolve(db_session, "zoning", "mapped", reviewer="JB", tag_slug="housing", note="same thing") == 2

    rows = db_session.query(TagQuarantine).all()
    assert {r.status for r in rows} == {"mapped"} and {r.reviewer for r in rows} == {"JB"}
    assert {r.mapped_tag_id for r in rows} == {housing_tag.id}
    assert pending_summary(db_session) == []
    with pytest.raises(ValueError):
        resolve(db_session, "zoning", "mapped", reviewer="JB")  # mapped needs --tag
