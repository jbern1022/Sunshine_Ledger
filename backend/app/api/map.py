from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Bill, SpatialContext

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
