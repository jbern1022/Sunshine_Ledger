"""Tests for summarization work-selection and input hashing.

No Ollama involved: `select_bills_needing_summary` and `summary_input_hash`
are deliberately free of model calls so the expensive half of the pipeline
can be reasoned about (and regression-tested) without a reachable host.
"""

from app.models import Claim
from app.pipeline.summarize import PROMPT_VERSION, summary_input_hash
from app.pipeline.summarize_batch import select_bills_needing_summary, summarization_input

MODEL = "llama3.1:8b"


def _hash(text: str, *, model: str = MODEL) -> str:
    return summary_input_hash(text, model=model)


def _add_claim(db, entity, *, claim_type="what_it_does", input_hash=None, generated_by=f"llm:{MODEL}"):
    claim = Claim(
        bill_entity_id=entity.id,
        claim_type=claim_type,
        claim_text="summary text",
        generated_by=generated_by,
        input_hash=input_hash,
    )
    db.add(claim)
    db.commit()
    return claim


def _set_description(db, entity, text):
    entity.bill.description = text
    db.commit()


# --- hashing -------------------------------------------------------------


def test_hash_is_stable_for_same_input():
    assert _hash("some bill text") == _hash("some bill text")


def test_hash_changes_with_text():
    assert _hash("text A") != _hash("text B")


def test_hash_changes_with_model():
    """A summary produced by a different model is stale even if the bill
    text is identical."""
    assert _hash("same text", model="llama3.1:8b") != _hash("same text", model="llama3.2")


def test_hash_changes_with_prompt_version():
    a = summary_input_hash("same text", model=MODEL, prompt_version=PROMPT_VERSION)
    b = summary_input_hash("same text", model=MODEL, prompt_version=PROMPT_VERSION + "x")
    assert a != b


def test_hash_ignores_text_beyond_truncation_limit():
    """Only the truncated text is sent to the model, so trailing text that
    never reaches it must not invalidate an otherwise-current summary."""
    from app.pipeline.summarize import MAX_BILL_TEXT_CHARS

    base = "x" * MAX_BILL_TEXT_CHARS
    assert _hash(base) == _hash(base + " trailing text the model never sees")


# --- selection -----------------------------------------------------------


def test_selects_bill_with_no_claims(client, db_session, bill_factory):
    entity = bill_factory()
    _set_description(db_session, entity, "a description")

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]
    assert skipped == 0


def test_skips_bill_whose_hash_matches(db_session, bill_factory):
    entity = bill_factory()
    _set_description(db_session, entity, "a description")
    _add_claim(db_session, entity, input_hash=_hash("a description"))

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert candidates == []
    assert skipped == 1


def test_reselects_bill_whose_description_changed(db_session, bill_factory):
    """The regression this whole mechanism exists for: an amended bill used
    to keep its original summary forever."""
    entity = bill_factory()
    _set_description(db_session, entity, "original description")
    _add_claim(db_session, entity, input_hash=_hash("original description"))

    _set_description(db_session, entity, "amended description")

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]
    assert skipped == 0


def test_reselects_when_model_changed(db_session, bill_factory):
    entity = bill_factory()
    _set_description(db_session, entity, "a description")
    _add_claim(db_session, entity, input_hash=_hash("a description", model="old-model"))

    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]


def test_reselects_legacy_claims_with_null_hash(db_session, bill_factory):
    """Claims written before input_hash existed have no known input, so they
    must be treated as needing a refresh rather than silently trusted."""
    entity = bill_factory()
    _set_description(db_session, entity, "a description")
    _add_claim(db_session, entity, input_hash=None)

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]
    assert skipped == 0


def test_skips_bill_without_description(db_session, bill_factory):
    """No input text means nothing to summarize -- it isn't a candidate and
    isn't counted as an up-to-date skip either."""
    entity = bill_factory()
    _set_description(db_session, entity, None)

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert candidates == []
    assert skipped == 0


def test_manual_review_claims_do_not_mark_bill_current(db_session, bill_factory):
    """A human-written claim shouldn't suppress LLM summarization of the
    other claim types."""
    entity = bill_factory()
    _set_description(db_session, entity, "a description")
    _add_claim(db_session, entity, generated_by="manual_review", input_hash=None)

    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]


def test_partial_hash_match_reselects(db_session, bill_factory):
    """If one claim is current and another is stale, the bill still needs
    work -- both summaries come from the same run."""
    entity = bill_factory()
    _set_description(db_session, entity, "a description")
    _add_claim(db_session, entity, claim_type="what_it_does", input_hash=_hash("a description"))
    _add_claim(db_session, entity, claim_type="who_it_affects", input_hash=_hash("stale"))

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]
    assert skipped == 0


def test_force_ignores_hash_match(db_session, bill_factory):
    entity = bill_factory()
    _set_description(db_session, entity, "a description")
    _add_claim(db_session, entity, input_hash=_hash("a description"))

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL, force=True)
    assert [e.id for e in candidates] == [entity.id]
    assert skipped == 0


def test_limit_caps_candidates(db_session, bill_factory):
    for i in range(3):
        e = bill_factory(bill_number=f"HB {i}")
        _set_description(db_session, e, f"description {i}")

    candidates, _ = select_bills_needing_summary(db_session, model=MODEL, limit=2)
    assert len(candidates) == 2


# --- input source selection ---------------------------------------------


def test_prefers_full_text_over_description(db_session, bill_factory):
    entity = bill_factory()
    entity.bill.description = "short blurb"
    entity.bill.full_text = "the full text of the bill"
    db_session.commit()

    text, label = summarization_input(entity.bill)
    assert text == "the full text of the bill"
    assert label == "legiscan_full_text"


def test_falls_back_to_description_without_full_text(db_session, bill_factory):
    """Legistar and iQM2 bills have no PDF to extract, and the LegiScan
    backfill may not have reached every bill yet."""
    entity = bill_factory()
    entity.bill.description = "short blurb"
    entity.bill.full_text = None
    db_session.commit()

    text, label = summarization_input(entity.bill)
    assert text == "short blurb"
    assert label.endswith("_description")


def test_no_input_when_neither_is_present(db_session, bill_factory):
    entity = bill_factory()
    entity.bill.description = None
    entity.bill.full_text = None
    db_session.commit()

    assert summarization_input(entity.bill) == (None, "none")


def test_gaining_full_text_marks_bill_stale(db_session, bill_factory):
    """Backfilling full text must invalidate a description-based summary --
    this is what makes the input swap roll out without manual invalidation."""
    entity = bill_factory()
    entity.bill.description = "short blurb"
    db_session.commit()
    _add_claim(db_session, entity, input_hash=_hash("short blurb"))

    assert select_bills_needing_summary(db_session, model=MODEL)[0] == []

    entity.bill.full_text = "the much longer full text"
    db_session.commit()

    candidates, _ = select_bills_needing_summary(db_session, model=MODEL)
    assert [e.id for e in candidates] == [entity.id]


def test_selection_hash_matches_stored_hash(db_session, bill_factory):
    """Selection and execution must derive the input identically. If they
    diverged, every bill would look stale on every run and re-summarize
    forever."""
    entity = bill_factory()
    entity.bill.description = "short blurb"
    entity.bill.full_text = "the full text of the bill"
    db_session.commit()

    text, _ = summarization_input(entity.bill)
    _add_claim(db_session, entity, input_hash=summary_input_hash(text, model=MODEL))

    candidates, skipped = select_bills_needing_summary(db_session, model=MODEL)
    assert candidates == []
    assert skipped == 1
