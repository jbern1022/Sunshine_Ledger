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
