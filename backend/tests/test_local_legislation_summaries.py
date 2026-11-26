"""Local ordinances and resolutions get their own prompt (accuracy sample 01,
docs/grant-ready/ACCURACY_SAMPLE_01_LOCAL_LEGISLATION.md): they were written with
the state-bill prompt, which produced "this bill" on 16 of 20, "the state" for a
city's union contract, and invented definitions on title-only records."""

from datetime import datetime, timezone

import pytest

from app.models import Source
from app.pipeline import summarize
from app.pipeline.summarize import (
    ITEM_FALLBACK_GENERATED_BY,
    PROMPT_VERSION,
    LOCAL_LEGISLATION_PROMPT,
    generate_local_legislation_summary,
    instrument_label,
    prompt_version_for,
    summary_input_hash,
    violates_local_wording,
)
from app.pipeline.summarize_batch import select_bills_needing_summary

MODEL = "llama3.1:8b"


class SeqClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []
        self.model = MODEL

    def generate(self, prompt, **_):
        self.prompts.append(prompt)
        return self.answers.pop(0)


@pytest.mark.parametrize(
    "item_type,label",
    [("Ordinance", "ordinance"), ("ORDINANCE FIRST READING", "ordinance"), ("Resolution", "resolution"), ("", "measure")],
)
def test_instrument_label(item_type, label):
    assert instrument_label(item_type) == label


def test_prompt_names_the_instrument_and_government_and_forbids_guessing():
    p = LOCAL_LEGISLATION_PROMPT.format(
        bill_number="26-1", title="T", instrument="resolution", jurisdiction="Margate", bill_text="body"
    )
    assert "Bill:" not in p
    assert "this resolution" in p and "Margate" in p
    assert "Never call it a bill" in p
    assert "the state" in p  # the rule about naming the right government
    assert "only a title" in p


def test_local_legislation_has_its_own_version_and_state_bills_keep_theirs():
    assert prompt_version_for("legislation") == PROMPT_VERSION
    assert prompt_version_for("legislation", "state") == PROMPT_VERSION
    assert prompt_version_for("legislation", "city") == f"{PROMPT_VERSION}+local1"
    assert prompt_version_for("legislation", "county") == f"{PROMPT_VERSION}+local1"
    assert prompt_version_for("agenda", "city") == f"{PROMPT_VERSION}+item1"


@pytest.mark.parametrize(
    "answer,source",
    [
        ("This bill approves a contract.", "A contract."),
        ("This resolution approves a contract between the state and the union.", "City of Margate and the union"),
        ("This ordinance likely aims to clarify the code.", "Amending the code"),
    ],
)
def test_wording_check_flags_bill_wording_the_wrong_government_and_guesses(answer, source):
    assert violates_local_wording(answer, source)


@pytest.mark.parametrize(
    "answer,source",
    [
        ("This resolution approves the City of Margate's contract with the union.", "contract with the union"),
        ("This ordinance asks the state to designate June.", "urging the State of Florida to designate June"),
        ("This resolution accepts a bill of sale for a truck.", "bill of sale"),
    ],
)
def test_wording_check_accepts_plain_local_descriptions(answer, source):
    assert not violates_local_wording(answer, source)


def test_rule_breaking_answers_are_retried_once_then_fall_back_to_the_title():
    client = SeqClient("This bill approves it.", "The bill approves it.")
    text, fallback = generate_local_legislation_summary(
        "26-1", "Approving a collective bargaining agreement", "Approving a collective bargaining agreement",
        item_type="Resolution", jurisdiction="Margate", client=client,
    )
    assert fallback is True and len(client.prompts) == 2
    assert text.startswith("Resolution: Approving a collective bargaining agreement.")
    assert "bill" not in text.lower()


def test_a_clean_answer_is_used_as_is():
    client = SeqClient("This resolution approves Margate's agreement with the Federation of Public Employees.")
    text, fallback = generate_local_legislation_summary(
        "26-1", "T", "body", item_type="Resolution", jurisdiction="Margate", client=client
    )
    assert fallback is False and text.startswith("This resolution approves")


def _ordinance(bill_factory, db_session):
    e = bill_factory(bill_number="2026-1", name="An ordinance rezoning land")
    e.jurisdiction_level = "city"
    e.jurisdiction_name = "Doral"
    e.attributes = {"item_type": "Ordinance"}
    e.bill.source_system = "legistar"
    e.bill.description = "An ordinance rezoning land"
    db_session.commit()
    return e


def test_local_legislation_summarized_with_the_state_prompt_is_redone(db_session, bill_factory):
    from app.models import Claim

    e = _ordinance(bill_factory, db_session)
    old = summary_input_hash(e.bill.description, model=MODEL, prompt_version=PROMPT_VERSION)
    for ct in ("what_it_does", "who_it_affects"):
        db_session.add(Claim(bill_entity_id=e.id, claim_type=ct, claim_text="x", generated_by=f"llm:{MODEL}", input_hash=old))
    db_session.commit()
    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert e in candidates


def test_summarize_and_store_uses_the_local_prompt_for_an_ordinance(db_session, bill_factory, monkeypatch):
    e = _ordinance(bill_factory, db_session)
    src = Source(url="u", document_reference="2026-1", publisher="p", source_type="legistar_bill", retrieved_at=datetime.now(timezone.utc))
    db_session.add(src)
    db_session.flush()
    client = SeqClient("This ordinance rezones land in Doral.", "Property owners in the rezoned area.")
    monkeypatch.setattr(summarize, "OllamaClient", lambda *a, **k: client)
    claims = summarize.summarize_and_store(db_session, e, "An ordinance rezoning land", src)
    by_type = {c.claim_type: c for c in claims}
    assert by_type["what_it_does"].claim_text == "This ordinance rezones land in Doral."
    assert "Doral" in client.prompts[0] and "Bill:" not in client.prompts[0]
    assert "who_it_affects" in by_type
    expected = summary_input_hash("An ordinance rezoning land", model=MODEL, prompt_version=prompt_version_for("legislation", "city"))
    assert all(c.input_hash == expected for c in claims)


def test_summarize_and_store_marks_a_local_title_fallback_as_rule_made(db_session, bill_factory, monkeypatch):
    e = _ordinance(bill_factory, db_session)
    src = Source(url="u", document_reference="2026-1", publisher="p", source_type="legistar_bill", retrieved_at=datetime.now(timezone.utc))
    db_session.add(src)
    db_session.flush()
    client = SeqClient("This bill rezones.", "The bill rezones.", "Owners.")
    monkeypatch.setattr(summarize, "OllamaClient", lambda *a, **k: client)
    claims = {c.claim_type: c for c in summarize.summarize_and_store(db_session, e, "An ordinance rezoning land", src)}
    assert claims["what_it_does"].generated_by == ITEM_FALLBACK_GENERATED_BY
    assert claims["who_it_affects"].generated_by == f"llm:{MODEL}"
