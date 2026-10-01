"""Amendment timeline entries (LegiScan `amendments` field on getBill).

Deliberately split from amendment *text* fetching, the same way bill_text.py
is split from ordinary ingestion: the amendments array on a getBill response
already carries enough metadata (date, chamber, adopted, title) for a
timeline entry at no extra API cost, so that part runs on every ingest.
Fetching the actual amendment document (for the diff view) is not wired
into ingestion -- see fetch_amendment_text / backfill_amendment_texts, an
opt-in step mirroring backfill_bill_texts. The document comes from its
flsenate.gov `state_link` (recorded on the event; verified 2026-09-29 to
extract identically), with one LegiScan getAmendment call as the fallback.

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
import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.logging_setup import quiet_http_logging
from app.models import Entity, Event
from app.pipeline.bill_text import extract_html_text, extract_pdf_text
from app.pipeline.text_cleanup import strip_amendment_furniture
from app.pipeline.legiscan import LegiScanClient, report_api_usage

logger = logging.getLogger(__name__)

CHAMBER_MAP = {"H": "House", "S": "Senate"}
_TITLE_NUMBER = re.compile(r"#\s*(\d{5,7})\b")


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
    existing = db.execute(
        select(Event).where(Event.entity_id == bill_entity.id, Event.event_type == "AMENDED")
    ).scalars().all()
    existing_ids = {e.attributes.get("amendment_id") for e in existing}
    # Amendments first found on flsenate.gov (flsenate_amendments.py) have no
    # LegiScan id; LegiScan's later record for the same number joins them.
    flsenate_only = {
        str(e.attributes["amendment_number"]): e
        for e in existing
        if e.attributes.get("amendment_number") and not e.attributes.get("amendment_id")
    }

    written = 0
    for amendment in amendments:
        amendment_id = amendment.get("amendment_id")
        if amendment_id is None or amendment_id in existing_ids:
            continue
        number = _TITLE_NUMBER.search(amendment.get("title") or "")
        twin = flsenate_only.get(number.group(1)) if number else None
        if twin is not None:
            # The official last action (flsenate.gov) keeps deciding adoption.
            twin.attributes = {**twin.attributes, "amendment_id": amendment_id, "legiscan_adopted": bool(amendment.get("adopted"))}
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
                    **({"state_link": amendment["state_link"]} if amendment.get("state_link") else {}),
                },
            )
        )
        written += 1

    if written:
        db.flush()
    return written


def fetch_amendment_text(
    client: LegiScanClient, amendment_id: int, *, state_link: str | None = None, fallback: bool = True
) -> str | None:
    """Fetch and clean one amendment's document text: from flsenate.gov when
    there's a `state_link`, otherwise -- or when that fails -- one LegiScan
    call, unless `fallback` is off (then NeedsLegiScan). Mirrors
    fetch_bill_text's PDF/HTML handling -- LegiScan documents both come from
    the same document-API family, confirmed live (see module docstring).
    """
    from app.pipeline import flsenate
    from app.pipeline.bill_text import NeedsLegiScan

    if state_link:
        try:
            body, kind = flsenate.fetch_document(state_link)
            return strip_amendment_furniture(extract_pdf_text(body) if kind == "pdf" else extract_html_text(body))
        except flsenate.BudgetExhausted:
            raise
        except Exception as exc:  # noqa: BLE001 -- LegiScan has the same document
            logger.info("flsenate.gov failed for amendment_id=%s (%s)", amendment_id, exc)
    if not fallback:
        raise NeedsLegiScan(amendment_id)
    doc = client.get_amendment(amendment_id)
    mime = doc.get("mime")
    raw = base64.b64decode(doc["doc"]) if doc.get("doc") else None
    if not raw:
        return None

    if mime == "application/pdf":
        return strip_amendment_furniture(extract_pdf_text(raw))
    if mime in ("text/html", "application/html"):
        return strip_amendment_furniture(extract_html_text(raw))

    logger.warning("Unrecognized amendment mime type %r for amendment_id=%s", mime, amendment_id)
    return None


def backfill_amendment_texts(db: Session, *, limit: int | None = None, refresh: bool = False) -> tuple[int, int]:
    """Populate `amendment_text` on AMENDED events that don't have it yet.

    flsenate.gov first when the event has a `state_link`, else one
    getAmendment call -- real API quota, hence skipping amendments that
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
        state_link = event.attributes.get("state_link")
        if not amendment_id and not state_link:
            failed += 1
            continue

        try:
            # flsenate-only amendments have no LegiScan id to fall back on.
            text = fetch_amendment_text(
                client, int(amendment_id) if amendment_id else 0, state_link=state_link, fallback=bool(amendment_id)
            )
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


def clean_stored_amendment_texts(db: Session, *, apply: bool = False) -> tuple[int, int]:
    """Strip amendment form furniture from already-stored amendment text
    (no API calls). Dry run unless `apply`. Returns (changed, checked)."""
    events = db.execute(select(Event).where(Event.event_type == "AMENDED")).scalars().all()
    changed = checked = 0
    for event in events:
        text = event.attributes.get("amendment_text")
        if not text:
            continue
        checked += 1
        cleaned = strip_amendment_furniture(text)
        if cleaned != text:
            changed += 1
            if apply:
                event.attributes = {**event.attributes, "amendment_text": cleaned}
    if apply:
        db.commit()
    return changed, checked


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch amendments that already have text.")
    parser.add_argument(
        "--clean-stored",
        action="store_true",
        help="Strip form furniture from stored amendment text (no API calls). Dry run unless --apply.",
    )
    parser.add_argument("--apply", action="store_true", help="With --clean-stored: write the cleaned text.")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.clean_stored:
            changed, checked = clean_stored_amendment_texts(session, apply=args.apply)
            print(f"{'Cleaned' if args.apply else 'Would clean'} {changed} of {checked} amendment texts.")
            raise SystemExit(0)
        ok, bad = backfill_amendment_texts(session, limit=args.limit, refresh=args.refresh)
        print(f"Done: {ok} fetched, {bad} skipped/failed.")
    finally:
        print(report_api_usage(session))
        session.close()
