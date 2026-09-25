"""One-time backfill: classify bills that have no Ollama topic tags yet with
the local model -- local (Legistar/iQM2) bills that predate topic tagging
(merged 2026-09-15, commit 0cbf348), and, with --include-state, state
(LegiScan) bills.

State bills were first left out because tagging them was meant to come from
LegiScan's `subjects` field, but that is empty for every FL bill on this API
tier (verified 2026-09-16 on 63 bills, and 2026-09-25 on the session
datasets). Classifying from title + description costs model time, not
LegiScan quota. Until 2026-09-25 no state bill had a tag, so no state bill
had badges, topic filtering or a demographic overlay.

Modeled on `legiscan.sync_state_bill_history`'s backfill pattern: a deliberate,
explicit, one-time-per-bill pass over bills the normal ingestion pipelines
won't revisit, not something folded into the nightly job.

Usage:
    python -m app.pipeline.topic_tagging_backfill [--include-state] [--limit N]
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
from app.pipeline.topic_tagging_ollama import LOCAL_KIND, STATE_KIND, tag_local_bill

logger = logging.getLogger(__name__)

LOCAL_SOURCE_KEYS = ("legistar_matter_id", "iqm2_legi_file_id")
STATE_SOURCE_KEY = "legiscan_id"


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


def select_local_bills_needing_tags(
    db, *, limit: int | None = None, include_state: bool = False
) -> list[Entity]:
    """Local bill entities (and state ones, with include_state) with no
    ollama-sourced tag yet.

    No DB writes and no Ollama calls, so this stays testable without a
    reachable model host -- same separation `summarize_batch.py` uses.
    """
    already_tagged = select(BillTag.bill_entity_id).where(BillTag.tag_source == "ollama")

    stmt = (
        select(Entity)
        .where(
            Entity.entity_type == "bill",
            or_(
                *(
                    Entity.external_ids.has_key(key)
                    for key in LOCAL_SOURCE_KEYS + ((STATE_SOURCE_KEY,) if include_state else ())
                )
            ),
            Entity.id.notin_(already_tagged),
        )
        .options(selectinload(Entity.bill))
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def backfill_local_bill_tags(limit: int | None = None, *, include_state: bool = False) -> tuple[int, int]:
    """Returns (succeeded, failed) counts."""
    _check_ollama_reachable()

    db = SessionLocal()
    succeeded = failed = 0
    try:
        candidates = select_local_bills_needing_tags(db, limit=limit, include_state=include_state)
        logger.info("Backfilling topic tags for %d bills", len(candidates))

        for entity in candidates:
            description = entity.bill.description if entity.bill else ""
            try:
                kind = STATE_KIND if STATE_SOURCE_KEY in (entity.external_ids or {}) else LOCAL_KIND
                tags = tag_local_bill(db, entity.id, title=entity.name, description=description or "", kind=kind)
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
    parser.add_argument(
        "--include-state",
        action="store_true",
        help="Also classify state (LegiScan) bills, whose LegiScan subjects are empty.",
    )
    args = parser.parse_args()

    ok, bad = backfill_local_bill_tags(limit=args.limit, include_state=args.include_state)
    print(f"\nDone: {ok} tagged, {bad} failed.")
