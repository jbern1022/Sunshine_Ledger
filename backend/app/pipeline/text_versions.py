"""Fetch bill text using the session dataset's document lists.

Two jobs, both one getBillText per document (the dataset download is 2
calls and tells us every bill's documents for free):

- --latest: bills with no text yet get their latest version as
  bills.full_text, passed bills first. Half the cost of bill_text's
  getBill + getBillText per bill.
- default: the filed (first) text version of bills that were amended.

Bill.full_text holds a bill's latest version; showing "what changed from
the filed bill to the version that passed" also needs the first. Each
bill's version list comes from the session dataset (free after the 2-call
download); only the filed documents themselves cost calls, one getBillText
each, and only for bills with more than one version. Stored versions are
skipped, so a rerun costs nothing extra.

    python -m app.pipeline.text_versions --session "2026 Regular Session" --dry-run
    python -m app.pipeline.text_versions --session "2026 Regular Session" --max-calls 1500
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillTextVersion, Entity
from app.pipeline import legiscan
from app.pipeline.legiscan import LegiScanClient, api_usage_summary

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
    """Fetch and store filed versions, stopping at `max_calls` LegiScan
    calls. Returns (stored, failed, left for a later run)."""
    from app.pipeline.bill_text import fetch_bill_text  # bill_text imports legiscan

    todo = filed_versions_to_fetch(db, bills)
    start = sum(legiscan.API_CALLS.values())
    stored = failed = 0
    for index, (entity, first) in enumerate(todo):
        if sum(legiscan.API_CALLS.values()) - start >= max_calls:
            return stored, failed, len(todo) - index
        try:
            text = fetch_bill_text(client, int(first["doc_id"]))
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
        db.commit()
        stored += 1
    return stored, failed, 0


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
    doc id (so nightly sync knows it's current). Stops at `max_calls`.
    Returns (stored, failed, left)."""
    from app.pipeline.bill_text import fetch_bill_text

    todo = latest_text_to_fetch(db, bills)
    start = sum(legiscan.API_CALLS.values())
    stored = failed = 0
    for index, (entity, latest) in enumerate(todo):
        if sum(legiscan.API_CALLS.values()) - start >= max_calls:
            return stored, failed, len(todo) - index
        try:
            text = fetch_bill_text(client, int(latest["doc_id"]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("doc_id=%s failed: %s", latest["doc_id"], exc)
            failed += 1
            continue
        if not text:
            failed += 1
            continue
        entity.bill.full_text = text
        entity.external_ids = {**entity.external_ids, "legiscan_text_doc_id": str(latest["doc_id"])}
        db.commit()
        stored += 1
    return stored, failed, 0


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
    parser.add_argument("--dry-run", action="store_true", help="Count what would be fetched; 2 calls for the dataset.")
    parser.add_argument("--latest", action="store_true", help="Fill missing bills.full_text instead (passed bills first).")
    args = parser.parse_args()

    api = LegiScanClient()
    dataset = DatasetClient(fetch_session_dataset(api, settings.legiscan_state, args.session), fallback=api)
    session = SessionLocal()
    try:
        pick, run, what = (
            (latest_text_to_fetch, backfill_latest_text, "missing bill texts")
            if args.latest
            else (filed_versions_to_fetch, backfill_filed_versions, "filed versions")
        )
        if args.dry_run:
            print(f"{args.session}: {len(pick(session, dataset.bills))} {what} to fetch (1 call each).")
        else:
            stored, failed, left = run(session, dataset.bills, api, max_calls=args.max_calls)
            print(f"{args.session}: stored {stored}, failed {failed}, left for a later run {left}.")
    finally:
        session.close()
        print(api_usage_summary())
