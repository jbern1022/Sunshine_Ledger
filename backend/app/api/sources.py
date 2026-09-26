"""GET /sources/status: when each data source was last checked, what it
covers, and its known gaps -- for the site's "last checked" notes and the
methodology page. Mirrors docs/DATA_SOURCES.md; keep the two in step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Bill, SourceCheck

router = APIRouter(prefix="/sources", tags=["sources"])


@dataclass(frozen=True)
class SourceInfo:
    key: str  # SourceCheck.source_key written by the ingestion step
    label: str
    jurisdiction: str | None
    schedule: str
    # A source counts as stale once its last successful check is older than
    # this: a nightly job gets a missed night plus slack, a weekly one a
    # missed week plus a day. None = loaded by hand, never stale.
    max_age_hours: int | None
    bill_source_system: str | None  # Bill.source_system, for coverage counts
    note: str


SOURCES: tuple[SourceInfo, ...] = (
    SourceInfo(
        "legiscan", "Florida Legislature (via LegiScan)", "FL", "Nightly", 36, "legiscan",
        "The 2026 Regular Session and the three 2026 special sessions: bill text, amendments, "
        "votes, action history and staff analyses.",
    ),
    SourceInfo(
        "legistar_jaxcityc", "Jacksonville City Council (Legistar)", "Jacksonville", "Nightly", 36, "legistar",
        "The most recent council matters. Matters without a PDF attachment have no full text.",
    ),
    SourceInfo(
        "iqm2_miami", "City of Miami (iQM2)", "Miami", "Nightly", 36, "iqm2",
        "Miami's legislative record is collected from its public portal, which doesn't publish "
        "full text, so Miami items have none.",
    ),
    SourceInfo(
        "gdelt", "News headlines (GDELT)", None, "Weekly", 8 * 24, None,
        "Recent headlines matched to bills by keyword. Not a measure of coverage or of the bill's effect.",
    ),
    SourceInfo(
        "census_bls", "U.S. Census Bureau (ACS) and Bureau of Labor Statistics", None,
        "Loaded when new releases come out", None, None,
        "District and county context for Housing, Transportation and Labor bills. ACS figures are "
        "5-year estimates with margins of error.",
    ),
)

BY_SOURCE_SYSTEM = {s.bill_source_system: s for s in SOURCES if s.bill_source_system}


class SourceStatusOut(BaseModel):
    key: str
    label: str
    jurisdiction: str | None
    schedule: str
    note: str
    last_checked_at: datetime | None
    stale: bool
    bill_count: int | None
    bills_with_text: int | None


def is_stale(info: SourceInfo, last_checked_at: datetime | None, now: datetime) -> bool:
    if info.max_age_hours is None:
        return False
    if last_checked_at is None:
        return True
    return now - last_checked_at > timedelta(hours=info.max_age_hours)


@router.get("/status", response_model=list[SourceStatusOut])
def source_status(db: Session = Depends(get_db)) -> list[SourceStatusOut]:
    now = datetime.now(timezone.utc)
    checks = {c.source_key: c.last_checked_at for c in db.execute(select(SourceCheck)).scalars()}
    counts = {
        system: (total, with_text)
        for system, total, with_text in db.execute(
            select(Bill.source_system, func.count(), func.count(Bill.full_text)).group_by(Bill.source_system)
        ).all()
    }
    out = []
    for info in SOURCES:
        total, with_text = counts.get(info.bill_source_system, (None, None)) if info.bill_source_system else (None, None)
        out.append(
            SourceStatusOut(
                key=info.key,
                label=info.label,
                jurisdiction=info.jurisdiction,
                schedule=info.schedule,
                note=info.note,
                last_checked_at=checks.get(info.key),
                stale=is_stale(info, checks.get(info.key), now),
                bill_count=total if info.bill_source_system else None,
                bills_with_text=with_text if info.bill_source_system else None,
            )
        )
    return out
