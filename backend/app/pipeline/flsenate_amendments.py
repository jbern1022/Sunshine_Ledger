"""Amendment list, authors and last actions from a bill's flsenate.gov page.

LegiScan's amendment records carry no sponsor and miss some documents:
HB 1389 (2026) has 3 in LegiScan but 5 on flsenate.gov, including the
amendment-to-amendment that rewrote lines 368-420 (checked 2026-10-01).
The bill page's Amendments tab lists every committee and floor amendment
with its number, type, sponsor, filed time, last action and PDF.

The tab is part of the bill page itself (`bills.full_text_url`), so it
costs one flsenate.gov request per bill (10 s crawl delay) and no LegiScan
calls. Records are matched to LegiScan's by the amendment number, which
LegiScan carries in its title ("House Committee Amendment #208403").
Matched events gain the flsenate fields. Where flsenate.gov gives a last
action, it decides `adopted`: LegiScan's flag disagrees with the official
record for some amendments (HB 1389's 208403 "Adopted without Objection"
and the Senate delete-all the House concurred in were both "not adopted"
in LegiScan). LegiScan's value is kept as `legiscan_adopted`. Unmatched
amendments become new AMENDED events with `source: flsenate`.

    python -m app.pipeline.flsenate_amendments --session "2026 Regular Session" [--limit N] [--max-documents N]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Bill, Entity, Event

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"^\s*(\d{5,7})\s*-\s*(.+?)\s*$")
_TITLE_NUMBER = re.compile(r"#\s*(\d{5,7})\b")
_DATE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")
_CHAMBERS = {"H": "House", "S": "Senate"}
# Last actions that mean the amendment became part of the bill. "Not
# adopted", "withdrawn", "failed", "unfavorable" and pending ones don't.
_ADOPTED = re.compile(r"\b(?:adopted|concurred)\b", re.IGNORECASE)
_NOT_ADOPTED = re.compile(r"\bnot adopted\b|withdrawn|failed|unfavorabl|laid on table|ruled out of order", re.IGNORECASE)


@dataclass
class FlAmendment:
    number: str
    label: str           # "Strike All Amendment", "Amendment to Amendment (406455)"
    summary: str | None  # "Remove everything after the enacting clause and insert:"
    sponsor: str | None
    filed: date | None
    last_action: str | None
    last_action_date: date | None
    stage: str           # committee | floor
    bill_version: str | None  # "H 1389 c1"
    chamber: str | None
    pdf_url: str | None

    @property
    def adopted(self) -> bool:
        action = self.last_action or ""
        return bool(_ADOPTED.search(action)) and not _NOT_ADOPTED.search(action)


def _date(text: str | None) -> date | None:
    m = _DATE.search(text or "")
    return datetime.strptime(m.group(1), "%m/%d/%Y").date() if m else None


def _text(node) -> str:
    return " ".join(node.get_text(" ").split()) if node else ""


def parse_amendments(html: str | bytes, *, base_url: str = "https://www.flsenate.gov") -> list[FlAmendment]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[FlAmendment] = []
    for stage, container_id in (("committee", "CommitteeAmendment"), ("floor", "FloorAmendment")):
        container = soup.find(id=container_id)
        if container is None:
            continue
        for table in container.find_all("table"):
            caption = _text(table.find("caption")) or None
            body = table.find("tbody")
            for row in body.find_all("tr", recursive=False) if body else []:
                cells = row.find_all("td", recursive=False)
                if len(cells) < 5:
                    continue
                span = cells[0].find("span")
                summary = _text(span) or None
                if span:
                    span.extract()
                m = _NUMBER.match(_text(cells[0]))
                if not m:
                    continue
                # "House: Concurred as Amended <br/> 3/12/2026": the action
                # can span lines; the date is what follows it.
                action_text = _text(cells[3])
                action_date = _DATE.search(action_text)
                last_action = (action_text[:action_date.start()] if action_date else action_text).strip() or None
                # Prefer the PDF; some rows list a Web Page link first.
                link = cells[4].find("a", href=re.compile(r"/Amendment/.*/PDF")) or cells[4].find("a", href=re.compile(r"/Amendment/"))
                href = link.get("href") if link else None
                chamber = _CHAMBERS.get((link.get("data-chamber") or "").upper()) if link else None
                out.append(FlAmendment(
                    number=m.group(1),
                    label=m.group(2),
                    summary=summary,
                    sponsor=_text(cells[1]) or None,
                    filed=_date(_text(cells[2])),
                    last_action=last_action,
                    last_action_date=_date(action_text),
                    stage=stage,
                    bill_version=caption,
                    chamber=chamber,
                    pdf_url=(base_url + href if href and href.startswith("/") else href),
                ))
    return out


def _number_of(event: Event) -> str | None:
    n = event.attributes.get("amendment_number")
    if n:
        return str(n)
    m = _TITLE_NUMBER.search(event.title or "")
    return m.group(1) if m else None


def merge_amendments(db: Session, bill_entity: Entity, amendments: list[FlAmendment]) -> tuple[int, int]:
    """Attach flsenate fields to matching AMENDED events and add the ones
    LegiScan doesn't have. Idempotent. Returns (updated, added)."""
    events = db.execute(
        select(Event).where(Event.entity_id == bill_entity.id, Event.event_type == "AMENDED")
    ).scalars().all()
    by_number = {n: e for e in events if (n := _number_of(e))}
    updated = added = 0
    for a in amendments:
        fields = {
            "amendment_number": a.number,
            "label": a.label,
            "summary": a.summary,
            "sponsor": a.sponsor,
            "stage": a.stage,
            "bill_version": a.bill_version,
            "last_action": a.last_action,
            "last_action_date": a.last_action_date.isoformat() if a.last_action_date else None,
            "flsenate_pdf": a.pdf_url,
        }
        fields = {k: v for k, v in fields.items() if v is not None}
        event = by_number.get(a.number)
        if event is not None:
            merged = {**event.attributes, **fields}
            if a.last_action:
                from_legiscan = event.attributes.get("source") != "flsenate" and "adopted" in event.attributes
                if from_legiscan and "legiscan_adopted" not in merged:
                    merged["legiscan_adopted"] = event.attributes["adopted"]
                merged["adopted"] = a.adopted
            if not merged.get("state_link") and a.pdf_url:
                merged["state_link"] = a.pdf_url
            if not merged.get("chamber") and a.chamber:
                merged["chamber"] = a.chamber
            if merged != event.attributes:
                event.attributes = merged
                updated += 1
            continue
        chamber = a.chamber or ""
        event = Event(
            entity_id=bill_entity.id,
            event_type="AMENDED",
            event_date=a.filed or a.last_action_date or date.today(),
            title=f"{chamber} {a.stage.capitalize()} Amendment #{a.number}".strip(),
            attributes={
                **fields,
                "source": "flsenate",
                "chamber": a.chamber,
                "adopted": a.adopted,
                **({"state_link": a.pdf_url} if a.pdf_url else {}),
            },
        )
        db.add(event)
        by_number[a.number] = event
        added += 1
    if updated or added:
        db.flush()
    return updated, added


