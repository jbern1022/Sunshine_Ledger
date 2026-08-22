"""Batch-generate plain-language summaries for already-ingested bills whose
summaries are missing or out of date (BRD 5.2).

Work is selected by comparing a hash of the exact summarization input
(source text + model + prompt version) against what each stored claim was
generated from. That skips bills nothing has changed for -- BRD 6's
cost-aware requirement -- and, unlike the older "skip anything that already
has a claim" rule, actually refreshes bills whose text was amended after
they were first summarized.

Uses each bill's short official `description` (from LegiScan, stored at
ingestion time) as the LLM input rather than full bill text -- real,
authoritative text, just thinner than the full legal text. A fuller
PDF-bill-text pipeline can replace this input later without changing
anything downstream (summarize_and_store just takes a string).

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
        if not entity.bill or not entity.bill.description:
            continue

        if not force:
            expected = summary_input_hash(entity.bill.description, model=model)
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
        if not entity.bill or not entity.bill.description:
            continue
        expected = summary_input_hash(entity.bill.description, model=model)
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
                source = Source(
                    url=bill.full_text_url or "",
                    document_reference=bill.bill_number,
                    publisher=f"{entity.jurisdiction_name or ''} via {bill.source_system}".strip(),
                    source_type=f"{bill.source_system}_bill",
                    retrieved_at=datetime.now(timezone.utc),
                    metadata_json={"used_for": "summarization", "input": "legiscan_description"},
                )
                db.add(source)
                db.flush()

                summarize_and_store(db, entity, bill.description, source)
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
