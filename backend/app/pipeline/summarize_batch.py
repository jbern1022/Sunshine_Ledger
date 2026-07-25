"""Batch-generate plain-language summaries for already-ingested bills that
don't have one yet (BRD 5.2).

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
from app.pipeline.summarize import summarize_and_store

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


def summarize_unclaimed_bills(limit: int | None = None) -> tuple[int, int]:
    """Returns (succeeded, failed) counts."""
    _check_ollama_reachable()

    db = SessionLocal()
    succeeded = failed = 0
    try:
        stmt = (
            select(Entity)
            .join(Bill, Bill.entity_id == Entity.id)
            .where(Entity.entity_type == "bill")
            .options(selectinload(Entity.bill), selectinload(Entity.claims))
        )
        candidates = [
            e for e in db.execute(stmt).scalars().all() if not e.claims and e.bill and e.bill.description
        ]
        if limit:
            candidates = candidates[:limit]

        logger.info("Summarizing %d bills with no existing claims", len(candidates))

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
    args = parser.parse_args()

    ok, bad = summarize_unclaimed_bills(limit=args.limit)
    print(f"\nDone: {ok} summarized, {bad} failed.")
