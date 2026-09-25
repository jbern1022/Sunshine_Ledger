"""One-time backfill: classify pre-existing local (Legistar/iQM2) bills that
predate the topic-tagging feature (merged 2026-09-15, commit 0cbf348).

LegiScan-sourced bills are deliberately excluded here. The `subjects` field
that would drive LegiScan tagging was verified live against 63 real bills
across FL/CA/NY and came back empty every time -- a data-availability limit
on this API key's tier, not a parsing bug (see the LegiScan verification
ticket). Re-fetching ~2,300 already-ingested LegiScan bills to backfill tags
that will never populate would spend real API quota for zero result, so this
only covers the Ollama-classified local bills, which cost compute time, not
quota.

Modeled on `legiscan.sync_state_bill_history`'s backfill pattern: a deliberate,
explicit, one-time-per-bill pass over bills the normal ingestion pipelines
won't revisit, not something folded into the nightly job.

Usage:
    python -m app.pipeline.topic_tagging_backfill [--limit N]
"""

from __future__ import annotations

import argparse
import logging

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal
from app.logging_setup import quiet_http_logging
from app.models import Entity
from app.models.tag import BillTag
from app.pipeline.topic_tagging_ollama import tag_local_bill

logger = logging.getLogger(__name__)

LOCAL_SOURCE_KEYS = ("legistar_matter_id", "iqm2_legi_file_id")


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


def select_local_bills_needing_tags(db, *, limit: int | None = None) -> list[Entity]:
    """Local bill entities with no ollama-sourced tag yet.

    No DB writes and no Ollama calls, so this stays testable without a
    reachable model host -- same separation `summarize_batch.py` uses.
    """
    already_tagged = select(BillTag.bill_entity_id).where(BillTag.tag_source == "ollama")

    stmt = (
        select(Entity)
        .where(
            Entity.entity_type == "bill",
            or_(*(Entity.external_ids.has_key(key) for key in LOCAL_SOURCE_KEYS)),
            Entity.id.notin_(already_tagged),
        )
        .options(selectinload(Entity.bill))
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def backfill_local_bill_tags(limit: int | None = None) -> tuple[int, int]:
    """Returns (succeeded, failed) counts."""
    _check_ollama_reachable()

    db = SessionLocal()
    succeeded = failed = 0
    try:
        candidates = select_local_bills_needing_tags(db, limit=limit)
        logger.info("Backfilling topic tags for %d local bills", len(candidates))

        for entity in candidates:
            description = entity.bill.description if entity.bill else ""
            try:
                tags = tag_local_bill(db, entity.id, title=entity.name, description=description or "")
                db.commit()
                succeeded += 1
                slugs = [t.tag_id for t in tags]
                print(f"  OK  {entity.name!r} -- {len(slugs)} tag(s)")
            except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the batch
                db.rollback()
                failed += 1
                print(f"  FAIL {entity.name!r}: {exc}")

        return succeeded, failed
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Test on a small batch before running the full corpus.",
    )
    args = parser.parse_args()

    ok, bad = backfill_local_bill_tags(limit=args.limit)
    print(f"\nDone: {ok} tagged, {bad} failed.")
