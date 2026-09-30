"""Fetch bill text using the session dataset's document lists.

Each document comes from flsenate.gov when it can (its `state_link` in the
dataset; no LegiScan call, ~10 s each) and otherwise from LegiScan, one
getBillText / getSupplement each. The dataset download is 2 calls and tells
us every bill's documents for free. `--max-calls` caps LegiScan calls and
`--max-documents` caps flsenate.gov fetches; what's left waits for a rerun.

- --latest: bills with no text yet get their latest version as
  bills.full_text, passed bills first.
- --staff-analyses: committee staff analyses not stored yet, passed bills
  first. The dataset lists every bill's supplements, so this skips the
  getBill per bill that staff_analysis.backfill_staff_analyses pays.
- --amendments: text of amendments whose timeline entry has none yet
  (for the amendment diff view), passed bills first; also records each
  one's flsenate.gov link.
- default: the filed (first) text version of bills that were amended.

Bill.full_text holds a bill's latest version; showing "what changed from
the filed bill to the version that passed" also needs the first, and only
bills with more than one version have one to fetch. Stored documents are
skipped, so a rerun fetches only what's left.

    python -m app.pipeline.text_versions --session "2026 Regular Session" --dry-run
    python -m app.pipeline.text_versions --session "2026 Regular Session" --max-calls 0 --max-documents 300
    python -m app.pipeline.text_versions --session "2025 Regular Session" --staff-analyses --dry-run
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillTextVersion, Entity, Event
from app.pipeline import flsenate, legiscan
from app.pipeline.legiscan import LegiScanClient, report_api_usage

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except ValueError:
        return None


def filed_versions_to_fetch(db: Session, bills: dict[int, dict]) -> list[tuple[Entity, dict]]:
    """(stored bill entity, first texts[] entry) for dataset bills with more
    than one text version whose first version isn't stored yet."""
    stored_docs = {row[0] for row in db.execute(select(BillTextVersion.legiscan_doc_id))}
    entities = {
        e.external_ids["legiscan_id"]: e
        for e in db.execute(select(Entity).where(Entity.external_ids.has_key("legiscan_id"))).scalars()
    }
    todo = []
    for bill_id, bill in sorted(bills.items()):
        texts = bill.get("texts") or []
        entity = entities.get(str(bill_id))
        if len(texts) < 2 or entity is None:
            continue
        first = texts[0]
        if int(first["doc_id"]) in stored_docs or first["doc_id"] == texts[-1]["doc_id"]:
            continue
        todo.append((entity, first))
    return todo


def backfill_filed_versions(db: Session, bills: dict[int, dict], client, *, max_calls: int) -> tuple[int, int, int]:
    """Fetch and store filed versions; at most `max_calls` of them through
    LegiScan. Returns (stored, failed, left for a later run)."""
    from app.pipeline.bill_text import NeedsLegiScan, fetch_text_document, text_version_meta  # bill_text imports legiscan

    todo = filed_versions_to_fetch(db, bills)
    start = sum(legiscan.API_CALLS.values())
    stored = failed = left = 0
    for index, (entity, first) in enumerate(todo):
        try:
            text = fetch_text_document(client, first, fallback=sum(legiscan.API_CALLS.values()) - start < max_calls)
        except flsenate.BudgetExhausted:
            return stored, failed, left + len(todo) - index
        except NeedsLegiScan:
            left += 1
            continue
        except Exception as exc:  # noqa: BLE001 -- one bad document shouldn't stop the run
            logger.warning("doc_id=%s failed: %s", first["doc_id"], exc)
            failed += 1
            continue
        if not text:
            failed += 1
            continue
        db.add(
            BillTextVersion(
                bill_entity_id=entity.id,
                legiscan_doc_id=int(first["doc_id"]),
                version_type=first.get("type"),
                version_date=_parse_date(first.get("date")),
                text=text,
            )
        )
        entity.external_ids = {**entity.external_ids, "filed_text_url": text_version_meta(first)["url"]}
        db.commit()
        stored += 1
    return stored, failed, left


