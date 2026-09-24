"""Nightly job: write new Bill Says / Interpretation / Expected Effect
versions for bills whose inputs changed.

Per bill, up to five blocks. A block is regenerated only when its input
hash (input text + model + method version) differs from the current
version's, so a new committee staff analysis re-versions the staff blocks
and leaves the Sunshine Ledger blocks alone, and vice versa.

One bill's failure (bad model JSON, Ollama hiccup) is counted and the batch
moves on -- same isolation rule as summarize_batch.

Usage:
    python -m app.pipeline.bill_layers_batch [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import Bill, Entity, Source, StaffAnalysis
from app.pipeline import bill_layers as gen
from app.pipeline.bill_layers_store import current_layer, layer_input_hash, store_layer_version
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section
from app.pipeline.summarize import OllamaClient

logger = logging.getLogger(__name__)


@dataclass
class LayerJob:
    layer: str
    origin: str
    input_text: str
    input_hash: str


def latest_staff_analysis(db: Session, entity_id) -> StaffAnalysis | None:
    return db.execute(
        select(StaffAnalysis)
        .where(StaffAnalysis.entity_id == entity_id, StaffAnalysis.text.isnot(None), StaffAnalysis.text != "")
        .order_by(StaffAnalysis.analysis_date.desc().nulls_last(), StaffAnalysis.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def staff_label(analysis: StaffAnalysis) -> str:
    committee = analysis.committee or "committee not stated"
    when = analysis.analysis_date.isoformat() if analysis.analysis_date else "undated"
    return f"Staff analysis, {committee}, {when}"


def _staff_input(section: str | None, analysis: StaffAnalysis) -> str:
    # The label is part of the input so a newer analysis re-versions the
    # block even when the extracted text is identical: its scope changed.
    return f"{staff_label(analysis)}\n{section if section else f'<no section>|{analysis.id}'}"


def plan_jobs(db: Session, entity: Entity, model: str) -> list[LayerJob]:
    bill = entity.bill
    candidates: list[tuple[str, str, str]] = []
    if bill.full_text:
        for layer, origin in (
            ("bill_says", "bill_text"),
            ("interpretation", "sunshine_ledger_ai"),
            ("expected_effect", "sunshine_ledger_ai"),
        ):
            candidates.append((layer, origin, bill.full_text))
    analysis = latest_staff_analysis(db, entity.id)
    if analysis is not None:
        candidates.append(("interpretation", "legislative_staff", _staff_input(extract_effect_section(analysis.text), analysis)))
        candidates.append(("expected_effect", "legislative_staff", _staff_input(extract_fiscal_section(analysis.text), analysis)))

    jobs: list[LayerJob] = []
    for layer, origin, text in candidates:
        h = layer_input_hash(layer, origin, text, model)
        current = current_layer(db, entity.id, layer, origin)
        if current is None or current.input_hash != h:
            jobs.append(LayerJob(layer, origin, text, h))
    return jobs


def _sources_for(entity: Entity, job: LayerJob, analysis: StaffAnalysis | None) -> list[Source]:
    now = datetime.now(timezone.utc)
    bill = entity.bill
    if job.origin == "legislative_staff" and analysis is not None:
        return [Source(
            url=analysis.source_url,
            document_reference=analysis.committee,
            publisher="Florida Legislature staff",
            source_type="fl_staff_analysis",
            retrieved_at=now,
            metadata_json={"analysis_date": analysis.analysis_date.isoformat() if analysis.analysis_date else None,
                           "used_for": f"bill_layer:{job.layer}"},
        )]
    return [Source(
        url=bill.full_text_url or "",
        document_reference=bill.bill_number,
        publisher=f"{entity.jurisdiction_name or ''} via {bill.source_system}".strip(),
        source_type=f"{bill.source_system}_bill_text",
        retrieved_at=now,
        metadata_json={"used_for": f"bill_layer:{job.layer}"},
    )]


def run_job(db: Session, entity: Entity, job: LayerJob, client, analysis: StaffAnalysis | None):
    bill = entity.bill
    if (job.layer, job.origin) == ("bill_says", "bill_text"):
        result = gen.build_bill_says(bill.bill_number, entity.name, bill.full_text, client)
    elif (job.layer, job.origin) == ("interpretation", "sunshine_ledger_ai"):
        result = gen.build_ai_interpretation(bill.bill_number, entity.name, bill.full_text, client)
    elif (job.layer, job.origin) == ("expected_effect", "sunshine_ledger_ai"):
        result = gen.build_ai_expected_effect(bill.bill_number, entity.name, bill.full_text, client)
    elif (job.layer, job.origin) == ("interpretation", "legislative_staff"):
        result = gen.build_staff_interpretation(extract_effect_section(analysis.text), staff_label(analysis), client)
    else:
        result = gen.build_staff_expected_effect(extract_fiscal_section(analysis.text), staff_label(analysis), client)
    for d in result.dropped:
        logger.info("%s %s/%s dropped item: %s", bill.bill_number, job.layer, job.origin, d)
    return store_layer_version(
        db, bill_entity_id=entity.id, layer=job.layer, origin=job.origin, result=result,
        input_hash=job.input_hash, generated_by=f"llm:{client.model}",
        sources=_sources_for(entity, job, analysis),
    )


def _bills(db: Session) -> list[Entity]:
    return list(db.execute(
        select(Entity).join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill").options(selectinload(Entity.bill))
        .order_by(Bill.last_action_date.desc().nulls_last())
    ).scalars().all())


def process_bills(
    db: Session,
    client,
    *,
    limit: int | None = None,
    max_minutes: float | None = None,
    clock=time.monotonic,
) -> tuple[int, int]:
    """Returns (block versions written, bills failed). `limit` caps bills
    that have work, not bills scanned. `max_minutes`, if given, is a wall
    clock budget: once elapsed time (measured with `clock`, injectable for
    tests) reaches it, no new bill is started -- a bill already started
    still finishes. `max_minutes=0` starts no bill at all."""
    written = failed = processed = 0
    start = clock()
    for entity in _bills(db):
        if not entity.bill:
            continue
        jobs = plan_jobs(db, entity, client.model)
        if not jobs:
            continue
        if limit is not None and processed >= limit:
            break
        if max_minutes is not None and (clock() - start) >= max_minutes * 60:
            break
        processed += 1
        analysis = latest_staff_analysis(db, entity.id)
        try:
            for job in jobs:
                if run_job(db, entity, job, client, analysis) is not None:
                    written += 1
        except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the batch
            db.rollback()
            failed += 1
            logger.warning("FAIL %s: %s", entity.bill.bill_number, exc)
    return written, failed


def exit_code(*, written: int, failed: int) -> int:
    """Non-zero only when the run failed entirely (failures with nothing
    written), so run-ingestion.sh's step recording catches a wholly-failed
    run rather than treating "some model calls flaked" as success."""
    return 1 if failed > 0 and written == 0 else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Max bills with work to process this run.")
    parser.add_argument("--max-minutes", type=float, default=180, help="Wall clock budget in minutes; no new bill starts once elapsed.")
    parser.add_argument("--dry-run", action="store_true", help="List planned jobs; no model calls, no writes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.dry_run:
            n = 0
            for entity in _bills(db):
                jobs = plan_jobs(db, entity, settings.ollama_layers_model) if entity.bill else []
                if jobs:
                    n += 1
                    print(f"{entity.bill.bill_number}: " + ", ".join(f"{j.layer}/{j.origin}" for j in jobs))
                    if args.limit and n >= args.limit:
                        break
            print(f"\n{n} bill(s) with work.")
        else:
            client = OllamaClient(model=settings.ollama_layers_model, timeout=300)
            ok, bad = process_bills(db, client, limit=args.limit, max_minutes=args.max_minutes)
            print(f"\nDone: {ok} block version(s) written, {bad} bill(s) failed.")
            sys.exit(exit_code(written=ok, failed=bad))
    finally:
        db.close()
