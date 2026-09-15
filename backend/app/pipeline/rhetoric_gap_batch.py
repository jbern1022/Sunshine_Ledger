"""Batch-run the rhetoric-vs-substance title/text gap check (Todoist
6hWPqqwCCf9jmGQp) for already-ingested bills that have full_text but no
rhetoric_gap claim yet.

Simpler selection than summarize_batch.py's hash-based staleness check --
this is a new, small-scope feature (v1: title/blurb vs. full text only), so
v1 just skips bills that already have a rhetoric_gap claim rather than
tracking whether the input has changed since. Re-checking after a bill's
full_text is amended is a real gap, same shape as the one summarize_batch.py
solved with input hashing -- worth the same fix here if/when this feature
graduates past v1, not before.

Usage:
    python -m app.pipeline.rhetoric_gap_batch [--limit N]
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
from app.pipeline.rhetoric_gap import CLAIM_TYPE, rhetoric_gap_and_store

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


def select_bills_needing_rhetoric_gap_check(db, *, limit: int | None = None) -> list[Entity]:
    """Bills with full_text and no rhetoric_gap claim yet. No DB writes and
    no Ollama calls, so this stays testable without a reachable model host."""
    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.full_text.isnot(None))
        .options(selectinload(Entity.bill), selectinload(Entity.claims))
    )

    candidates = [
        entity
        for entity in db.execute(stmt).scalars().all()
        if not any(c.claim_type == CLAIM_TYPE for c in entity.claims)
    ]
    if limit:
        candidates = candidates[:limit]
    return candidates


def run_rhetoric_gap_batch(limit: int | None = None) -> tuple[int, int, int]:
    """Returns (gaps_found, no_gap, failed) counts."""
    _check_ollama_reachable()

    db = SessionLocal()
    gaps_found = no_gap = failed = 0
    try:
        candidates = select_bills_needing_rhetoric_gap_check(db, limit=limit)
        logger.info("Checking %d bills for a rhetoric gap", len(candidates))

        for entity in candidates:
            bill = entity.bill
            try:
                source = Source(
                    url=bill.full_text_url or "",
                    document_reference=bill.bill_number,
                    publisher=f"{entity.jurisdiction_name or ''} via {bill.source_system}".strip(),
                    source_type=f"{bill.source_system}_bill",
                    retrieved_at=datetime.now(timezone.utc),
                    metadata_json={"used_for": "rhetoric_gap_check"},
                )
                db.add(source)
                db.flush()

                claim = rhetoric_gap_and_store(db, entity, source)
                if claim is not None:
                    gaps_found += 1
                    print(f"  GAP  {bill.bill_number}")
                else:
                    no_gap += 1
            except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the batch
                db.rollback()
                failed += 1
                print(f"  FAIL {bill.bill_number}: {exc}")

        return gaps_found, no_gap, failed
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    found, clean, bad = run_rhetoric_gap_batch(limit=args.limit)
    print(f"\nDone: {found} gaps flagged, {clean} checked clean, {bad} failed.")