def _bills(db: Session, session: str) -> list[Entity]:
    return list(db.execute(
        select(Entity).join(Bill, Bill.entity_id == Entity.id)
        .where(Bill.session == session, Bill.source_system == "legiscan", Bill.full_text_url.like("%flsenate.gov/Session/Bill/%"))
        .options(selectinload(Entity.bill))
        .order_by(Bill.bill_number)
    ).scalars().all())


def sync_session(db: Session, session: str, *, limit: int | None = None, skip_done: bool = True) -> dict[str, int]:
    """Fetch each bill page once and merge its amendments. Bills already
    synced (`flsenate_amendments_checked` on the bill entity) are skipped
    unless `skip_done` is off, so a stopped run resumes where it left off."""
    from app.pipeline import flsenate

    counts = {"bills": 0, "updated": 0, "added": 0, "failed": 0}
    for entity in _bills(db, session):
        if skip_done and (entity.attributes or {}).get("flsenate_amendments_checked"):
            continue
        if limit is not None and counts["bills"] >= limit:
            break
        try:
            body, kind = flsenate.fetch_document(entity.bill.full_text_url)
            if kind != "html":
                raise flsenate.NotADocument("bill page was not HTML")
            updated, added = merge_amendments(db, entity, parse_amendments(body))
            entity.attributes = {**(entity.attributes or {}), "flsenate_amendments_checked": date.today().isoformat()}
            db.commit()
        except flsenate.BudgetExhausted:
            break
        except Exception as exc:  # noqa: BLE001 -- one bad page shouldn't stop the run
            db.rollback()
            counts["failed"] += 1
            logger.warning("flsenate amendments failed for %s: %s", entity.bill.bill_number, exc)
            continue
        counts["bills"] += 1
        counts["updated"] += updated
        counts["added"] += added
    return counts


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal
    from app.logging_setup import quiet_http_logging
    from app.pipeline import flsenate

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", required=True, help='e.g. "2026 Regular Session"')
    parser.add_argument("--limit", type=int, default=None, help="Max bills this run.")
    parser.add_argument("--max-documents", type=int, default=None, help="flsenate.gov request budget for this run.")
    parser.add_argument("--recheck", action="store_true", help="Refetch bills already checked.")
    args = parser.parse_args()
    flsenate.set_budget(args.max_documents)
    db = SessionLocal()
    try:
        c = sync_session(db, args.session, limit=args.limit, skip_done=not args.recheck)
        print(f"{args.session}: {c['bills']} bills checked, {c['updated']} amendments updated, "
              f"{c['added']} added from flsenate.gov, {c['failed']} failed.")
        print(flsenate.usage_summary())
    finally:
        db.close()
