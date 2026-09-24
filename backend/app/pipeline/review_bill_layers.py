"""Quality gate for bill layers: generate every block for a sample of real
bills and print a markdown report. Writes NOTHING to the database -- the
person reading the report decides whether the backfill goes ahead.

Sample: half with staff analysis, quarter state without, quarter local,
so both origins and both staff formats are exercised.

Usage:
    python -m app.pipeline.review_bill_layers --sample 20 > layers-review.md
    python -m app.pipeline.review_bill_layers --bill "HB 123" --bill "SB 7"

To compare two models on the exact same bills, run this twice with --model
and --bills-from pointed at the first run's report:
    python -m app.pipeline.review_bill_layers --model llama3.1:8b --sample 20 > r1.md
    python -m app.pipeline.review_bill_layers --model qwen2.5:14b --bills-from r1.md > r2.md
"""

from __future__ import annotations

import argparse
import re

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import Bill, Entity, StaffAnalysis
from app.pipeline import bill_layers as gen
from app.pipeline.bill_layers_batch import latest_staff_analysis, staff_label
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section
from app.pipeline.summarize import OllamaClient

# Matches this script's own report headings, e.g. "## H0565 — Some Title" or
# "## 2026-0548-W — A Local Ordinance".
_BILL_HEADING_RE = re.compile(r"^## (\S+) — ", re.MULTILINE)


def parse_bills_from_report(text: str) -> list[str]:
    """Bill numbers from an earlier report's "## <bill_number> — <title>"
    headings, in the order they appear. Used by --bills-from so a second
    model run covers exactly the same bills as an earlier one."""
    return _BILL_HEADING_RE.findall(text)


def _sample(db, n: int, bill_numbers: list[str], *, exclude: list[str] = ()) -> list[Entity]:
    base = select(Entity).join(Bill, Bill.entity_id == Entity.id).options(selectinload(Entity.bill))
    if bill_numbers:
        rows = db.execute(base.where(Bill.bill_number.in_(bill_numbers))).scalars().all()
        by_number = {e.bill.bill_number: e for e in rows}
        # Preserve the order bill_numbers was given in (the order an earlier
        # report listed them), not whatever order the DB returns.
        return [by_number[b] for b in bill_numbers if b in by_number]
    if exclude:
        base = base.where(Bill.bill_number.not_in(exclude))
    has_staff = select(StaffAnalysis.entity_id)
    with_staff = db.execute(
        base.where(Bill.full_text.isnot(None), Entity.id.in_(has_staff)).order_by(func.random()).limit(n // 2)
    ).scalars().all()
    state_without = db.execute(
        base.where(
            Bill.full_text.isnot(None),
            Entity.id.not_in(has_staff),
            Entity.jurisdiction_level == "state",
        )
        .order_by(func.random())
        .limit(n // 4)
    ).scalars().all()
    local = db.execute(
        base.where(
            Bill.full_text.isnot(None),
            Entity.id.not_in(has_staff),
            Entity.jurisdiction_level != "state",
        )
        .order_by(func.random())
        .limit(n - n // 2 - n // 4)
    ).scalars().all()
    return list(with_staff) + list(state_without) + list(local)


def _render(title: str, result: gen.LayerResult) -> list[str]:
    lines = [f"#### {title}", f"- state: `{result.evidence_state}` · scope: {result.scope_note}"]
    for i in result.items:
        ref = f" ({i['section_ref']})" if i.get("section_ref") else ""
        lines.append(f"- {i['text']}{ref}")
        for a in i.get("assumptions") or []:
            lines.append(f"  - assumption: {a}")
    for d in result.dropped:
        text = d.get('text') or d.get('quote') or d
        ref = f" ({d.get('section_ref')})" if isinstance(d, dict) and d.get('section_ref') else ""
        lines.append(f"- ~~dropped~~: {text}{ref}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--bill", action="append", default=[])
    parser.add_argument("--model", default=None, help="Override the model for this run (e.g. to compare against an earlier report).")
    parser.add_argument(
        "--bills-from",
        default=None,
        help="Path to an earlier report; run exactly its bill numbers, in order. "
        "Combine with --sample N to also draw N new random bills, excluding the listed ones.",
    )
    args = parser.parse_args()

    client = OllamaClient(model=args.model) if args.model else OllamaClient()
    db = SessionLocal()
    kept_quotes = dropped_quotes = kept_effects = dropped_effects = 0
    out: list[str] = [f"# Bill layers quality review ({client.model})", ""]
    try:
        bills_from_numbers: list[str] = []
        if args.bills_from:
            with open(args.bills_from) as f:
                bills_from_numbers = parse_bills_from_report(f.read())

        if bills_from_numbers:
            entities = _sample(db, 0, bills_from_numbers)
            if args.sample:
                entities += _sample(db, args.sample, [], exclude=bills_from_numbers)
        else:
            entities = _sample(db, args.sample if args.sample is not None else 20, args.bill)

        for entity in entities:
            bill = entity.bill
            out += [f"## {bill.bill_number} — {entity.name}", ""]
            try:
                says = gen.build_bill_says(bill.bill_number, entity.name, bill.full_text or "", client)
                kept_quotes += len(says.items)
                dropped_quotes += len(says.dropped)
                out += _render("Bill Says · bill text", says)
                out += _render("Interpretation · Sunshine Ledger",
                               gen.build_ai_interpretation(bill.bill_number, entity.name, bill.full_text or "", client))
                ai_eff = gen.build_ai_expected_effect(bill.bill_number, entity.name, bill.full_text or "", client)
                kept_effects += len(ai_eff.items)
                dropped_effects += len(ai_eff.dropped)
                out += _render("Expected Effect · Sunshine Ledger", ai_eff)
                analysis = latest_staff_analysis(db, entity.id)
                if analysis is None:
                    out.append("_No staff analysis published._")
                else:
                    label = staff_label(analysis)
                    out += _render("Interpretation · staff",
                                   gen.build_staff_interpretation(extract_effect_section(analysis.text), label, client))
                    out += _render("Expected Effect · staff",
                                   gen.build_staff_expected_effect(extract_fiscal_section(analysis.text), label, client))
            except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't sink the report
                out.append(f"**Generation error:** {type(exc).__name__}: {exc}")
            out.append("")
        total_q = kept_quotes + dropped_quotes
        total_e = kept_effects + dropped_effects
        out[1:1] = [
            f"- Bill Says quotes verified: {kept_quotes}/{total_q}" if total_q else "- Bill Says quotes: none returned",
            f"- Sunshine Ledger effects kept after guards: {kept_effects}/{total_e}" if total_e else "- Sunshine Ledger effects: none returned",
            "",
        ]
        print("\n".join(out))
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