def latest_text_to_fetch(db: Session, bills: dict[int, dict]) -> list[tuple[Entity, dict]]:
    """(stored bill entity, latest texts[] entry) for dataset bills we hold
    without full_text. Passed bills first (LegiScan status 4), then the rest."""
    from app.models import Bill

    entities = {
        e.external_ids["legiscan_id"]: e
        for e in db.execute(
            select(Entity).join(Bill, Bill.entity_id == Entity.id).where(
                Entity.external_ids.has_key("legiscan_id"), Bill.full_text.is_(None)
            )
        ).scalars()
    }
    todo = [
        (entities[str(bill_id)], bill["texts"][-1], bill.get("status") == 4)
        for bill_id, bill in sorted(bills.items())
        if bill.get("texts") and str(bill_id) in entities
    ]
    todo.sort(key=lambda item: not item[2])  # stable: passed bills first
    return [(entity, latest) for entity, latest, _ in todo]


def backfill_latest_text(db: Session, bills: dict[int, dict], client, *, max_calls: int) -> tuple[int, int, int]:
    """Set bills.full_text from each bill's latest document and record its
    doc id (so nightly sync knows it's current); at most `max_calls` through
    LegiScan. Returns (stored, failed, left)."""
    from app.pipeline.bill_text import NeedsLegiScan, fetch_text_document, text_version_meta

    todo = latest_text_to_fetch(db, bills)
    start = sum(legiscan.API_CALLS.values())
    stored = failed = left = 0
    for index, (entity, latest) in enumerate(todo):
        try:
            text = fetch_text_document(client, latest, fallback=sum(legiscan.API_CALLS.values()) - start < max_calls)
        except flsenate.BudgetExhausted:
            return stored, failed, left + len(todo) - index
        except NeedsLegiScan:
            left += 1
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("doc_id=%s failed: %s", latest["doc_id"], exc)
            failed += 1
            continue
        if not text:
            failed += 1
            continue
        entity.bill.full_text = text
        entity.external_ids = {
            **entity.external_ids,
            "legiscan_text_doc_id": str(latest["doc_id"]),
            "text_version": text_version_meta(latest),
        }
        db.commit()
        stored += 1
    return stored, failed, left


# House analysis file names: h0117.CRJ.PDF, h0117a.CRJ.PDF, ..., h0117z.CRJ.PDF,
# h0117z1.CRJ.PDF -- bill, revision (none, a-y, then z for the final analysis
# and z1, z2 for its revisions), committee. The House publishes only the
# latest revision per committee; LegiScan still lists the earlier ones, whose
# links soft-404 (815 of 820 flsenate.gov failures on 2026-09-29 had a later
# revision of the same committee stored).
_HOUSE_ANALYSIS = re.compile(r"/h\d+([a-z]?)(\d*)\.([A-Za-z0-9]+)\.PDF$", re.IGNORECASE)


def _house_revision(supp: dict) -> tuple[str, tuple[str, int]] | None:
    """(committee, sortable revision) for a House analysis link, else None."""
    match = _HOUSE_ANALYSIS.search(supp.get("state_link") or "")
    if not match:
        return None
    letter, number, committee = match.groups()
    return committee.upper(), (letter.lower(), int(number or 0))


def _drop_superseded(supplements: list[dict]) -> list[dict]:
    """One bill's supplements without House analyses that a later revision
    for the same committee replaced."""
    latest: dict[str, tuple[str, int]] = {}
    for supp in supplements:
        rev = _house_revision(supp)
        if rev and rev[1] > latest.get(rev[0], ("", -1)):
            latest[rev[0]] = rev[1]
    return [s for s in supplements if (rev := _house_revision(s)) is None or latest[rev[0]] == rev[1]]


