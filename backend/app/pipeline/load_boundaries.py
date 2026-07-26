"""Load reference boundary geometry into `spatial_contexts` for map shading
(BRD 5.3). Two paths:

1. `load_sample_boundaries` — bundled, approximate GeoJSON for Miami-Dade,
   Duval, and statewide FL, for local dev/demo without any external
   download. NOT survey-accurate.
2. `load_tiger_shapefile` — real U.S. Census TIGER/Line county shapefile
   loader for production use. Download the county shapefile for Florida
   (FIPS 12) from https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/ and
   point this at the extracted .shp file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import shapefile  # pyshp
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Polygon, shape as shapely_shape
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import SpatialContext

logger = logging.getLogger(__name__)

SAMPLE_GEOJSON_PATH = Path(__file__).parent / "sample_data" / "fl_counties_approx.geojson"


def _as_multipolygon(geom) -> MultiPolygon:
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    return geom


def load_sample_boundaries(db: Session, *, replace: bool = True) -> int:
    """Load the bundled approximate FL/Miami-Dade/Duval polygons for local dev."""
    data = json.loads(SAMPLE_GEOJSON_PATH.read_text())

    if replace:
        db.execute(delete(SpatialContext).where(SpatialContext.entity_id.is_(None), SpatialContext.event_id.is_(None)))

    count = 0
    for feature in data["features"]:
        props = feature["properties"]
        geom = _as_multipolygon(shapely_shape(feature["geometry"]))
        db.add(
            SpatialContext(
                scope_type=props["scope_type"],
                scope_name=props["scope_name"],
                geom_source="Bernal Labs approximate placeholder (not survey-accurate)",
                geom=from_shape(geom, srid=4326),
            )
        )
        count += 1

    db.commit()
    logger.info("Loaded %d sample boundary polygons", count)
    return count


def load_tiger_shapefile(
    db: Session,
    shapefile_path: Path,
    *,
    scope_type: str,
    name_field: str,
    state_fips: str = "12",
    state_fips_field: str = "STATEFP",
    jurisdiction_name: str = "FL",
    name_filter: list[str] | None = None,
    replace: bool = True,
) -> int:
    """Load county/place boundaries from a real TIGER/Line shapefile.

    `name_field` / `state_fips_field` match TIGER/Line's own column names.
    Use "NAMELSAD" (not "NAME") for counties -- it includes the "County"
    suffix already used everywhere else in this codebase (bill
    geo_scope_names, seed data), so scope_name matches with zero
    transformation. Filter to Florida via `state_fips="12"`, and optionally
    to specific counties/cities via `name_filter` (MVP only needs
    Miami-Dade and Duval).

    `replace` clears any existing reference boundary rows (entity_id and
    event_id both null) with a matching scope_type + scope_name first, so
    re-running this (or running it after `load_sample_boundaries`) doesn't
    leave stale/duplicate polygons for the same county.
    """
    reader = shapefile.Reader(str(shapefile_path))
    fields = [f[0] for f in reader.fields[1:]]  # skip deletion flag field

    if replace and name_filter:
        db.execute(
            delete(SpatialContext).where(
                SpatialContext.entity_id.is_(None),
                SpatialContext.event_id.is_(None),
                SpatialContext.scope_type == scope_type,
                SpatialContext.scope_name.in_(name_filter),
            )
        )

    count = 0
    for sr in reader.shapeRecords():
        record = dict(zip(fields, sr.record))
        if state_fips_field in record and str(record[state_fips_field]) != state_fips:
            continue

        name = str(record.get(name_field, "")).strip()
        if not name:
            continue
        if name_filter and name not in name_filter:
            continue

        geom = _as_multipolygon(shapely_shape(sr.shape.__geo_interface__))
        db.add(
            SpatialContext(
                scope_type=scope_type,
                scope_name=name,
                geom_source=f"US Census TIGER/Line ({shapefile_path.name})",
                geom=from_shape(geom, srid=4326),
            )
        )
        count += 1

    db.commit()
    logger.info("Loaded %d boundaries from %s", count, shapefile_path)
    return count
