"""State legislative districts: who holds the seat, what they sponsor, and
Census context about the RESIDENTS who live there.

Doctrine (Todoist 6hvxmFvCHr9x6cGp): no voter-file data and no claims about
an electorate; no pairing of demographics with votes to suggest a member
voted for or against their district; no composite district score. The
profile is ACS estimates with vintage and margins of error, labelled as
residents.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.districts.service import (
    BadDistrictCode, members, parse_code, plan_on, sponsored_bill_ids,
)
from app.models import Bill, DemographicOverlay, District, Entity, MapPlan, Tag

router = APIRouter(prefix="/districts", tags=["districts"])

RESIDENTS_LABEL = (
    "Estimates for the people who live in this district (American Community Survey). "
    "They describe residents, not voters or the electorate, and say nothing about how any member should vote."
)
# Census's own rule of thumb: a coefficient of variation above 30% is high
# unreliability; an estimate no larger than its margin of error cannot be
# told apart from zero.
HIGH_CV = 0.30
Z90 = 1.645  # ACS margins of error are published at 90% confidence


def metric_reliability(estimate: float | None, moe: float | None) -> dict:
    """Flag or suppress a value by how large its margin of error is."""
    if estimate is None or moe is None or estimate == 0:
        return {"estimate": estimate, "margin_of_error": moe, "reliability": "unknown" if moe is None else "ok", "suppressed": False}
    if abs(estimate) <= moe:
        return {"estimate": None, "margin_of_error": moe, "reliability": "suppressed", "suppressed": True,
                "note": "The margin of error is as large as the estimate, so the value is not shown."}
    cv = (moe / Z90) / abs(estimate)
    return {"estimate": estimate, "margin_of_error": moe, "reliability": "high_moe" if cv > HIGH_CV else "ok", "suppressed": False}


def _get_district(db: Session, code: str, on: date | None = None) -> District:
    try:
        parse_code(code)
    except BadDistrictCode:
        raise HTTPException(status_code=404, detail="District not found")
    plan = plan_on(db, on or date.today())
    stmt = select(District).where(District.code == code)
    if plan:
        stmt = stmt.where(District.map_plan_id == plan.id)
    d = db.execute(stmt.limit(1)).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="District not found")
    return d


@router.get("")
def list_districts(chamber: str | None = Query(None, pattern="^(house|senate)$"), db: Session = Depends(get_db)) -> dict:
    plan = plan_on(db, date.today())
    stmt = select(District).order_by(District.chamber.desc(), District.number)
    if plan:
        stmt = stmt.where(District.map_plan_id == plan.id)
    if chamber:
        stmt = stmt.where(District.chamber == chamber)
    rows = db.execute(stmt).scalars().all()
    return {
        "map_plan": {"key": plan.key, "name": plan.name, "effective_from": plan.effective_from} if plan else None,
        "total": len(rows),
        "items": [{"code": d.code, "chamber": d.chamber, "number": d.number} for d in rows],
    }


@router.get("/{code}")
def get_district(code: str, db: Session = Depends(get_db)) -> dict:
    d = _get_district(db, code)
    plan = db.get(MapPlan, d.map_plan_id)
    mem = members(db, d)

    bill_ids = sponsored_bill_ids(d.code)
    total = db.execute(select(func.count(func.distinct(Bill.entity_id))).where(Bill.entity_id.in_(bill_ids))).scalar_one()
    bills = db.execute(
        select(Entity, Bill)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.id.in_(bill_ids))
        .order_by(Bill.last_action_date.desc().nulls_last())
        .limit(25)
    ).all()

    overlays = db.execute(
        select(DemographicOverlay).where(
            DemographicOverlay.geography_type == "district", DemographicOverlay.geography_id == d.code,
            DemographicOverlay.source == "acs",
        )
    ).scalars().all()
    labels = {t.slug: t.label for t in db.execute(select(Tag)).scalars()}
    profile = [
        {
            "badge_slug": o.badge_slug, "badge_label": labels.get(o.badge_slug, o.badge_slug), "vintage": o.as_of,
            "metrics": [
                {"label": m["label"], "unit": m.get("unit"), **metric_reliability(m.get("estimate"), m.get("margin_of_error"))}
                for m in o.metrics
            ],
        }
        for o in overlays
    ]
    return {
        "code": d.code, "chamber": d.chamber, "number": d.number,
        "map_plan": {"key": plan.key, "name": plan.name, "effective_from": plan.effective_from, "effective_to": plan.effective_to},
        "members": mem,
        "sponsored_bills": {
            "total": total,
            "note": "Bills filed by members while they held this seat. Where no seat history is on record, the member's current district is used.",
            "items": [
                {"entity_id": e.id, "bill_number": b.bill_number, "name": e.name, "status": b.status,
                 "last_action_date": b.last_action_date}
                for e, b in bills
            ],
        },
        "census_profile": {
            "population": "residents",
            "label": RESIDENTS_LABEL,
            "source": "U.S. Census Bureau, American Community Survey 5-year estimates",
            "profile": profile,
        },
    }
