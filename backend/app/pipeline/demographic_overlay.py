"""ACS/BLS demographic-economic overlay for "who it affects" (Roadmap
Phase 2, Todoist 6hCMm77F28HRRr6p).

Two data sources, each used at its real native geography (design note on
the ticket's Notion page, 2026-09-15, has the full reasoning):
  - ACS (Census): district-level for state bills, county-level for local
    bills. Annual 5-year estimates; every estimate carries a margin of
    error, surfaced per BRD 7, never dropped.
  - BLS: county-level ONLY -- there is no state-legislative-district BLS
    series. State bills therefore get no BLS-sourced overlay; this is a
    documented gap, not an oversight.

Results are cached in `demographic_overlays` by a batch loader (this
module's load_* functions), not fetched live per API request -- ACS is
annual, BLS is monthly, matching the same cost-aware posture as
spatial_contexts being pre-loaded once (load_boundaries.py).

Covers 3 of the Roadmap ticket's own example badges: Housing, Infrastructure/
Transportation, Labor/Employment. The other 10 badge categories have no
defined table mapping yet and simply have no overlay row -- callers should
treat "no row found" as "no overlay for this badge," not an error.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_setup import quiet_http_logging
from app.models import DemographicOverlay
from app.pipeline._retry import with_retry

logger = logging.getLogger(__name__)

ACS_BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"
BLS_SERIES_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Most recent 5-year ACS vintage (2020-2024 estimates; checked 2026-09-25,
# when 2025 was not yet published). The Census Bureau releases the next one
# each December: bump this, then rerun `python -m app.pipeline.demographic_overlay`.
ACS_YEAR = "2024"

FL_STATE_FIPS = "12"

SLD_CHAMBER_GEOGRAPHY = {
    "HD": "state legislative district (lower chamber)",
    "SD": "state legislative district (upper chamber)",
}

# Counties this app actually ingests local bills for (Miami, Jacksonville).
COUNTY_FIPS = {
    "Miami-Dade County": "086",
    "Duval County": "031",
}

# badge_slug -> ACS variables (paired _E/_M per Census convention), each
# with its own unit -- these are NOT all person/unit counts (B08303 is an
# aggregate minutes figure), so unit is per-variable, not assumed.
ACS_TABLES: dict[str, list[tuple[str, str, str]]] = {
    "housing": [
        ("B25003_001", "Total occupied housing units", "housing units"),
        ("B25003_002", "Owner-occupied", "housing units"),
        ("B25003_003", "Renter-occupied", "housing units"),
    ],
    "infrastructure_transportation": [
        ("B08303_001", "Aggregate travel time to work", "minutes (aggregate, all workers)"),
    ],
}


class ACSError(RuntimeError):
    pass


class BLSError(RuntimeError):
    pass


def _num(value: object) -> float | None:
    """Parse an ACS cell value. Census uses -666666666 as a suppressed/
    not-available sentinel for small-sample estimates -- treat it as
    missing rather than a real (absurd) number."""
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if n <= -666_666_666:
        return None
    return n


class ACSClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.census_api_key
        if not self.api_key:
            raise ACSError(
                "CENSUS_API_KEY is not set. Free signup: https://api.census.gov/data/key_signup.html"
            )
        self._client = httpx.Client(timeout=20.0)

    def _get(self, params: dict) -> list[list[str]]:
        def _do_request() -> httpx.Response:
            resp = self._client.get(ACS_BASE_URL.format(year=ACS_YEAR), params={**params, "key": self.api_key})
            resp.raise_for_status()
            return resp

        resp = with_retry(_do_request, description=f"ACS get={params.get('get')}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ACSError(f"Unexpected ACS response: {resp.text[:200]}") from exc

    def get_by_district(self, variables: list[str], *, chamber: str) -> dict[str, dict[str, str]]:
        """{district code (e.g. "101"): {variable: value}} for every FL
        district in one chamber, one request for the whole chamber."""
        geo = SLD_CHAMBER_GEOGRAPHY[chamber]
        rows = self._get({
            "get": "NAME," + ",".join(variables),
            "for": f"{geo}:*",
            "in": f"state:{FL_STATE_FIPS}",
        })
        header, *data_rows = rows
        out: dict[str, dict[str, str]] = {}
        for row in data_rows:
            out[row[-1]] = dict(zip(header[1:-2], row[1:-2]))
        return out

    def get_by_county(self, variables: list[str], *, county_fips: str) -> dict[str, str]:
        rows = self._get({
            "get": "NAME," + ",".join(variables),
            "for": f"county:{county_fips}",
            "in": f"state:{FL_STATE_FIPS}",
        })
        header, data_row = rows[0], rows[1]
        return dict(zip(header[1:-2], data_row[1:-2]))


class BLSClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.bls_api_key
        self._client = httpx.Client(timeout=20.0)

    def get_series(self, series_ids: list[str], *, start_year: str, end_year: str) -> dict[str, list[dict]]:
        payload: dict = {"seriesid": series_ids, "startyear": start_year, "endyear": end_year}
        if self.api_key:
            payload["registrationkey"] = self.api_key

        def _do_request() -> httpx.Response:
            resp = self._client.post(BLS_SERIES_URL, json=payload)
            resp.raise_for_status()
            return resp

        resp = with_retry(_do_request, description=f"BLS series={series_ids}")
        data = resp.json()
        if data.get("status") != "REQUEST_SUCCEEDED":
            raise BLSError(f"BLS request failed: {data.get('message')}")
        return {s["seriesID"]: s["data"] for s in data["Results"]["series"]}


def county_unemployment_series_id(county_fips: str) -> str:
    """LAUS county unemployment-rate series id. Format confirmed live
    2026-09-15 against LAUCN120860000000003 (Miami-Dade County, FL)."""
    return f"LAUCN{FL_STATE_FIPS}{county_fips}0000000003"


def _store_overlay(
    db: Session, *, geography_type: str, geography_id: str, badge_slug: str, source: str, metrics: list, as_of: str
) -> DemographicOverlay:
    existing = db.execute(
        select(DemographicOverlay).where(
            DemographicOverlay.geography_type == geography_type,
            DemographicOverlay.geography_id == geography_id,
            DemographicOverlay.badge_slug == badge_slug,
            DemographicOverlay.source == source,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.metrics = metrics
        existing.as_of = as_of
        return existing

    overlay = DemographicOverlay(
        geography_type=geography_type,
        geography_id=geography_id,
        badge_slug=badge_slug,
        source=source,
        metrics=metrics,
        as_of=as_of,
    )
    db.add(overlay)
    return overlay


def _acs_metrics(values: dict[str, str], table: list[tuple[str, str, str]]) -> list[dict]:
    return [
        {
            "label": label,
            "estimate": _num(values.get(f"{var}E")),
            "margin_of_error": _num(values.get(f"{var}M")),
            "unit": unit,
        }
        for var, label, unit in table
    ]


def _acs_table_and_variables(badge_slug: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    if badge_slug not in ACS_TABLES:
        raise ValueError(f"No ACS table mapping for badge {badge_slug!r}")
    table = ACS_TABLES[badge_slug]
    variables = [f"{var}{suffix}" for var, _label, _unit in table for suffix in ("E", "M")]
    return table, variables


def load_acs_district_overlays(db: Session, *, badge_slug: str, client: ACSClient | None = None) -> int:
    """Load one ACS badge's table for every FL House and Senate district."""
    table, variables = _acs_table_and_variables(badge_slug)
    client = client or ACSClient()

    count = 0
    for prefix in ("HD", "SD"):
        by_district = client.get_by_district(variables, chamber=prefix)
        for code, values in by_district.items():
            _store_overlay(
                db,
                geography_type="district",
                geography_id=f"{prefix}-{code.zfill(3)}",
                badge_slug=badge_slug,
                source="acs",
                metrics=_acs_metrics(values, table),
                as_of=ACS_YEAR,
            )
            count += 1
    db.commit()
    logger.info("Loaded ACS %s overlay for %d districts", badge_slug, count)
    return count


