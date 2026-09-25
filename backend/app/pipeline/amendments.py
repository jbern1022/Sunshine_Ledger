"""Amendment timeline entries (LegiScan `amendments` field on getBill).

Deliberately split from amendment *text* fetching, the same way bill_text.py
is split from ordinary ingestion: the amendments array on a getBill response
already carries enough metadata (date, chamber, adopted, title) for a
timeline entry at no extra API cost, so that part runs on every ingest.
Fetching the actual amendment document (for the diff view) costs one extra
LegiScan call per amendment and is not wired into ingestion -- see
fetch_amendment_text / backfill_amendment_texts, an opt-in step mirroring
backfill_bill_texts.

Response shape verified 2026-09-15 against live FL bills (HB 175, amendment
278267 among others), not just LegiScan's documentation:
- `chamber` is a short code ("H"/"S"), not a full name -- CHAMBER_MAP below.
- `description` is routinely an empty string; `title` (e.g. "House
  Committee Amendment #337249") is what actually carries the label, same
  as RollCallOut already does with `description=event.title` for votes.
- `getAmendment` returns {"amendment": {..., "mime", "doc" (base64)}},
  same document-API family as getBillText -- extract_pdf_text /
  extract_html_text apply unchanged. Confirmed against a real 264KB PDF
  amendment (extracted cleanly to ~70KB of "Remove everything after the
  enacting clause and insert:..." style strike-and-insert text -- exactly
  the "gutting amendment" case the diff view exists to make visible).
"""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.logging_setup import quiet_http_logging
from app.models import Entity, Event
from app.pipeline.bill_text import extract_html_text, extract_pdf_text
from app.pipeline.legiscan import LegiScanClient, api_usage_summary

logger = logging.getLogger(__name__)

CHAMBER_MAP = {"H": "House", "S": "Senate"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def sync_bill_amendments(db: Session, *, bill_entity: Entity, amendments: list[dict]) -> int:
    """Upsert one AMENDED Event per amendment stub from a getBill response.

    Idempotent on amendment_id: re-running ingestion for an unchanged bill
    (which already short-circuits before calling this, via the
    change_hash check in ingest_state_bills) or a bill whose change_hash
    changed for an unrelated reason won't duplicate timeline rows.

    Returns the number of new events written.
    """
    existing_ids = {
        e.attributes.get("amendment_id")
        for e in db.execute(
            select(Event).where(Event.entity_id == bill_entity.id, Event.event_type == "AMENDED")
        ).scalars()
    }

    written = 0
    for amendment in amendments:
        amendment_id = amendment.get("amendment_id")
        if amendment_id is None or amendment_id in existing_ids:
            continue

        event_date = _parse_date(amendment.get("date")) or date.today()
        raw_chamber = amendment.get("chamber")
        chamber = CHAMBER_MAP.get(raw_chamber, raw_chamber)
        adopted = bool(amendment.get("adopted"))
        title = amendment.get("title") or "Amendment"

        db.add(
            Event(
                entity_id=bill_entity.id,
                event_type="AMENDED",
                event_date=event_date,
                title=title,
                attributes={
                    "amendment_id": amendment_id,
                    "chamber": chamber,
                    "adopted": adopted,
                },
            )
        )
        written += 1

    if written:
        db.flush()
    return written


def fetch_amendment_text(client: LegiScanClient, amendment_id: int) -> str | None:
    """Fetch and clean one amendment's document text (opt-in, costs one
    LegiScan call). Mirrors fetch_bill_text's PDF/HTML handling -- LegiScan
    documents both come from the same document-API family, confirmed live
    (see module docstring).
    """
    doc = client.get_amendment(amendment_id)
    mime = doc.get("mime")
    raw = base64.b64decode(doc["doc"]) if doc.get("doc") else None
    if not raw:
        return None

    if mime == "application/pdf":
        return extract_pdf_text(raw)
    if mime in ("text/html", "application/html"):
        return extract_html_text(raw)

    logger.warning("Unrecognized amendment mime type %r for amendment_id=%s", mime, amendment_id)
    return None


def backfill_amendment_texts(db: Session, *, limit: int | None = None, refresh: bool = False) -> tuple[int, int]:
    """Populate `amendment_text` on AMENDED events that don't have it yet.

    One getAmendment call per amendment, so it spends real API quota --
    same reasoning as backfill_bill_texts, hence skipping amendments that
    already have text unless `refresh` is set. Stored on the event's
    `attributes` JSONB (amendment_text key) rather than a dedicated column:
    this is a per-event attribute like everything else already on Event,
    and doesn't warrant its own migration.

    Returns (fetched, skipped_or_failed).
    """
    client = LegiScanClient()

    stmt = select(Event).where(Event.event_type == "AMENDED").options(selectinload(Event.entity))
    events = [
        e for e in db.execute(stmt).scalars().all() if refresh or not e.attributes.get("amendment_text")
    ]
    if limit:
        events = events[:limit]

    logger.info("Fetching amendment text for %d amendments", len(events))

    fetched = failed = 0
    for event in events:
        amendment_id = event.attributes.get("amendment_id")
        if not amendment_id:
            failed += 1
            continue

        try:
            text = fetch_amendment_text(client, int(amendment_id))
            if not text:
                failed += 1
                continue

            event.attributes = {**event.attributes, "amendment_text": text}
            db.commit()
            fetched += 1
        except Exception as exc:  # noqa: BLE001 -- one bad amendment shouldn't kill the backfill
            db.rollback()
            failed += 1
            logger.warning("Amendment text fetch failed for amendment_id=%s: %s", amendment_id, exc)

    logger.info("Amendment text: %d fetched, %d skipped/failed", fetched, failed)
    return fetched, failed


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch amendments that already have text.")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        ok, bad = backfill_amendment_texts(session, limit=args.limit, refresh=args.refresh)
        print(f"Done: {ok} fetched, {bad} skipped/failed.")
    finally:
        session.close()
        print(api_usage_summary())
