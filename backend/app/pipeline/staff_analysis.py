"""Ingest Florida legislative-staff bill analyses as legislative-intent
context (Roadmap: subtask of "rhetoric-vs-substance comparison" -- the
cheapest, no-new-data-source slice, since these are nonpartisan staff
documents rather than sponsor rhetoric specifically).

Discovery: LegiScan's `getBill` response includes a `supplements` array.
Every real Florida analysis entry in it carries `title == "Analysis"` --
confirmed by sampling 25 live FL bills 2026-09-21, where every supplement
matched that shape and LegiScan's own `type`/`type_id` fields were uniformly
"Veto Letter"/8 (a LegiScan taxonomy quirk, not a real veto letter). No
scraper against flsenate.gov/myfloridahouse.gov is needed or used.

Retrieval: through LegiScan's `getSupplement` op, not the supplement's own
`state_link` -- that URL soft-404s (200 status, HTML error page instead of
the PDF) for older/rotated links, confirmed 2026-09-21 against a real
analysis URL. `getSupplement` returns the same PDF base64-encoded and is the
same op family already used for bill text and amendments.

One bill can carry several analyses over its life (one per committee stop),
so ingestion is additive -- see models/staff_analysis.py.
"""

from __future__ import annotations

import base64
import html
import io
import logging
import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.models import Bill, Entity, StaffAnalysis
from app.pipeline.legiscan import LegiScanClient

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

# The nav footer LegiScan's House/Senate analysis PDFs repeat on every page,
# e.g. "JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION BILL HISTORY".
_NAV_FOOTER = re.compile(r"^\s*JUMP TO SUMMARY.*BILL HISTORY\s*$", re.IGNORECASE)

# A page-number-only line, e.g. " 2 ". Real analysis prose never appears as
# a bare digit on its own line, unlike a filed bill PDF's trailing line
# numbers, so this can be dropped outright rather than needing the
# sequence-aware check bill_text.py's cleaner uses.
_BARE_PAGE_NUMBER = re.compile(r"^\s*\d{1,3}\s*$")


def clean_analysis_text(raw: str) -> str:
    """Strip the repeating nav-footer and bare page-number lines from a
    staff analysis PDF's extracted text.

    Deliberately light-touch compared to bill_text.py's cleaner: the layout
    here is plain prose with footnotes, not a line-numbered filed bill, so
    there's no per-line numbering to reconstruct and footnote markers/text
    are real content to keep, not furniture to strip.
    """
    cleaned: list[str] = []
    for line in raw.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        if _NAV_FOOTER.match(line) or _BARE_PAGE_NUMBER.match(line):
            continue
        cleaned.append(line.strip())
    return "\n".join(cleaned)


def extract_analysis_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader  # imported lazily, same reasoning as bill_text.py

    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    return clean_analysis_text(raw)


def is_staff_analysis(supplement: dict) -> bool:
    """Whether a LegiScan `supplements` entry is a staff analysis.

    `title == "Analysis"` is the reliable signal -- see module docstring on
    why `type`/`type_id` aren't."""
    return supplement.get("title") == "Analysis"


def backfill_staff_analyses(db: Session, *, limit: int | None = None) -> tuple[int, int]:
    """Populate `staff_analyses` for FL LegiScan bills.

    One `getBill` call per bill already-ingested (to discover any new
    supplements) plus one `getSupplement` call per not-yet-stored analysis,
    so this spends real API quota -- same cost shape as backfill_bill_texts.

    Returns (fetched, skipped_or_failed).
    """
    client = LegiScanClient()

    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.source_system == "legiscan")
        .options(selectinload(Entity.bill))
    )
    entities = list(db.execute(stmt).scalars().all())
    if limit:
        entities = entities[:limit]

    known_ids = {
        row[0] for row in db.execute(select(StaffAnalysis.legiscan_supplement_id)).all()
    }

    logger.info("Checking %d bills for staff analyses", len(entities))

    fetched = failed = 0
    for entity in entities:
        legiscan_id = (entity.external_ids or {}).get("legiscan_id")
        if not legiscan_id:
            continue

        try:
            detail = client.get_bill(int(legiscan_id))
        except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the backfill
            failed += 1
            logger.warning("getBill failed for legiscan_id=%s: %s", legiscan_id, exc)
            continue

        for supp in detail.get("supplements") or []:
            if not is_staff_analysis(supp):
                continue
            supplement_id = supp.get("supplement_id")
            if not supplement_id or supplement_id in known_ids:
                continue

            try:
                doc = client.get_supplement(int(supplement_id))
                raw = base64.b64decode(doc["doc"])
                if doc.get("mime") != "application/pdf":
                    logger.warning(
                        "supplement_id=%s has unsupported mime %s -- skipping",
                        supplement_id, doc.get("mime"),
                    )
                    failed += 1
                    continue

                text = extract_analysis_pdf_text(raw)

                db.execute(
                    pg_insert(StaffAnalysis)
                    .values(
                        entity_id=entity.id,
                        legiscan_supplement_id=int(supplement_id),
                        committee=html.unescape(supp.get("description") or "") or None,
                        analysis_date=_parse_date(supp.get("date")),
                        source_url=supp.get("state_link") or supp.get("url"),
                        legiscan_url=supp.get("url"),
                        text=text,
                    )
                    .on_conflict_do_nothing(index_elements=["legiscan_supplement_id"])
                )
                db.commit()
                known_ids.add(supplement_id)
                fetched += 1
            except Exception as exc:  # noqa: BLE001 -- one bad document shouldn't kill the backfill
                db.rollback()
                failed += 1
                logger.warning("Supplement fetch failed for supplement_id=%s: %s", supplement_id, exc)

    logger.info("Staff analyses: %d fetched, %d skipped/failed", fetched, failed)
    return fetched, failed


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        ok, bad = backfill_staff_analyses(session, limit=args.limit)
        print(f"Done: {ok} fetched, {bad} skipped/failed.")
    finally:
        session.close()
