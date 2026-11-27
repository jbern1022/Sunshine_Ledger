import pytest

from app.models import Claim
from app.pipeline import strip_summary_preambles
from app.pipeline.summarize import strip_preamble


@pytest.mark.parametrize("raw", [
    "Here is a 2-4 sentence plain-language summary of the bill:\n\nThis bill designates a mangrove island.",
    "Here is a plain-language summary of the bill:\nThis bill designates a mangrove island.",
    "Here's a 4-sentence plain-language summary of the legislation: This bill designates a mangrove island.",
    "Sure, here is a summary of what this bill does:\n\nThis bill designates a mangrove island.",
])
def test_the_opener_is_removed(raw):
    assert strip_preamble(raw) == "This bill designates a mangrove island."


@pytest.mark.parametrize("text", [
    "This bill designates a mangrove island.",
    "Here is what changes: the county must hold a hearing.",  # no "summary" announced: content, keep
    "Here is a summary of the bill:",  # nothing after it: keep rather than publish empty
])
def test_anything_else_is_left_alone(text):
    assert strip_preamble(text) == text


def test_backfill_updates_in_place_and_is_idempotent(db_session, bill_factory):
    entity = bill_factory()
    c = Claim(bill_entity_id=entity.id, claim_type="what_it_does", generated_by="llm:llama3.1:8b", input_hash="h",
              claim_text="Here is a 2-4 sentence plain-language summary of the bill:\n\nThis bill does X.")
    db_session.add(c)
    db_session.commit()
    assert len(strip_summary_preambles.run(db_session, apply=False)) == 1
    assert c.claim_text.startswith("Here is")
    strip_summary_preambles.run(db_session, apply=True)
    db_session.refresh(c)
    assert (c.claim_text, c.input_hash) == ("This bill does X.", "h")
    assert strip_summary_preambles.run(db_session, apply=True) == []