def load_acs_county_overlays(db: Session, *, badge_slug: str, client: ACSClient | None = None) -> int:
    """Load one ACS badge's table for every county this app covers (local bills)."""
    table, variables = _acs_table_and_variables(badge_slug)
    client = client or ACSClient()

    count = 0
    for county_name, fips in COUNTY_FIPS.items():
        values = client.get_by_county(variables, county_fips=fips)
        _store_overlay(
            db,
            geography_type="county",
            geography_id=county_name,
            badge_slug=badge_slug,
            source="acs",
            metrics=_acs_metrics(values, table),
            as_of=ACS_YEAR,
        )
        count += 1
    db.commit()
    logger.info("Loaded ACS %s overlay for %d counties", badge_slug, count)
    return count


def load_bls_county_unemployment(db: Session, *, year: str, client: BLSClient | None = None) -> int:
    """Load county-level unemployment rate for every county this app covers,
    tagged to the Labor/Employment badge. No margin of error -- BLS doesn't
    publish one for this series, so `margin_of_error` is null (per the
    model's own docstring: null there is expected, not a bug)."""
    client = client or BLSClient()
    series_ids = {county: county_unemployment_series_id(fips) for county, fips in COUNTY_FIPS.items()}
    results = client.get_series(list(series_ids.values()), start_year=year, end_year=year)

    count = 0
    for county_name, series_id in series_ids.items():
        data_points = results.get(series_id, [])
        if not data_points:
            logger.warning("No BLS data returned for %s (series %s)", county_name, series_id)
            continue
        latest = data_points[0]  # BLS returns newest period first
        metrics = [
            {
                "label": "Unemployment rate",
                "estimate": _num(latest.get("value")),
                "margin_of_error": None,
                "unit": "percent",
            }
        ]
        _store_overlay(
            db,
            geography_type="county",
            geography_id=county_name,
            badge_slug="labor_employment",
            source="bls",
            metrics=metrics,
            as_of=f"{latest.get('year')}-{latest.get('period', '').lstrip('M')}",
        )
        count += 1
    db.commit()
    logger.info("Loaded BLS labor_employment overlay for %d counties", count)
    return count


def load_all_overlays(db: Session, *, bls_year: str | None = None) -> dict[str, int]:
    """Batch entry point: populate every overlay this module knows how to
    build. Safe to re-run -- _store_overlay upserts by the unique key."""
    results = {
        "acs_district_housing": load_acs_district_overlays(db, badge_slug="housing"),
        "acs_district_infrastructure_transportation": load_acs_district_overlays(
            db, badge_slug="infrastructure_transportation"
        ),
        "acs_county_housing": load_acs_county_overlays(db, badge_slug="housing"),
        "acs_county_infrastructure_transportation": load_acs_county_overlays(
            db, badge_slug="infrastructure_transportation"
        ),
        # Latest month available: the current year's series, or last year's
        # early in January before the first release.
        "bls_county_labor_employment": load_bls_county_unemployment(db, year=bls_year or str(date.today().year))
        or load_bls_county_unemployment(db, year=str(date.today().year - 1)),
    }
    logger.info("Demographic overlay batch load complete: %s", results)
    return results


if __name__ == "__main__":
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    session = SessionLocal()
    try:
        totals = load_all_overlays(session)
        for name, n in totals.items():
            print(f"{name}: {n}")
    finally:
        session.close()
