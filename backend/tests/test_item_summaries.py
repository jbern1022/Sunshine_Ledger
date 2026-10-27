"""Kind-aware summaries for city and county records (docs/LOCAL_ITEMS_READING_REVIEW_2026-10-27.md):
agenda items, hearing cases and minutes are not bills, so they are not described as bills."""

from datetime import datetime, timezone

import pytest

from app.models import Claim, Flag
from app.pipeline import summarize
from app.pipeline.summarize import (
    ITEM_FALLBACK_GENERATED_BY,
    PROMPT_VERSION,
    WHAT_IT_DOES_ITEM_PROMPT,
    generate_item_description,
    has_no_substance,
    prompt_version_for,
    summary_input_hash,
    violates_item_wording,
)
from app.pipeline.summarize_batch import retire_unneeded_claims, select_bills_needing_summary

MODEL = "llama3.1:8b"


class SeqClient:
    """Returns the queued answers in order and records the prompts it was given."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []
        self.model = MODEL

    def generate(self, prompt, **_):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def _item(bill_factory, db_session, *, item_type, name="Request to opt in to a settlement", text="The Board is asked to sign on."):
    entity = bill_factory(bill_number="26-1", name=name)
    entity.jurisdiction_level = "county"
    entity.jurisdiction_name = "Polk County"
    entity.attributes = {"item_type": item_type}
    entity.bill.source_system = "legistar"
    entity.bill.description = text
    db_session.commit()
    return entity


def _claim(db, entity, claim_type, *, generated_by=f"llm:{MODEL}", input_hash=None, text="x"):
    c = Claim(bill_entity_id=entity.id, claim_type=claim_type, claim_text=text, generated_by=generated_by, input_hash=input_hash)
    db.add(c)
    db.commit()
    return c


# --- the wording check ------------------------------------------------------


@pytest.mark.parametrize("text", [
    "This bill asks the Board to sign on.",
    "The bill creates an open space plan.",
    "The legislation would change a date.",
    "This item is likely a zoning request.",
    "It appears to amend a plan.",
    "It seems to be a routine request.",
    "Bill proposes a land use plan.",
])
def test_wording_check_flags_bill_wording_and_guesses(text):
    assert violates_item_wording(text)


@pytest.mark.parametrize("text", [
    "This item asks the Board to sign the county on to a settlement.",
    "The Board is asked to approve a bill of sale for a surplus truck.",
    "The county pays billing costs for the program.",
    "A public hearing on a planned development in District 1.",
])
def test_wording_check_accepts_plain_item_descriptions(text):
    assert not violates_item_wording(text)


# --- records with nothing to summarize --------------------------------------


@pytest.mark.parametrize("item_type,title", [
    ("Minutes", "October 21, 2026"),
    ("Minutes", "anything at all"),
    ("Agenda", "Matter 7218"),
    ("Planning - HPB", "10-13 Minutes"),
    ("Agenda", "October 21, 2026"),
])
def test_records_with_no_substance(item_type, title):
    assert has_no_substance(item_type, title)


@pytest.mark.parametrize("item_type,title", [
    ("Consent Agenda", "Accept Publix Davenport water system improvements"),
    ("Public Hearing", "Case # LUP-26-02-020 Gotha Subdivision Planned Development"),
    ("Proclamation", "Proclaiming November Veterans Month"),
])
def test_records_with_substance(item_type, title):
    assert not has_no_substance(item_type, title)


# --- prompt and versions ----------------------------------------------------


def test_item_prompt_is_not_framed_as_legislation():
    p = WHAT_IT_DOES_ITEM_PROMPT.format(bill_number="26-1", title="T", item_type="Public Hearing", bill_text="body")
    assert "piece of legislation" not in p
    assert "Public Hearing" in p and "this item" in p
    assert "Never call it a bill" in p


def test_only_non_legislation_gets_the_scoped_prompt_version():
    assert prompt_version_for("legislation") == PROMPT_VERSION
    for kind in ("agenda", "discussion", "other"):
        assert prompt_version_for(kind) == f"{PROMPT_VERSION}+item1"
    assert prompt_version_for("other") != prompt_version_for("legislation")


# --- generating a description -----------------------------------------------


def test_a_clean_answer_is_used_as_is():
    client = SeqClient("This item asks the Board to sign on to a settlement.")
    text, fallback = generate_item_description("26-1", "Opt in", "body", item_type="Consent Agenda", client=client)
    assert text == "This item asks the Board to sign on to a settlement." and fallback is False
    assert len(client.prompts) == 1


def test_a_rule_breaking_answer_is_retried_once_with_the_rule_restated():
    client = SeqClient("This bill asks the Board to sign on.", "This item asks the Board to sign on.")
    text, fallback = generate_item_description("26-1", "Opt in", "body", item_type="Consent Agenda", client=client)
    assert text == "This item asks the Board to sign on." and fallback is False
    assert len(client.prompts) == 2 and "broke a rule" in client.prompts[1]


def test_two_rule_breaking_answers_fall_back_to_a_plain_restatement_of_the_title():
    client = SeqClient("This bill asks.", "The bill asks.")
    text, fallback = generate_item_description(
        "26-1", "Opt in to the settlement", "body", item_type="Consent Agenda", client=client
    )
    assert fallback is True
    assert text.startswith("Consent Agenda: Opt in to the settlement.") and "no further detail" in text
    assert "bill" not in text.lower()


# --- work selection ----------------------------------------------------------


def _expected(entity, kind_version):
    return summary_input_hash(entity.bill.description, model=MODEL, prompt_version=kind_version)


def test_a_non_legislation_item_is_current_when_its_item_hash_matches(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    _claim(db_session, e, "what_it_does", input_hash=_expected(e, prompt_version_for("agenda")))
    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert e not in candidates and skipped == 1


def test_a_non_legislation_item_with_an_old_legislation_hash_is_resummarized(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    _claim(db_session, e, "what_it_does", input_hash=_expected(e, PROMPT_VERSION))
    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert e in candidates


def test_a_leftover_who_claim_does_not_keep_an_item_stale(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    _claim(db_session, e, "what_it_does", input_hash=_expected(e, prompt_version_for("agenda")))
    _claim(db_session, e, "who_it_affects", input_hash=_expected(e, PROMPT_VERSION))  # flagged, so it was kept
    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert e not in candidates


def test_a_title_only_fallback_counts_as_current(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    _claim(db_session, e, "what_it_does", generated_by=ITEM_FALLBACK_GENERATED_BY, input_hash=_expected(e, prompt_version_for("agenda")))
    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert e not in candidates


def test_minutes_are_never_candidates(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Minutes", name="October 21, 2026")
    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert e not in candidates


def test_legislation_selection_is_unchanged(db_session, bill_factory):
    e = bill_factory()
    e.bill.description = "Text."
    db_session.commit()
    _claim(db_session, e, "what_it_does", input_hash=summary_input_hash("Text.", model=MODEL))
    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert e not in candidates and skipped == 1


# --- retiring claims that should not exist ------------------------------------


def test_retire_removes_who_claims_on_non_legislation_but_keeps_what(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    _claim(db_session, e, "what_it_does")
    _claim(db_session, e, "who_it_affects")
    assert retire_unneeded_claims(db_session) == 1
    assert {c.claim_type for c in db_session.query(Claim).filter_by(bill_entity_id=e.id)} == {"what_it_does"}


def test_retire_removes_every_llm_claim_on_a_minutes_record(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Minutes", name="October 21, 2026")
    _claim(db_session, e, "what_it_does")
    _claim(db_session, e, "who_it_affects")
    assert retire_unneeded_claims(db_session) == 2
    assert db_session.query(Claim).filter_by(bill_entity_id=e.id).count() == 0


def test_retire_keeps_a_claim_a_reader_flagged(db_session, bill_factory):
    e = _item(bill_factory, db_session, item_type="Minutes", name="October 21, 2026")
    flagged = _claim(db_session, e, "what_it_does")
    db_session.add(Flag(bill_entity_id=e.id, claim_id=flagged.id, object_type="claim", object_id=flagged.id, reason_text="wrong"))
    db_session.commit()
    assert retire_unneeded_claims(db_session) == 0
    assert db_session.query(Claim).filter_by(bill_entity_id=e.id).count() == 1


def test_retire_never_touches_legislation_or_manual_claims(db_session, bill_factory):
    leg = bill_factory()
    _claim(db_session, leg, "who_it_affects")
    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    _claim(db_session, e, "who_it_affects", generated_by="manual_review")
    assert retire_unneeded_claims(db_session) == 0


# --- storing -----------------------------------------------------------------


def test_summarize_and_store_writes_only_what_it_does_for_an_item(db_session, bill_factory, monkeypatch):
    from app.models import Source

    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    src = Source(url="u", document_reference="26-1", publisher="p", source_type="legistar_bill", retrieved_at=datetime.now(timezone.utc))
    db_session.add(src)
    db_session.flush()
    client = SeqClient("This item asks the Board to sign on to a settlement.")
    monkeypatch.setattr(summarize, "OllamaClient", lambda *a, **k: client)
    claims = summarize.summarize_and_store(db_session, e, "The Board is asked to sign on.", src)
    assert [c.claim_type for c in claims] == ["what_it_does"]
    assert claims[0].generated_by == f"llm:{MODEL}"
    assert claims[0].input_hash == summary_input_hash("The Board is asked to sign on.", model=MODEL, prompt_version=prompt_version_for("agenda"))


def test_summarize_and_store_marks_a_title_fallback_as_rule_made(db_session, bill_factory, monkeypatch):
    from app.models import Source

    e = _item(bill_factory, db_session, item_type="Consent Agenda")
    src = Source(url="u", document_reference="26-1", publisher="p", source_type="legistar_bill", retrieved_at=datetime.now(timezone.utc))
    db_session.add(src)
    db_session.flush()
    client = SeqClient("This bill asks.", "The bill asks.")
    monkeypatch.setattr(summarize, "OllamaClient", lambda *a, **k: client)
    claims = summarize.summarize_and_store(db_session, e, "The Board is asked to sign on.", src)
    assert claims[0].generated_by == ITEM_FALLBACK_GENERATED_BY
    assert "no further detail" in claims[0].claim_text
