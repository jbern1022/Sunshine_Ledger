from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.data.elections import CALENDARS
from app.db import get_db
from app.federal.policy import eligible_for_generation
from app.models import Bill, Claim, Entity, Source
from app.pipeline.item_kind import item_kind
from app.pipeline.summarize import ITEM_FALLBACK_GENERATED_BY, has_no_substance

router = APIRouter(tags=["health"])

# Ingestion is cron'd daily. Two days allows one missed run before alerting,
# so a single transient failure doesn't page anyone, while a genuinely
# stalled pipeline still surfaces on the second night.
MAX_INGEST_AGE_HOURS = 48

# A bill is only counted as stuck once it has survived a nightly cycle
# without a summary. Scraping and summarizing run back-to-back in the same
# job, so anything younger is probably just mid-run.
STUCK_AFTER_HOURS = 24


def count_stuck_without_summary(db: Session, *, cutoff: dt.datetime) -> int:
    """Bills the summarizer would take, old enough that a nightly run should
    have reached them, still without a summary.

    Mirrors the summarizer's own selection (summarize_batch): federal bills
    outside the delegation are never summarized, minutes and bare titles are
    skipped, and for non-legislation a title restatement (rule:item_title)
    counts as done. Counting anything else reports records as stuck that the
    pipeline will never take (2026-11-25: 370 flagged, nearly all minutes).
    """

    def claim_exists(condition):
        return select(Claim.id).where(Claim.bill_entity_id == Entity.id, condition).exists()

    has_llm = claim_exists(Claim.generated_by.like("llm:%"))
    has_fallback = claim_exists(Claim.generated_by == ITEM_FALLBACK_GENERATED_BY)
    rows = db.execute(
        select(Entity.name, Entity.attributes["item_type"].as_string(), has_fallback)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(
            Entity.entity_type == "bill",
            Entity.created_at < cutoff,
            (Bill.full_text.isnot(None)) | (Bill.description.isnot(None)),
            eligible_for_generation(),
            ~has_llm,
        )
    ).all()
    count = 0
    for name, item_type, fallback in rows:
        if item_kind(item_type) != "legislation" and (fallback or has_no_substance(item_type, name)):
            continue
        count += 1
    return count


@router.get("/health")
def health() -> dict[str, str | bool]:
    """Liveness only: is the process up and serving.

    Deliberately dependency-free -- it must not start failing because the
    database is slow or the pipeline is behind. Data freshness lives at
    /health/data.

    `read_only` says which origin answered: the Route 53 uptime check
    string-matches '"read_only":false', so a reply from the pilot-light
    standby (READ_ONLY=true) still counts as "the home server is down" and
    the failover automation keeps the standby running until home is back.
    """
    return {"status": "ok", "read_only": settings.read_only}


@router.get("/health/data")
def data_health(response: Response, db: Session = Depends(get_db)) -> dict:
    """Whether the data behind the site is actually current.

    `/health` stayed green through three days of stale data: the process was
    alive the whole time while nightly ingestion crashed and nobody noticed
    (Aug 21-24). Liveness and freshness are different questions, and only
    the second one would have caught that.

    Returns 503 when stale so a status-code monitor treats it as an
    incident; `reasons` says which check failed. A monitor that also alerts
    when this endpoint stops responding covers the remaining case -- the job
    host being down entirely.
    """
    now = dt.datetime.now(dt.timezone.utc)

    last_ingest = db.execute(select(func.max(Source.retrieved_at))).scalar()
    age_hours = round((now - last_ingest).total_seconds() / 3600, 1) if last_ingest else None

    bills_total = db.execute(
        select(func.count()).select_from(Entity).where(Entity.entity_type == "bill")
    ).scalar()

    missing_summary = count_stuck_without_summary(db, cutoff=now - dt.timedelta(hours=STUCK_AFTER_HOURS))

    reasons: list[str] = []
    if last_ingest is None:
        reasons.append("no ingestion has ever run")
    elif age_hours is not None and age_hours > MAX_INGEST_AGE_HOURS:
        reasons.append(f"last ingestion was {age_hours}h ago (limit {MAX_INGEST_AGE_HOURS}h)")
    if missing_summary:
        reasons.append(f"{missing_summary} bill(s) older than {STUCK_AFTER_HOURS}h have no summary")

    # Election dates are hand-entered from the state's published calendar
    # and carry a re-verify date, because there's no machine-readable feed
    # to catch a change. Nothing enforced that date until now, and the
    # stakes are higher than for bill data: the next Florida event is the
    # voter registration deadline, and publishing a wrong one could cost
    # someone their vote. Flag it rather than trusting the date silently.
    today = now.date()
    #
    # A calendar whose last event has passed has no future date left to be
    # wrong about (the re-verify date exists to catch late amendments to dates
    # still ahead), so it isn't flagged: otherwise this endpoint would return
    # 503 from the day after the final election until someone loads the next
    # cycle's dates. An empty calendar still counts as unverified.
    stale_calendars = [
        f"{cal.state} {cal.year}"
        for cal in CALENDARS.values()
        if cal.verify_by < today and not (cal.events and max(e.date for e in cal.events) < today)
    ]
    if stale_calendars:
        reasons.append(
            f"election calendar past its re-verify date: {', '.join(stale_calendars)} "
            "-- re-check against the state's published calendar"
        )

    if reasons:
        response.status_code = 503

    return {
        "status": "stale" if reasons else "ok",
        "reasons": reasons,
        "last_ingest_at": last_ingest.isoformat() if last_ingest else None,
        "hours_since_ingest": age_hours,
        "bills_total": bills_total,
        "bills_missing_summary": missing_summary,
        "election_calendars": {
            cal.state: {
                "year": cal.year,
                "verify_by": cal.verify_by.isoformat(),
                "days_until_reverify": (cal.verify_by - now.date()).days,
            }
            for cal in CALENDARS.values()
        },
        "checked_at": now.isoformat(),
    }
