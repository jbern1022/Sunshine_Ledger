"""List and approve Impact Lens criteria rows (the human step of review-by-risk).

    python -m app.impact_lens.review --queue [--limit 50]
    python -m app.impact_lens.review --bill "HB 1389"
    python -m app.impact_lens.review --bill "HB 1389" --approve 0 --approve 3 --reviewer joe [--note "checked against the quote"]
    python -m app.impact_lens.review --bill "HB 1389" --reject 2 --reviewer joe --note "county is wrong"

--queue lists, across all bills, the mappings that need a person: tier
"needs_review", not yet approved or rejected, newest bill activity first. It
reads only; nothing is held back from readers by it (see
docs/IMPACT_LENS_NIGHTLY_MAPPING.md).

--bill lists each entry's stored mapping, its review tier ("simple" or
"needs_review") and whether a person has approved it. --approve records an
approval for those entry numbers (current Who layer, current vocabulary and
method version). An approval is append-only and one row can have only one, so
approving twice is a no-op.

--reject records a rejection. A rejection is terminal for that row and beats an
approval: the read endpoint then withholds the mapping (the entry counts as
unmapped and the bill's result cannot say "does not apply"). A rejected row
cannot be approved; remap the entry (a new method or vocabulary version) to get
a fresh, unreviewed row. See docs/IMPACT_LENS_REVIEW_LIFECYCLE.md.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.impact_lens.criteria import review_tier
from app.impact_lens.map_batch import current_who_layers
from app.impact_lens.selection import review_state, served_rows
from app.models import Bill, BillLayer, BillLayerCriteria, BillLayerCriteriaReview


class RejectedMapping(ValueError):
    """Raised when approving a row that has been rejected."""


def criteria_rows(db: Session, layer: BillLayer) -> dict[int, BillLayerCriteria]:
    """The rows readers are served (see app.impact_lens.selection)."""
    return served_rows(db, layer)


def is_approved(row: BillLayerCriteria) -> bool:
    return review_state(row) == "approved"


def approve(db: Session, row: BillLayerCriteria, *, reviewer: str, note: str | None = None) -> bool:
    """Record an approval. Returns False (and writes nothing) if already approved;
    raises RejectedMapping for a rejected row (remap it instead)."""
    state = review_state(row)
    if state == "rejected":
        raise RejectedMapping("this mapping was rejected; remap the entry to get a new row to approve")
    if state == "approved":
        return False
    db.add(BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer=reviewer, note=note))
    db.commit()
    return True


def reject(db: Session, row: BillLayerCriteria, *, reviewer: str, note: str | None = None) -> bool:
    """Record a rejection. Returns False (and writes nothing) if already rejected."""
    if review_state(row) == "rejected":
        return False
    db.add(BillLayerCriteriaReview(criteria_id=row.id, decision="rejected", reviewer=reviewer, note=note))
    db.commit()
    return True


def review_queue(db: Session, *, limit: int = 50) -> list[tuple[Bill, BillLayer, int, str]]:
    """(bill, layer, entry number, group) for each served mapping that needs review and
    has no decision yet, on the current Who layer of each bill, newest activity first."""
    pairs = db.execute(
        select(Bill, BillLayer)
        .join(BillLayer, BillLayer.bill_entity_id == Bill.entity_id)
        .where(BillLayer.layer == "who_it_affects", BillLayer.superseded_at.is_(None))
        .order_by(Bill.last_action_date.desc().nulls_last(), Bill.bill_number)
    ).all()
    out: list[tuple[Bill, BillLayer, int, str]] = []
    if limit <= 0:
        return out
    for bill, layer in pairs:
        for i, row in sorted(criteria_rows(db, layer).items()):
            if review_state(row) == "unreviewed" and review_tier(row.criteria) == "needs_review":
                out.append((bill, layer, i, str(layer.items[i].get("group") or "")))
                if len(out) >= limit:
                    return out
    return out


def describe(bill: Bill, layer: BillLayer, rows: dict[int, BillLayerCriteria]) -> list[str]:
    out = [f"{bill.bill_number} ({bill.session}), who_it_affects v{layer.version}: {len(layer.items)} entries, {len(rows)} mapped"]
    for i, entry in enumerate(layer.items):
        row = rows.get(i)
        group = str(entry.get("group") or "")
        if row is None:
            out.append(f"  {i:>2}  {group[:40]:<40}  not mapped")
            continue
        status = {"approved": "approved", "rejected": "rejected"}.get(review_state(row), "not approved")
        out.append(f"  {i:>2}  {group[:40]:<40}  {review_tier(row.criteria):<12}  {status}")
    return out


if __name__ == "__main__":
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bill", help='e.g. "HB 1389"')
    parser.add_argument("--queue", action="store_true", help="List mappings that need review, across all bills.")
    parser.add_argument("--limit", type=int, default=50, help="With --queue: how many entries to list.")
    parser.add_argument("--approve", type=int, action="append", default=[], metavar="ENTRY", help="Entry number to approve (repeatable).")
    parser.add_argument("--reject", type=int, action="append", default=[], metavar="ENTRY", help="Entry number to reject (repeatable; terminal).")
    parser.add_argument("--reviewer", help="Who is reviewing (required with --approve or --reject).")
    parser.add_argument("--note", help="Optional note stored with the approval.")
    args = parser.parse_args()
    if bool(args.bill) == args.queue:
        parser.error("give --bill or --queue, not both and not neither")
    if args.queue and (args.approve or args.reject):
        parser.error("--queue only lists; approve or reject with --bill")
    if (args.approve or args.reject) and not args.reviewer:
        parser.error("--approve and --reject need --reviewer")
    if set(args.approve) & set(args.reject):
        parser.error("an entry cannot be both approved and rejected in one run")

    db = SessionLocal()
    try:
        if args.queue:
            queue = review_queue(db, limit=args.limit)
            for bill, layer, i, group in queue:
                print(f"{bill.bill_number} ({bill.session})  entry {i:>2}  {group[:50]}")
            print(f"{len(queue)} entries waiting" + (" (limit reached)" if len(queue) >= args.limit else ""))
            sys.exit(0)
        pairs = current_who_layers(db, [args.bill])
        if not pairs:
            print(f"No current who_it_affects layer for {args.bill}", file=sys.stderr)
            sys.exit(1)
        for bill, layer in pairs:
            rows = criteria_rows(db, layer)
            for n in args.approve:
                row = rows.get(n)
                if row is None:
                    print(f"{bill.bill_number} entry {n}: not mapped, nothing to approve", file=sys.stderr)
                    continue
                try:
                    done = approve(db, row, reviewer=args.reviewer, note=args.note)
                except RejectedMapping as exc:
                    print(f"{bill.bill_number} entry {n}: {exc}", file=sys.stderr)
                    continue
                print(f"{bill.bill_number} entry {n}: {'approved' if done else 'already approved'}")
            for n in args.reject:
                row = rows.get(n)
                if row is None:
                    print(f"{bill.bill_number} entry {n}: not mapped, nothing to reject", file=sys.stderr)
                    continue
                done = reject(db, row, reviewer=args.reviewer, note=args.note)
                print(f"{bill.bill_number} entry {n}: {'rejected' if done else 'already rejected'}")
            db.expire_all()
            print("\n".join(describe(bill, layer, criteria_rows(db, layer))))
    finally:
        db.close()
