"""Districts: map plans, who held a seat when, and who sponsored from it.

A sponsor is tied to a district through a dated tenure, so a member who
changed districts is counted in the district they held when the bill was
filed. Where we hold no state tenure for a person (the nightly feed gives
only the current roster), we fall back to the district on their current
record and say so (`basis: "current_roster"`) rather than imply a history we
do not have.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import Bill, District, Entity, MapPlan, OfficeTenure, Relationship, SpatialContext
from app.models.district import district_code

SPONSOR_TYPES = ("sponsor", "co_sponsor")
CODE_RE = re.compile(r"^(HD|SD)-(\d{3})$")
STATE_OFFICES = ("fl_house", "fl_senate")

# The maps first used in the 2022 elections (general election 2022-11-08).
# Check the dates against the plan's enactment before relying on them for
# anything earlier than the 2024 session data we hold.
CURRENT_PLAN = dict(
    key="fl-state-2022",
    name="Florida state legislative districts, plan in use since the 2022 elections",
    effective_from=date(2022, 11, 8),
)


class BadDistrictCode(ValueError):
    pass


def parse_code(code: str) -> tuple[str, int]:
    m = CODE_RE.match(code or "")
    if not m:
        raise BadDistrictCode(f"expected HD-### or SD-###, got {code!r}")
    return ("house" if m.group(1) == "HD" else "senate"), int(m.group(2))


def ensure_current_plan(db: Session) -> MapPlan:
    plan = db.execute(select(MapPlan).where(MapPlan.key == CURRENT_PLAN["key"])).scalar_one_or_none()
    if plan is None:
        plan = MapPlan(state="FL", **CURRENT_PLAN)
        db.add(plan)
        db.flush()
    return plan


def sync_districts(db: Session) -> dict:
    """Create District rows (current plan) for every district boundary already
    in spatial_contexts. Idempotent; attaches the boundary to each."""
    plan = ensure_current_plan(db)
    existing = {d.code: d for d in db.execute(select(District).where(District.map_plan_id == plan.id)).scalars()}
    out = {"created": 0, "linked": 0, "skipped": 0}
    for ctx in db.execute(select(SpatialContext).where(SpatialContext.scope_type == "district")).scalars():
        try:
            chamber, number = parse_code(ctx.scope_name)
        except BadDistrictCode:
            out["skipped"] += 1
            continue
        d = existing.get(ctx.scope_name)
        if d is None:
            d = District(map_plan_id=plan.id, chamber=chamber, number=number, code=district_code(chamber, number))
            db.add(d)
            existing[d.code] = d
            out["created"] += 1
        if d.spatial_context_id != ctx.id:
            d.spatial_context_id = ctx.id
            out["linked"] += 1
    db.flush()
    return out


def plan_on(db: Session, on: date) -> MapPlan | None:
    return db.execute(
        select(MapPlan).where(MapPlan.effective_from <= on, or_(MapPlan.effective_to.is_(None), MapPlan.effective_to >= on))
    ).scalar_one_or_none()


def _office(chamber: str) -> str:
    return "fl_house" if chamber == "house" else "fl_senate"


def sponsored_bill_ids(code: str):
    """A SELECT of bill entity ids sponsored (or co-sponsored) from this
    district: by someone whose tenure in it covers the bill's date, or, for a
    person with no state tenure recorded, whose current record says so."""
    chamber, number = parse_code(code)
    person = aliased(Entity)
    bill_date = func.coalesce(Bill.introduced_date, Bill.last_action_date)
    in_tenure = exists().where(
        OfficeTenure.person_entity_id == Relationship.from_entity_id,
        OfficeTenure.office_type == _office(chamber),
        OfficeTenure.district == number,
        OfficeTenure.start_date <= bill_date,
        or_(OfficeTenure.end_date.is_(None), OfficeTenure.end_date >= bill_date),
    )
    has_any = exists().where(
        OfficeTenure.person_entity_id == Relationship.from_entity_id, OfficeTenure.office_type.in_(STATE_OFFICES)
    )
    return (
        select(Relationship.to_entity_id)
        .join(person, person.id == Relationship.from_entity_id)
        .join(Bill, Bill.entity_id == Relationship.to_entity_id)
        .where(
            Relationship.relationship_type.in_(SPONSOR_TYPES),
            or_(in_tenure, and_(not_(has_any), person.attributes["district"].as_string() == code)),
        )
    )


def members(db: Session, district: District) -> list[dict]:
    """Everyone who held the seat (from tenures), then anyone the current
    roster puts there who has no tenure on record."""
    out: list[dict] = []
    tenured: set = set()
    rows = db.execute(
        select(OfficeTenure, Entity)
        .join(Entity, Entity.id == OfficeTenure.person_entity_id)
        .where(OfficeTenure.office_type == _office(district.chamber), OfficeTenure.district == district.number)
        .order_by(OfficeTenure.start_date.desc())
    ).all()
    for t, p in rows:
        tenured.add(p.id)
        out.append({
            "person_entity_id": p.id, "name": p.name, "party": t.party or (p.attributes or {}).get("party"),
            "start_date": t.start_date, "end_date": t.end_date, "end_reason": t.end_reason,
            "current": t.end_date is None, "basis": "tenure",
        })
    has_state_tenure = select(OfficeTenure.person_entity_id).where(OfficeTenure.office_type.in_(STATE_OFFICES))
    roster = db.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.attributes["district"].as_string() == district.code,
            not_(Entity.attributes.has_key("committee")),
            Entity.id.not_in(has_state_tenure),
        )
    ).scalars()
    for p in roster:
        if p.id in tenured:
            continue
        out.append({
            "person_entity_id": p.id, "name": p.name, "party": (p.attributes or {}).get("party"),
            "start_date": None, "end_date": None, "end_reason": None, "current": True, "basis": "current_roster",
        })
    return out


def main() -> None:
    """Create/refresh District rows from the boundaries already loaded.

    Usage: python -m app.districts.service
    """
    import logging

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        result = sync_districts(db)
        db.commit()
    logging.getLogger(__name__).info("districts: %s", result)


if __name__ == "__main__":
    main()
