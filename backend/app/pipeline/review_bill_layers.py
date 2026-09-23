"""Quality gate for bill layers: generate every block for a sample of real
bills and print a markdown report. Writes NOTHING to the database -- the
person reading the report decides whether the backfill goes ahead.

Sample: half bills with a staff analysis, half without (state and local),
so both origins and both staff formats are exercised.

Usage:
    python -m app.pipeline.review_bill_layers --sample 20 > layers-review.md
    python -m app.pipeline.review_bill_layers --bill "HB 123" --bill "SB 7"
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import Bill, Entity, StaffAnalysis
from app.pipeline import bill_layers as gen
from app.pipeline.bill_layers_batch import latest_staff_analysis, staff_label
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section
from app.pipeline.summarize import OllamaClient


def _sample(db, n: int, bill_numbers: list[str]) -> list[Entity]:
    base = select(Entity).join(Bill, Bill.entity_id == Entity.id).options(selectinload(Entity.bill))
    if bill_numbers:
        return list(db.execute(base.where(Bill.bill_number.in_(bill_numbers))).scalars().all())
    has_staff = select(StaffAnalysis.entity_id)
    with_staff = db.execute(
        base.where(Bill.full_text.isnot(None), Entity.id.in_(has_staff)).order_by(func.random()).limit(n // 2)
    ).scalars().all()
    without = db.execute(
        base.where(Bill.full_text.isnot(None), Entity.id.not_in(has_staff)).order_by(func.random()).limit(n - n // 2)
    ).scalars().all()
    return list(with_staff) + list(without)


def _render(title: str, result: gen.LayerResult) -> list[str]:
    lines = [f"#### {title}", f"- state: `{result.evidence_state}` · scope: {result.scope_note}"]
    for i in result.items:
        ref = f" ({i['section_ref']})" if i.get("section_ref") else ""
        lines.append(f"- {i['text']}{ref}")
        for a in i.get("assumptions") or []:
            lines.append(f"  - assumption: {a}")
    for d in result.dropped:
        lines.append(f"- ~~dropped~~: `{d}`")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--bill", action="append", default=[])
    args = parser.parse_args()

    client = OllamaClient()
    db = SessionLocal()
    kept_quotes = dropped_quotes = kept_effects = dropped_effects = 0
    out: list[str] = [f"# Bill layers quality review ({client.model})", ""]
    try:
        for entity in _sample(db, args.sample, args.bill):
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
            except gen.LayerGenerationError as exc:
                out.append(f"**Generation error:** {exc}")
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
