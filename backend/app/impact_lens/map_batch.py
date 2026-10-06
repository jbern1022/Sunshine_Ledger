"""Map Who-it-affects entries to Impact Lens criteria, and export a sheet for
hand-labeling.

    python -m app.impact_lens.map_batch --bill "HB 1389" [--bill "SB 2" ...] [--dry-run]
    python -m app.impact_lens.map_batch --bill "HB 1389" --export sheet.md

Maps the CURRENT who_it_affects layer of each bill (all sessions if the number
repeats). Already-mapped entries at this vocabulary + method version are
skipped, so a rerun makes no model calls. --export writes what is stored
(never calls the model) as a Markdown sheet with a verdict line per entry.
This is the phase 2 baseline: a person fills the verdicts, and the counts
decide when the review-by-risk step can start.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.impact_lens.criteria import review_tier
from app.impact_lens.mapper import METHOD_VERSION, map_layer
from app.impact_lens.vocabulary import VOCABULARY_VERSION, jurisdiction_label
from app.models import Bill, BillLayer, BillLayerCriteria


def current_who_layers(db: Session, bill_numbers: list[str]) -> list[tuple[Bill, BillLayer]]:
    rows = db.execute(
        select(Bill, BillLayer)
        .join(BillLayer, BillLayer.bill_entity_id == Bill.entity_id)
        .where(
            Bill.bill_number.in_(bill_numbers),
            BillLayer.layer == "who_it_affects",
            BillLayer.superseded_at.is_(None),
        )
        .order_by(Bill.bill_number, Bill.session)
    ).all()
    return [(b, l) for b, l in rows]


def _fmt_test(t: dict) -> str:
    vals = ", ".join(jurisdiction_label(v) if t["attr"] == "jurisdiction" else str(v) for v in t["values"])
    return f'{t["attr"]} {t["op"]} [{vals}]  (from {t["from"]["kind"]} {t["from"]["index"]})'


def export_sheet(db: Session, pairs: list[tuple[Bill, BillLayer]]) -> str:
    out = [
        "# Impact Lens criteria: hand-labeling sheet",
        "",
        f"Vocabulary v{VOCABULARY_VERSION}, method {METHOD_VERSION}. For each entry mark ONE verdict:",
        "`correct`, `wrong` (a mapped part says something the bill does not), `missed` (a part that could have been mapped was left unmapped), or `unsure`.",
        "A `wrong` mapping is the serious one: note which part and why.",
        "",
    ]
    for bill, layer in pairs:
        out += [f"## {bill.bill_number} ({bill.session}), who_it_affects v{layer.version}", ""]
        rows = {
            r.entry_index: r for r in db.execute(
                select(BillLayerCriteria).where(
                    BillLayerCriteria.bill_layer_id == layer.id,
                    BillLayerCriteria.vocabulary_version == VOCABULARY_VERSION,
                    BillLayerCriteria.method_version == METHOD_VERSION,
                )
            ).scalars()
        }
        for i, entry in enumerate(layer.items):
            out += [f"### Entry {i}: {entry.get('group')}", f"- **Change:** {entry.get('text') or entry.get('change')}", f"- **Quote:** {entry.get('quote')}"]
            for kind in ("conditions", "exceptions"):
                for j, it in enumerate(entry.get(kind) or []):
                    out.append(f"- **{kind[:-1].title()} {j}:** {it.get('text')}  _Quote:_ {it.get('quote')}")
            row = rows.get(i)
            if row is None:
                out += ["- **Not mapped yet.**", ""]
                continue
            c = row.criteria
            aud = c["audience"]
            out.append("- **Audience:** " + ("unmapped" if aud is None else "anyone" if aud["kind"] == "anyone" else f'{aud["attr"]} in {aud["any_of"]}'))
            aff = c.get("affected")
            if aff:
                out.append(f'- **Affected party:** role in {aff["any_of"]}')
            out += [f"- **Requires:** {_fmt_test(t)}" for t in c["requires"]]
            out += [f"- **Excludes:** {_fmt_test(t)}" for t in c["excludes"]]
            out += [f"- **Unmapped:** {u['kind']} {u['index']}: {u['reason']}" for u in c["unmapped"]]
            out += [f"- **Adjusted:** {n}" for n in c.get("notes", [])]
            if c["ambiguous"]:
                out.append(f"- **Ambiguous:** {c['ambiguous']['question']}")
            out += [f"- **Review tier:** {review_tier(c)}", "- **Verdict:** ", "- **Note:** ", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    from app.db import SessionLocal
    from app.logging_setup import quiet_http_logging
    from app.pipeline.summarize import OllamaClient

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bill", action="append", required=True, help='e.g. "HB 1389" (repeatable)')
    parser.add_argument("--dry-run", action="store_true", help="Say what would be mapped; no model calls, no writes.")
    parser.add_argument("--export", metavar="PATH", help="Write the hand-labeling sheet for what is stored; no model calls.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        pairs = current_who_layers(db, args.bill)
        missing = set(args.bill) - {b.bill_number for b, _ in pairs}
        if missing:
            print(f"No current who_it_affects layer for: {', '.join(sorted(missing))}", file=sys.stderr)
        if args.export:
            Path(args.export).write_text(export_sheet(db, pairs))
            print(f"Wrote {args.export}")
            sys.exit(0)
        if args.dry_run:
            for bill, layer in pairs:
                print(f"{bill.bill_number} ({bill.session}): {len(layer.items)} entries")
            sys.exit(0)
        client = OllamaClient(model=settings.ollama_layers_model, timeout=300, temperature=0, num_predict=2048)
        failed_total = 0
        for bill, layer in pairs:
            stored, skipped, failed = map_layer(db, layer, client, generated_by=f"llm:{settings.ollama_layers_model}")
            failed_total += failed
            print(f"{bill.bill_number} ({bill.session}): stored {stored}, already mapped {skipped}, failed {failed}")
        sys.exit(1 if failed_total and not pairs else 0)
    finally:
        db.close()
