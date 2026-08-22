"""Batch-generate plain-language summaries for already-ingested bills whose
summaries are missing or out of date (BRD 5.2).

Work is selected by comparing a hash of the exact summarization input
(source text + model + prompt version) against what each stored claim was
generated from. That skips bills nothing has changed for -- BRD 6's
cost-aware requirement -- and, unlike the older "skip anything that already
has a claim" rule, actually refreshes bills whose text was amended after
they were first summarized.

Summarizes the cleaned full text of the filed bill where available (see
pipeline/bill_text.py), falling back to the short official `description`
for sources with no PDF to extract -- Legistar and iQM2 bills, and any
LegiScan bill the text backfill hasn't reached. See `summarization_input`.

Only run this after the Roadmap's Step 2 quality gate
(`review_summaries.py`) has been checked against real bills -- this writes
directly to the public-facing `claims` table.

Usage:
    python -m app.pipeline.summarize_batch [--limit N]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import Bill, Entity, Source
from app.pipeline.summarize import summarize_and_store, summary_input_hash

logger = logging.getLogger(__name__)


def summarization_input(bill: Bill) -> tuple[str | None, str]:
    """The text to summarize for `bill`, plus a label describing its origin.

    Prefers the cleaned full bill text over the short official blurb. The
    Step 2 quality gate against real 2026-session bills showed full text is
    materially better: it names the specific groups a bill regulates where
    the blurb produced "does not specify a particular affected group", and
    it captures conditions the blurb omits entirely.

    Falls back to `description` for bills with no full text -- Legistar and
    iQM2 sources have no PDF to extract, and full-text backfill for
    LegiScan bills is a separate job that may not have reached every bill.

    Single source of truth on purpose: work selection and execution must
    derive the input the same way, or the hash computed when deciding to
    summarize wouldn't match the hash stored afterwards, and those bills
    would be re-summarized on every run forever.
    """
    if bill.full_text:
        return bill.full_text, "legiscan_full_text"
    if bill.description:
        return bill.description, f"{bill.source_system}_description"
    return None, "none"


def _check_ollama_reachable() -> None:
    try:
        resp = httpx.get(f"{settings.ollama_host.rstrip('/')}/api/tags", timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Ollama not reachable at {settings.ollama_host} -- check it's awake and OLLAMA_HOST is correct: {exc}"
        ) from exc

    models = [m["name"] for m in resp.json().get("models", [])]
    if models and not any(settings.ollama_model in m for m in models):
        logger.warning(
            "Configured OLLAMA_MODEL=%s not found in Ollama's model list %s -- check for a typo/tag mismatch.",
            settings.ollama_model,
            models,
        )


def select_bills_needing_summary(
    db, *, model: str, limit: int | None = None, force: bool = False
) -> tuple[list[Entity], int]:
    """Bills whose summaries are missing or stale, plus a count of those
    skipped as already up to date.

    A bill needs work when it has no LLM-generated claims yet, or when its
    claims were generated from a different input (see `summary_input_hash`:
    source text, model, prompt version). The previous rule -- skip anything
    with *any* claim -- meant an amended bill kept its original summary
    permanently, since ingestion updates `bill.description` in place.

    No DB writes and no Ollama calls, so this stays testable without a
    reachable model host.
    """
    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill")
        .options(selectinload(Entity.bill), selectinload(Entity.claims))
    )

    candidates: list[Entity] = []
    skipped = 0
    for entity in db.execute(stmt).scalars().all():
        if not entity.bill:
            continue
        text, _ = summarization_input(entity.bill)
        if not text:
            continue

        if not force:
            expected = summary_input_hash(text, model=model)
            llm_claims = [c for c in entity.claims if c.generated_by.startswith("llm:")]
            if llm_claims and all(c.input_hash == expected for c in llm_claims):
                skipped += 1
                continue

        candidates.append(entity)

    if limit:
        candidates = candidates[:limit]
    return candidates, skipped


def mark_existing_claims_current(db, *, model: str) -> int:
    """Backfill `input_hash` on LLM claims that predate the column, treating
    them as generated from their bill's current description.

    Opt-in (`--mark-current`), never automatic, because it asserts something
    we can't actually verify: that each existing summary was produced from
    the description now stored. That's true for any bill unchanged since it
    was summarized, and false for one amended in between -- those would be
    marked current while showing a stale summary.

    The alternative is leaving the hashes null, which re-summarizes the
    whole corpus on the next run. Correct, but not free. Use this only when
    the stored summaries are known to match the current model and prompts.

    Returns the number of claims updated.
    """
    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill")
        .options(selectinload(Entity.bill), selectinload(Entity.claims))
    )

    updated = 0
    for entity in db.execute(stmt).scalars().all():
        if not entity.bill:
            continue
        text, _ = summarization_input(entity.bill)
        if not text:
            continue
        expected = summary_input_hash(text, model=model)
        for claim in entity.claims:
            if claim.generated_by.startswith("llm:") and claim.input_hash is None:
                claim.input_hash = expected
                updated += 1

    db.commit()
    logger.info("Marked %d pre-existing claims as current for model=%s", updated, model)
    return updated


def summarize_unclaimed_bills(limit: int | None = None, *, force: bool = False) -> tuple[int, int]:
    """Returns (succeeded, failed) counts."""
    _check_ollama_reachable()

    db = SessionLocal()
    succeeded = failed = 0
    try:
        candidates, skipped = select_bills_needing_summary(
            db, model=settings.ollama_model, limit=limit, force=force
        )

        logger.info(
            "Summarizing %d bills (%d skipped -- summaries already match current input)",
            len(candidates),
            skipped,
        )

        for entity in candidates:
            bill = entity.bill
            try:
                text, input_label = summarization_input(bill)
                source = Source(
                    url=bill.full_text_url or "",
                    document_reference=bill.bill_number,
                    publisher=f"{entity.jurisdiction_name or ''} via {bill.source_system}".strip(),
                    source_type=f"{bill.source_system}_bill",
                    retrieved_at=datetime.now(timezone.utc),
                    # Record which text produced the summary -- the two
                    # inputs differ enough in quality that knowing which was
                    # used matters when reviewing a claim.
                    metadata_json={"used_for": "summarization", "input": input_label},
                )
                db.add(source)
                db.flush()

                summarize_and_store(db, entity, text, source)
                succeeded += 1
                print(f"  OK  {bill.bill_number}")
            except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the batch
                db.rollback()
                failed += 1
                print(f"  FAIL {bill.bill_number}: {exc}")

        return succeeded, failed
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-summarize even when the stored summaries match the current input. "
        "Expensive at full corpus size -- normally the hash check is what you want.",
    )
    parser.add_argument(
        "--mark-current",
        action="store_true",
        help="Backfill input_hash on pre-existing claims instead of summarizing. "
        "Asserts they match the current description/model -- read the docstring first.",
    )
    args = parser.parse_args()

    if args.mark_current:
        db = SessionLocal()
        try:
            print(f"Marked {mark_existing_claims_current(db, model=settings.ollama_model)} claims as current.")
        finally:
            db.close()
    else:
        ok, bad = summarize_unclaimed_bills(limit=args.limit, force=args.force)
        print(f"\nDone: {ok} summarized, {bad} failed.")
