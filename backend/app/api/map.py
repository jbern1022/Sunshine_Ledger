from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Bill, Entity, Relationship, SpatialContext

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/counties")
def counties_geojson(
    jurisdiction_name: str | None = Query(None, description="Filter boundaries, e.g. FL"),
    db: Session = Depends(get_db),
) -> dict:
    """County/city-level shading data (BRD 5.3): boundary polygons plus a bill
    count per scope, joined by scope_name rather than per-address geometry.
    """
    boundary_stmt = select(SpatialContext).where(SpatialContext.scope_type.in_(["county", "city"]))
    boundaries = db.execute(boundary_stmt).scalars().all()

    counts = Counter()
    for geo_scope_names in db.execute(select(Bill.geo_scope_names)).scalars().all():
        counts.update(geo_scope_names)

    features = []
    for boundary in boundaries:
        shape = to_shape(boundary.geom)
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(shape),
                "properties": {
                    "scope_type": boundary.scope_type,
                    "scope_name": boundary.scope_name,
                    "bill_count": counts.get(boundary.scope_name, 0),
                    "source": boundary.geom_source,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


CHAMBER_BY_PREFIX = {"HD": "State House", "SD": "State Senate"}


@router.get("/districts")
def districts_geojson(db: Session = Depends(get_db)) -> dict:
    """Bill *sponsorship* activity per state legislative district.

    Deliberately separate from `/map/counties`, which shades by a bill's
    geographic scope. This endpoint answers a different question: how many
    tracked bills were filed by the legislator representing each district.

    These are NOT interchangeable. Nearly every state bill is statewide in
    effect, so a district shaded dark here means "this district's
    representative sponsors a lot of bills", never "these bills only affect
    this district". The frontend labels it accordingly -- keep that framing
    if this endpoint grows, per the BRD's neutrality requirement.
    """
    boundaries = db.execute(
        select(SpatialContext).where(SpatialContext.scope_type == "district")
    ).scalars().all()

    district_expr = Entity.attributes["district"].as_string()
    rows = db.execute(
        select(
            district_expr,
            Entity.name,
            # distinct: a legislator sponsoring the same bill as both sponsor
            # and co-sponsor must not be double-counted.
            func.count(func.distinct(Relationship.to_entity_id)),
        )
        .join(Relationship, Relationship.from_entity_id == Entity.id)
        .where(
            Entity.entity_type == "person",
            Relationship.relationship_type.in_(["sponsor", "co_sponsor"]),
            district_expr.isnot(None),
        )
        .group_by(district_expr, Entity.name)
    ).all()

    counts: Counter = Counter()
    legislators: defaultdict[str, list[str]] = defaultdict(list)
    for district, name, bill_count in rows:
        if not district:
            continue
        counts[district] += bill_count
        legislators[district].append(name)

    features = []
    for boundary in boundaries:
        shape = to_shape(boundary.geom)
        prefix = boundary.scope_name.split("-")[0]
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(shape),
                "properties": {
                    "scope_type": boundary.scope_type,
                    "scope_name": boundary.scope_name,
                    "chamber": CHAMBER_BY_PREFIX.get(prefix, prefix),
                    "bill_count": counts.get(boundary.scope_name, 0),
                    "legislators": sorted(legislators.get(boundary.scope_name, [])),
                    "source": boundary.geom_source,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}