def staff_analyses_to_fetch(db: Session, bills: dict[int, dict]) -> list[tuple[Entity, dict]]:
    """(stored bill entity, supplement) for dataset staff analyses we don't
    hold yet, passed bills first. Superseded House revisions are skipped:
    they're no longer published, and the latest one is fetched instead."""
    from app.models import StaffAnalysis
    from app.pipeline.staff_analysis import is_staff_analysis

    known = {row[0] for row in db.execute(select(StaffAnalysis.legiscan_supplement_id))}
    entities = {
        e.external_ids["legiscan_id"]: e
        for e in db.execute(select(Entity).where(Entity.external_ids.has_key("legiscan_id"))).scalars()
    }
    todo = [
        (entities[str(bill_id)], supp, bill.get("status") == 4)
        for bill_id, bill in sorted(bills.items())
        if str(bill_id) in entities
        for supp in _drop_superseded([s for s in bill.get("supplements") or [] if is_staff_analysis(s)])
        if supp.get("supplement_id") and supp["supplement_id"] not in known
    ]
    todo.sort(key=lambda item: not item[2])  # stable: passed bills first
    return [(entity, supp) for entity, supp, _ in todo]


def backfill_staff_analyses(db: Session, bills: dict[int, dict], client, *, max_calls: int) -> tuple[int, int, int]:
    """Store missing staff analyses; at most `max_calls` of them through
    LegiScan (getSupplement). Returns (stored, failed, left)."""
    from app.pipeline import staff_analysis
    from app.pipeline.bill_text import NeedsLegiScan

    todo = staff_analyses_to_fetch(db, bills)
    known: set[int] = set()
    start = sum(legiscan.API_CALLS.values())
    stored = failed = left = 0
    for index, (entity, supp) in enumerate(todo):
        try:
            ok, bad = staff_analysis.store_new_staff_analyses(
                db, client, entity=entity, supplements=[supp], known_ids=known,
                fallback=sum(legiscan.API_CALLS.values()) - start < max_calls,
            )
        except flsenate.BudgetExhausted:
            return stored, failed, left + len(todo) - index
        except NeedsLegiScan:
            left += 1
            continue
        stored += ok
        failed += bad
    return stored, failed, left


def amendment_texts_to_fetch(db: Session, bills: dict[int, dict]) -> list[tuple[Event, dict]]:
    """(stored AMENDED event, dataset amendment) for amendments of dataset
    bills whose event has no amendment_text yet, passed bills first."""
    status = {
        str(a["amendment_id"]): bill.get("status") == 4
        for bill in bills.values()
        for a in bill.get("amendments") or []
        if a.get("amendment_id")
    }
    amendments = {str(a["amendment_id"]): a for bill in bills.values() for a in bill.get("amendments") or []}
    todo = [
        (event, amendments[str(event.attributes.get("amendment_id"))])
        for event in db.execute(select(Event).where(Event.event_type == "AMENDED")).scalars()
        if not event.attributes.get("amendment_text") and str(event.attributes.get("amendment_id")) in amendments
    ]
    todo.sort(key=lambda item: (not status[str(item[1]["amendment_id"])], int(item[1]["amendment_id"])))
    return todo


def backfill_amendment_texts(db: Session, bills: dict[int, dict], client, *, max_calls: int) -> tuple[int, int, int]:
    """Store missing amendment texts (and each one's flsenate.gov link); at
    most `max_calls` through LegiScan. Returns (stored, failed, left)."""
    from app.pipeline.amendments import fetch_amendment_text
    from app.pipeline.bill_text import NeedsLegiScan

    todo = amendment_texts_to_fetch(db, bills)
    start = sum(legiscan.API_CALLS.values())
    stored = failed = left = 0
    for index, (event, amendment) in enumerate(todo):
        try:
            text = fetch_amendment_text(
                client, int(amendment["amendment_id"]), state_link=amendment.get("state_link"),
                fallback=sum(legiscan.API_CALLS.values()) - start < max_calls,
            )
        except flsenate.BudgetExhausted:
            return stored, failed, left + len(todo) - index
        except NeedsLegiScan:
            left += 1
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("amendment_id=%s failed: %s", amendment["amendment_id"], exc)
            failed += 1
            continue
        if not text:
            failed += 1
            continue
        link = {"state_link": amendment["state_link"]} if amendment.get("state_link") else {}
        event.attributes = {**event.attributes, **link, "amendment_text": text}
        db.commit()
        stored += 1
    return stored, failed, left


