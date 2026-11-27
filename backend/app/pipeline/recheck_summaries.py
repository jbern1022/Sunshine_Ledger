"""Re-check stored "what it does" summaries against the accuracy guards
(app.pipeline.summary_checks, 2026-11-27) and repair the ones that fail.

    python -m app.pipeline.recheck_summaries            # dry run: counts and examples
    python -m app.pipeline.recheck_summaries --apply

With --apply:
- Open Government Sunset Review summaries get the rule-based sunset sentence
  in place (no model call).
- Summaries with status words on a record not enacted, and title-only local
  summaries that turn "authorizing" into "requires" or drop a condition, have
  their input_hash cleared, so the next nightly summarize step regenerates
  just those records with the guards on.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Bill, Claim, Entity
from app.pipeline.bill_layers_text import overstates_title_modal
from app.pipeline.summarize import LOCAL_LEVELS
from app.pipeline.summary_checks import apply_sunset_rule, drops_condition, is_enacted, overstates_status


@dataclass
class Recheck:
    sunset_fixed: list[tuple[str, str, str]] = field(default_factory=list)  # (bill, old, new)
    regenerate: Counter = field(default_factory=Counter)  # reason -> count
    examples: dict[str, list[str]] = field(default_factory=dict)


def _reason(claim: Claim, entity: Entity, bill: Bill) -> str | None:
    local = entity.jurisdiction_level in LOCAL_LEVELS
    if not is_enacted(bill.status) and overstates_status(
        claim.claim_text, jurisdiction=entity.jurisdiction_name if local else None
    ):
        return "status words"
    if local and not (bill.full_text or "").strip():
        if overstates_title_modal(claim.claim_text, entity.name):
            return "authorizes read as requires"
        if drops_condition(claim.claim_text, entity.name):
            return "dropped condition"
    return None


def recheck(db: Session, *, apply: bool) -> Recheck:
    out = Recheck()
    rows = db.execute(
        select(Claim, Entity, Bill)
        .join(Entity, Entity.id == Claim.bill_entity_id)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Claim.claim_type == "what_it_does", Claim.generated_by.like("llm:%"))
    ).all()
    for claim, entity, bill in rows:
        if bill.full_text and entity.jurisdiction_level not in LOCAL_LEVELS:
            fixed = apply_sunset_rule(claim.claim_text, bill.full_text, entity.name)
            if fixed != claim.claim_text:
                out.sunset_fixed.append((bill.bill_number, claim.claim_text, fixed))
                if apply:
                    claim.claim_text = fixed
        reason = _reason(claim, entity, bill)
        if reason:
            out.regenerate[reason] += 1
            out.examples.setdefault(reason, [])
            if len(out.examples[reason]) < 3:
                out.examples[reason].append(f"{bill.bill_number}: {claim.claim_text[:140]}")
            if apply:
                claim.input_hash = None
    if apply:
        db.commit()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args()
    with SessionLocal() as db:
        out = recheck(db, apply=args.apply)
    verb = "Fixed" if args.apply else "Would fix"
    print(f"{verb} the sunset sentence in {len(out.sunset_fixed)} summaries.")
    for number, _old, new in out.sunset_fixed[:3]:
        print(f"  {number}: ...{new[-120:]}")
    verb = "Marked for regeneration" if args.apply else "Would mark for regeneration"
    print(f"{verb}: {sum(out.regenerate.values())} summaries")
    for reason, n in out.regenerate.most_common():
        print(f"  {reason}: {n}")
        for ex in out.examples[reason]:
            print(f"    {ex}")


if __name__ == "__main__":
    main()
