"""Amendment timeline entries (LegiScan `amendments` field on getBill).

Deliberately split from amendment *text* fetching, the same way bill_text.py
is split from ordinary ingestion: the amendments array on a getBill response
already carries enough metadata (date, chamber, adopted, title) for a
timeline entry at no extra API cost, so that part runs on every ingest.
Fetching the actual amendment document (for the future diff view) costs one
extra LegiScan call per amendment and is not wired in here -- see
fetch_amendment_text, an opt-in backfill step mirroring backfill_bill_texts.
"""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, Event
from app.pipeline.bill_text import extract_html_text, extract_pdf_text
from app.pipeline.legiscan import LegiScanClient

logger = logging.getLogger(__name__)


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
        chamber = amendment.get("chamber") or amendment.get("chamber_id")
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
                    "description": amendment.get("description"),
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
    documents both come from the same document-API family.

    Not hand-verified against a live amendment_id (see
    LegiScanClient.get_amendment); this follows the documented shape.
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
