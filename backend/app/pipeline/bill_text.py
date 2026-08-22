"""Fetch and clean real bill text from LegiScan (Roadmap: replace the thin
`description` blurb as summarization input).

LegiScan returns bill documents base64-encoded, usually as PDFs of the
filed bill. Those PDFs are laid out for print, so raw extraction is noisy:
every content line carries a trailing line number, and each page repeats a
chamber header, a CODING legend, a document id, and a page marker. Feeding
that to a model wastes context on furniture and invites it to quote line
numbers back. `clean_legislative_text` strips it.

Deliberately does NOT change what the summarizer reads. Swapping the
summarization input from `description` to full text is a material change to
public-facing output and needs the Roadmap's Step 2 quality gate
(`review_summaries.py`) run against real bills first. This module only
fetches and stores; wiring it in is a separate, reviewed step.
"""

from __future__ import annotations

import base64
import io
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Bill, Entity
from app.pipeline.legiscan import LegiScanClient

logger = logging.getLogger(__name__)

# Page furniture that repeats on every page of a filed bill.
_BOILERPLATE = re.compile(
    r"^\s*(?:"
    r"CODING:.*"                          # "CODING: Words stricken are deletions..."
    r"|Page \d+ of \d+"
    r"|(?:[A-Za-z]\s+){3,}[A-Za-z]\s*"    # letter-spaced "F L O R I D A  H O U S E ..."
    r"|[a-z]{1,4}\d+-\d+"                 # document ids like "hb95-00"
    r"|(?:CS/)?(?:HB|SB|HR|SR|HJR|SJR)\s*\d+\s+\d{4}"  # running header "HB 95  2026"
    r")\s*$",
    re.IGNORECASE,
)

# Trailing line number on a content line, e.g. "...effective date. 9"
_TRAILING_LINE_NUMBER = re.compile(r"\s(\d{1,3})\s*$")


def clean_legislative_text(raw: str) -> str:
    """Strip print furniture from extracted bill-PDF text.

    Line numbers are only removed when they continue the expected sequence.
    A blunt "strip any trailing number" rule would corrupt real content --
    statutory references, dollar amounts and dates routinely end a line --
    whereas legislative line numbering runs 1..N in order, so requiring the
    successor value makes a false positive require a genuine coincidence.

    Pure function: no network, no DB, so the parsing rules stay testable
    without hitting LegiScan.
    """
    cleaned: list[str] = []
    expected = 0

    for line in raw.split("\n"):
        line = line.rstrip()
        if not line.strip() or _BOILERPLATE.match(line):
            continue

        match = _TRAILING_LINE_NUMBER.search(line)
        if match and int(match.group(1)) == expected + 1:
            expected = int(match.group(1))
            line = line[: match.start()]

        if line.strip():
            cleaned.append(line.strip())

    return "\n".join(cleaned)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract and clean text from a bill PDF."""
    from pypdf import PdfReader  # imported lazily -- only bill-text runs need it

    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    return clean_legislative_text(raw)


def fetch_bill_text(client: LegiScanClient, doc_id: int) -> str | None:
    """Fetch one document by LegiScan doc_id and return its cleaned text.

    Returns None for document types we can't read rather than raising --
    LegiScan serves some documents as HTML or Word, and one unreadable
    document shouldn't stop a backfill.
    """
    doc = client._call("getBillText", id=str(doc_id))["text"]
    mime = doc.get("mime")
    if mime != "application/pdf":
        logger.warning("doc_id=%s is %s, not PDF -- skipping", doc_id, mime)
        return None

    return extract_pdf_text(base64.b64decode(doc["doc"]))


def backfill_bill_texts(db: Session, *, limit: int | None = None, refresh: bool = False) -> tuple[int, int]:
    """Populate `bills.full_text` for LegiScan bills that don't have it.

    One `getBillText` call per bill, so it spends real API quota (free tier
    is 30,000/month against ~1,900 state bills) -- hence skipping bills that
    already have text unless `refresh` is set.

    Returns (fetched, skipped_or_failed).
    """
    client = LegiScanClient()

    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.source_system == "legiscan")
        .options(selectinload(Entity.bill))
    )
    entities = [
        e for e in db.execute(stmt).scalars().all() if refresh or not (e.bill and e.bill.full_text)
    ]
    if limit:
        entities = entities[:limit]

    logger.info("Fetching bill text for %d bills", len(entities))

    fetched = failed = 0
    for entity in entities:
        bill = entity.bill
        legiscan_id = (entity.external_ids or {}).get("legiscan_id")
        if not legiscan_id:
            failed += 1
            continue

        try:
            detail = client.get_bill(int(legiscan_id))
            docs = detail.get("texts") or []
            if not docs:
                failed += 1
                continue

            # Last entry is the most recent version (LegiScan orders them
            # oldest-first), which is what should be summarized.
            text = fetch_bill_text(client, int(docs[-1]["doc_id"]))
            if not text:
                failed += 1
                continue

            bill.full_text = text
            db.commit()
            fetched += 1
        except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the backfill
            db.rollback()
            failed += 1
            logger.warning("Bill text fetch failed for %s: %s", bill.bill_number if bill else entity.id, exc)

    logger.info("Bill text: %d fetched, %d skipped/failed", fetched, failed)
    return fetched, failed


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch bills that already have text.")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        ok, bad = backfill_bill_texts(session, limit=args.limit, refresh=args.refresh)
        print(f"Done: {ok} fetched, {bad} skipped/failed.")
    finally:
        session.close()
