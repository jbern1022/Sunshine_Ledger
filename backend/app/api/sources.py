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
from app.models import Bill, Entity, SourceCheck
from app.pipeline.legistar import CLIENT_JURISDICTIONS, nightly_clients, source_key

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
        "The 2024, 2025 and 2026 sessions, regular and special: bills, votes, amendments and "
        "action history. Bill text and staff analyses are most complete for 2026.",
    ),
    # One entry per nightly Legistar city, read from the adapter's registry so a
    # new city appears here without touching this file.
    *(
        SourceInfo(
            source_key(name), CLIENT_JURISDICTIONS[name]["label"], CLIENT_JURISDICTIONS[name]["jurisdiction"],
            "Nightly", 36, "legistar", CLIENT_JURISDICTIONS[name]["note"],
        )
        for name in nightly_clients()
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
# Source systems that several sources share (Legistar): a source with no rows of
# its own has zero, not the system-wide total.
_SHARED_SYSTEMS = {
    system for system in BY_SOURCE_SYSTEM if sum(s.bill_source_system == system for s in SOURCES) > 1
}


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
    # Per-city counts: several cities can share a source system (Legistar).
    by_city = {
        (system, city): (total, with_text)
        for system, city, total, with_text in db.execute(
            select(Bill.source_system, Entity.jurisdiction_name, func.count(), func.count(Bill.full_text))
            .join(Entity, Entity.id == Bill.entity_id)
            .group_by(Bill.source_system, Entity.jurisdiction_name)
        ).all()
    }
    out = []
    for info in SOURCES:
        if not info.bill_source_system:
            total, with_text = None, None
        elif (info.bill_source_system, info.jurisdiction) in by_city:
            total, with_text = by_city[(info.bill_source_system, info.jurisdiction)]
        elif info.bill_source_system in _SHARED_SYSTEMS:
            total, with_text = 0, 0
        else:
            total, with_text = counts.get(info.bill_source_system, (None, None))
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
