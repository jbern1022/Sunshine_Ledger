"""Fetch and clean real bill text from LegiScan (Roadmap: replace the thin
`description` blurb as summarization input).

LegiScan returns bill documents base64-encoded in one of two formats, and
both need cleaning before a model sees them:

- PDFs of the filed bill, laid out for print. Every content line carries a
  *trailing* line number, and each page repeats a chamber header, a CODING
  legend, a document id and a page marker.
- HTML documents (roughly half the Florida corpus, Senate resolutions
  especially), which number lines at the *start* and carry a drafting
  stamp instead of per-page furniture.

Feeding either raw to a model wastes context on furniture and invites it
to quote line numbers back.

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

# HTML bill text numbers lines at the START instead, e.g.
# "    2         A resolution designating February 3, 2026..."
# The trailing separator must be optional: bills contain numbered lines with
# no content ("    4  "), and those arrive here already rstripped. Requiring
# whitespace after the digits would fail to match them, break the expected
# sequence, and leave every following line's number embedded in the text.
_LEADING_LINE_NUMBER = re.compile(r"^\s*(\d{1,3})(?:\s|$)")

# Drafting stamp that appears once per HTML document, e.g.
# "8-02178-26                                            20261780__"
_DRAFT_STAMP = re.compile(r"^\s*\d+-\d+-\d+\s+\d+_*\s*$")


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


def clean_html_legislative_text(raw: str) -> str:
    """Strip furniture from the text of an HTML bill document.

    Same job as `clean_legislative_text`, different layout: LegiScan's HTML
    documents number lines at the *start* rather than the end, and carry a
    drafting stamp instead of per-page headers. The sequential check is the
    same idea and exists for the same reason -- a line legitimately opening
    with a number ("2026 Regular Session...") must not lose it.
    """
    cleaned: list[str] = []
    expected = 0

    for line in raw.split("\n"):
        line = line.rstrip()
        if not line.strip() or _DRAFT_STAMP.match(line):
            continue

        match = _LEADING_LINE_NUMBER.match(line)
        if match and int(match.group(1)) == expected + 1:
            expected = int(match.group(1))
            line = line[match.end():]

        if line.strip():
            cleaned.append(line.strip())

    return "\n".join(cleaned)


def extract_html_text(html_bytes: bytes) -> str:
    """Extract and clean text from an HTML bill document.

    Roughly half of LegiScan's Florida documents are served as text/html
    rather than PDF -- Senate resolutions especially. Treating those as
    unreadable would leave those bills falling back to the short blurb for
    no good reason.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="replace"), "html.parser")
    return clean_html_legislative_text(soup.get_text())


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
    raw = base64.b64decode(doc["doc"])

    if mime == "application/pdf":
        return extract_pdf_text(raw)
    if mime in ("text/html", "application/html"):
        return extract_html_text(raw)

    logger.warning("doc_id=%s has unsupported mime %s -- skipping", doc_id, mime)
    return None


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
