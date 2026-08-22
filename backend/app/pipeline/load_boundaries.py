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


# TIGER ships state legislative districts as two files: SLDL (lower/House)
# and SLDU (upper/Senate). LegiScan identifies a legislator's district as
# "HD-120"/"SD-024", so scope_name is normalized to that form at load time
# -- the district map joins sponsors to polygons on this string, and doing
# the transformation here keeps the query side free of string munging.
DISTRICT_CHAMBERS = {
    "sldl": {"prefix": "HD", "code_field": "SLDLST"},
    "sldu": {"prefix": "SD", "code_field": "SLDUST"},
}


def load_tiger_districts(
    db: Session,
    shapefile_path: Path,
    *,
    chamber: str,
    state_fips: str = "12",
    replace: bool = True,
) -> int:
    """Load state legislative district polygons from a TIGER SLDL/SLDU shapefile.

    `chamber` is "sldl" (state House) or "sldu" (state Senate). Download from
    https://www2.census.gov/geo/tiger/TIGER2024/SLDL/tl_2024_12_sldl.zip (and
    .../SLDU/tl_2024_12_sldu.zip) for Florida.

    Districts whose code isn't a plain number (TIGER uses "ZZZ" for
    unpopulated/water-only areas) are skipped -- they have no legislator and
    would never match a sponsor.
    """
    if chamber not in DISTRICT_CHAMBERS:
        raise ValueError(f"chamber must be one of {sorted(DISTRICT_CHAMBERS)}, got {chamber!r}")

    prefix = DISTRICT_CHAMBERS[chamber]["prefix"]
    code_field = DISTRICT_CHAMBERS[chamber]["code_field"]

    reader = shapefile.Reader(str(shapefile_path))
    fields = [f[0] for f in reader.fields[1:]]

    if replace:
        db.execute(
            delete(SpatialContext).where(
                SpatialContext.entity_id.is_(None),
                SpatialContext.event_id.is_(None),
                SpatialContext.scope_type == "district",
                SpatialContext.scope_name.like(f"{prefix}-%"),
            )
        )

    count = 0
    for sr in reader.shapeRecords():
        record = dict(zip(fields, sr.record))
        if "STATEFP" in record and str(record["STATEFP"]) != state_fips:
            continue

        code = str(record.get(code_field, "")).strip()
        if not code.isdigit():
            continue

        geom = _as_multipolygon(shapely_shape(sr.shape.__geo_interface__))
        db.add(
            SpatialContext(
                scope_type="district",
                scope_name=f"{prefix}-{code.zfill(3)}",
                geom_source=f"US Census TIGER/Line ({shapefile_path.name})",
                geom=from_shape(geom, srid=4326),
            )
        )
        count += 1

    db.commit()
    logger.info("Loaded %d %s district boundaries from %s", count, prefix, shapefile_path)
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


TIGER_DISTRICT_URLS = {
    "sldl": "https://www2.census.gov/geo/tiger/TIGER2024/SLDL/tl_2024_12_sldl.zip",
    "sldu": "https://www2.census.gov/geo/tiger/TIGER2024/SLDU/tl_2024_12_sldu.zip",
}


def download_and_load_districts(db: Session, *, chamber: str, state_fips: str = "12") -> int:
    """Fetch a TIGER district shapefile and load it in one step.

    Deliberately does both in a single call: container restarts wipe /tmp,
    so a download in one step and a load in another can silently lose the
    file in between (see docs/RUNBOOK.md).
    """
    import io
    import tempfile
    import zipfile

    import httpx

    url = TIGER_DISTRICT_URLS[chamber]
    logger.info("Downloading %s", url)
    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()

    with tempfile.TemporaryDirectory() as tmpdir:
        zipfile.ZipFile(io.BytesIO(resp.content)).extractall(tmpdir)
        shp = next(Path(tmpdir).glob("*.shp"))
        return load_tiger_districts(db, shp, chamber=chamber, state_fips=state_fips)


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Load reference boundary geometry.")
    parser.add_argument(
        "--districts",
        action="store_true",
        help="Download and load TIGER state legislative districts (both chambers).",
    )
    parser.add_argument("--state-fips", default="12", help="Default 12 (Florida).")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.districts:
            total = sum(
                download_and_load_districts(session, chamber=c, state_fips=args.state_fips)
                for c in ("sldl", "sldu")
            )
            print(f"Loaded {total} district boundaries.")
        else:
            print(f"Loaded {load_sample_boundaries(session)} sample boundaries.")
    finally:
        session.close()