def record_version_meta(db: Session, bills: dict[int, dict]) -> int:
    """Label stored texts from the dataset, for bills fetched before labels
    were recorded: the current version's type/date/official link (only when
    the stored doc id matches one of the bill's documents) and the filed
    version's official link. No document fetches. Returns bills updated."""
    from app.pipeline.bill_text import text_version_meta

    filed = {row[0]: row[1] for row in db.execute(select(BillTextVersion.bill_entity_id, BillTextVersion.legiscan_doc_id))}
    entities = {
        e.external_ids["legiscan_id"]: e
        for e in db.execute(select(Entity).where(Entity.external_ids.has_key("legiscan_id"))).scalars()
    }
    updated = 0
    for bill_id, bill in bills.items():
        entity = entities.get(str(bill_id))
        texts = bill.get("texts") or []
        if entity is None or not texts:
            continue
        by_doc = {str(t["doc_id"]): t for t in texts}
        extra = {}
        current = by_doc.get(str(entity.external_ids.get("legiscan_text_doc_id")))
        if current:
            extra["text_version"] = text_version_meta(current)
        first = by_doc.get(str(filed.get(entity.id)))
        if first:
            extra["filed_text_url"] = text_version_meta(first)["url"]
        if extra and any(entity.external_ids.get(k) != v for k, v in extra.items()):
            entity.external_ids = {**entity.external_ids, **extra}
            updated += 1
    db.commit()
    return updated


if __name__ == "__main__":
    import argparse

    from app.config import settings
    from app.db import SessionLocal
    from app.logging_setup import quiet_http_logging
    from app.pipeline.legiscan_dataset import DatasetClient, fetch_session_dataset

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", required=True, help='e.g. "2026 Regular Session"')
    parser.add_argument("--max-calls", type=int, default=1500)
    parser.add_argument("--max-documents", type=int, default=None, help="Cap flsenate.gov fetches (10 s each).")
    parser.add_argument("--dry-run", action="store_true", help="Count what would be fetched; 2 calls for the dataset.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--latest", action="store_true", help="Fill missing bills.full_text instead (passed bills first).")
    mode.add_argument("--staff-analyses", action="store_true", help="Fetch missing staff analyses (passed bills first).")
    mode.add_argument("--amendments", action="store_true", help="Fetch missing amendment texts (passed bills first).")
    mode.add_argument("--version-meta", action="store_true", help="Label stored texts' versions from the dataset (no fetches).")
    args = parser.parse_args()

    flsenate.set_budget(args.max_documents)
    api = LegiScanClient()
    dataset = DatasetClient(fetch_session_dataset(api, settings.legiscan_state, args.session), fallback=api)
    session = SessionLocal()
    try:
        if args.version_meta:
            print(f"{args.session}: labelled {record_version_meta(session, dataset.bills)} bills' text versions.")
            raise SystemExit(0)
        if args.latest:
            pick, run, what = latest_text_to_fetch, backfill_latest_text, "missing bill texts"
        elif args.staff_analyses:
            pick, run, what = staff_analyses_to_fetch, backfill_staff_analyses, "missing staff analyses"
        elif args.amendments:
            pick, run, what = amendment_texts_to_fetch, backfill_amendment_texts, "missing amendment texts"
        else:
            pick, run, what = filed_versions_to_fetch, backfill_filed_versions, "filed versions"
        if args.dry_run:
            print(f"{args.session}: {len(pick(session, dataset.bills))} {what} to fetch (flsenate.gov first, LegiScan as the fallback).")
        else:
            stored, failed, left = run(session, dataset.bills, api, max_calls=args.max_calls)
            print(f"{args.session}: stored {stored}, failed {failed}, left for a later run {left}.")
    finally:
        print(report_api_usage(session))
        session.close()
