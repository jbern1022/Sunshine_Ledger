"""List and approve Impact Lens criteria rows (the human step of review-by-risk).

    python -m app.impact_lens.review --bill "HB 1389"
    python -m app.impact_lens.review --bill "HB 1389" --approve 0 --approve 3 --reviewer joe [--note "checked against the quote"]

--bill lists each entry's stored mapping, its review tier ("simple" or
"needs_review") and whether a person has approved it. --approve records an
approval for those entry numbers (current Who layer, current vocabulary and
method version). An approval is append-only and one row can have only one, so
approving twice is a no-op. Rejections are not recorded here: the read
endpoint does not act on them yet, and a recorded decision with no effect
would mislead.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.impact_lens.criteria import review_tier
from app.impact_lens.map_batch import current_who_layers
from app.impact_lens.mapper import METHOD_VERSION
from app.impact_lens.vocabulary import VOCABULARY_VERSION
from app.models import Bill, BillLayer, BillLayerCriteria, BillLayerCriteriaReview


def criteria_rows(db: Session, layer: BillLayer) -> dict[int, BillLayerCriteria]:
    return {
        r.entry_index: r
        for r in db.execute(
            select(BillLayerCriteria).where(
                BillLayerCriteria.bill_layer_id == layer.id,
                BillLayerCriteria.vocabulary_version == VOCABULARY_VERSION,
                BillLayerCriteria.method_version == METHOD_VERSION,
            )
        ).scalars()
    }


def is_approved(row: BillLayerCriteria) -> bool:
    return any(r.decision == "approved" for r in row.reviews)


def approve(db: Session, row: BillLayerCriteria, *, reviewer: str, note: str | None = None) -> bool:
    """Record an approval. Returns False (and writes nothing) if already approved."""
    if is_approved(row):
        return False
    db.add(BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer=reviewer, note=note))
    db.commit()
    return True


def describe(bill: Bill, layer: BillLayer, rows: dict[int, BillLayerCriteria]) -> list[str]:
    out = [f"{bill.bill_number} ({bill.session}), who_it_affects v{layer.version}: {len(layer.items)} entries, {len(rows)} mapped"]
    for i, entry in enumerate(layer.items):
        row = rows.get(i)
        group = str(entry.get("group") or "")
        if row is None:
            out.append(f"  {i:>2}  {group[:40]:<40}  not mapped")
            continue
        status = "approved" if is_approved(row) else "not approved"
        out.append(f"  {i:>2}  {group[:40]:<40}  {review_tier(row.criteria):<12}  {status}")
    return out


if __name__ == "__main__":
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bill", required=True, help='e.g. "HB 1389"')
    parser.add_argument("--approve", type=int, action="append", default=[], metavar="ENTRY", help="Entry number to approve (repeatable).")
    parser.add_argument("--reviewer", help="Who is approving (required with --approve).")
    parser.add_argument("--note", help="Optional note stored with the approval.")
    args = parser.parse_args()
    if args.approve and not args.reviewer:
        parser.error("--approve needs --reviewer")

    db = SessionLocal()
    try:
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
                done = approve(db, row, reviewer=args.reviewer, note=args.note)
                print(f"{bill.bill_number} entry {n}: {'approved' if done else 'already approved'}")
            db.expire_all()
            print("\n".join(describe(bill, layer, criteria_rows(db, layer))))
    finally:
        db.close()
