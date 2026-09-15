from sqlalchemy import select

import pytest

from app.models import DemographicOverlay
from app.pipeline.demographic_overlay import (
    ACSClient,
    ACSError,
    _acs_metrics,
    _num,
    _store_overlay,
    county_unemployment_series_id,
    load_acs_county_overlays,
    load_acs_district_overlays,
    load_bls_county_unemployment,
)


def test_acs_client_requires_an_api_key():
    with pytest.raises(ACSError, match="CENSUS_API_KEY"):
        ACSClient(api_key="")


# --- _num --------------------------------------------------------------


def test_num_parses_a_normal_value():
    assert _num("75372") == 75372.0


def test_num_treats_census_suppression_sentinel_as_missing():
    assert _num("-666666666") is None


def test_num_handles_none_and_garbage():
    assert _num(None) is None
    assert _num("N/A") is None


# --- _acs_metrics --------------------------------------------------------


def test_acs_metrics_pairs_estimate_and_moe_with_per_variable_unit():
    table = [("B25003_001", "Total occupied housing units", "housing units")]
    values = {"B25003_001E": "75372", "B25003_001M": "1245"}
    assert _acs_metrics(values, table) == [
        {"label": "Total occupied housing units", "estimate": 75372.0, "margin_of_error": 1245.0, "unit": "housing units"}
    ]


# --- county_unemployment_series_id ---------------------------------------


def test_county_unemployment_series_id_matches_live_verified_format():
    # Confirmed live 2026-09-15 against the real BLS API for Miami-Dade.
    assert county_unemployment_series_id("086") == "LAUCN120860000000003"


# --- load_acs_district_overlays (fake client) -----------------------------


class FakeACSClient:
    def __init__(self, by_district=None, by_county=None):
        self._by_district = by_district or {}
        self._by_county = by_county or {}
        self.district_calls = []
        self.county_calls = []

    def get_by_district(self, variables, *, chamber):
        self.district_calls.append(chamber)
        return self._by_district.get(chamber, {})

    def get_by_county(self, variables, *, county_fips):
        self.county_calls.append(county_fips)
        return self._by_county.get(county_fips, {})


class FakeBLSClient:
    def __init__(self, series_data=None):
        self._series_data = series_data or {}

    def get_series(self, series_ids, *, start_year, end_year):
        return {sid: self._series_data.get(sid, []) for sid in series_ids}


def test_load_acs_district_overlays_stores_both_chambers(db_session):
    client = FakeACSClient(
        by_district={
            "HD": {"101": {"B25003_001E": "75372", "B25003_001M": "1245", "B25003_002E": "38959", "B25003_002M": "1242", "B25003_003E": "36413", "B25003_003M": "1570"}},
            "SD": {"024": {"B25003_001E": "200000", "B25003_001M": "5000", "B25003_002E": "100000", "B25003_002M": "3000", "B25003_003E": "100000", "B25003_003M": "3000"}},
        }
    )

    count = load_acs_district_overlays(db_session, badge_slug="housing", client=client)

    assert count == 2
    hd = db_session.execute(
        select(DemographicOverlay).where(DemographicOverlay.geography_id == "HD-101")
    ).scalar_one()
    assert hd.geography_type == "district"
    assert hd.badge_slug == "housing"
    assert hd.source == "acs"
    assert hd.metrics[0]["estimate"] == 75372.0
    assert hd.metrics[0]["margin_of_error"] == 1245.0

    sd = db_session.execute(
        select(DemographicOverlay).where(DemographicOverlay.geography_id == "SD-024")
    ).scalar_one()
    assert sd.geography_type == "district"


def test_load_acs_district_overlays_is_idempotent_upsert(db_session):
    client = FakeACSClient(by_district={"HD": {"101": {"B25003_001E": "1", "B25003_001M": "1", "B25003_002E": "1", "B25003_002M": "1", "B25003_003E": "1", "B25003_003M": "1"}}, "SD": {}})
    load_acs_district_overlays(db_session, badge_slug="housing", client=client)

    updated_client = FakeACSClient(by_district={"HD": {"101": {"B25003_001E": "999", "B25003_001M": "1", "B25003_002E": "1", "B25003_002M": "1", "B25003_003E": "1", "B25003_003M": "1"}}, "SD": {}})
    load_acs_district_overlays(db_session, badge_slug="housing", client=updated_client)

    rows = db_session.execute(
        select(DemographicOverlay).where(DemographicOverlay.geography_id == "HD-101")
    ).scalars().all()
    assert len(rows) == 1  # no duplicate row
    assert rows[0].metrics[0]["estimate"] == 999.0  # value refreshed in place


def test_load_acs_district_overlays_rejects_unmapped_badge(db_session):
    import pytest

    with pytest.raises(ValueError, match="No ACS table mapping"):
        load_acs_district_overlays(db_session, badge_slug="not_a_real_badge", client=FakeACSClient())


def test_load_acs_county_overlays_stores_both_covered_counties(db_session):
    client = FakeACSClient(
        by_county={
            "086": {"B08303_001E": "500000", "B08303_001M": "4000"},
            "031": {"B08303_001E": "433097", "B08303_001M": "4310"},
        }
    )

    count = load_acs_county_overlays(db_session, badge_slug="infrastructure_transportation", client=client)

    assert count == 2
    row = db_session.execute(
        select(DemographicOverlay).where(DemographicOverlay.geography_id == "Duval County")
    ).scalar_one()
    assert row.geography_type == "county"
    assert row.metrics[0]["unit"] == "minutes (aggregate, all workers)"


def test_load_bls_county_unemployment_has_no_margin_of_error(db_session):
    client = FakeBLSClient(
        series_data={
            "LAUCN120860000000003": [{"year": "2024", "period": "M12", "value": "2.5"}],
            "LAUCN120310000000003": [{"year": "2024", "period": "M12", "value": "3.3"}],
        }
    )

    count = load_bls_county_unemployment(db_session, year="2024", client=client)

    assert count == 2
    row = db_session.execute(
        select(DemographicOverlay).where(
            DemographicOverlay.geography_id == "Miami-Dade County", DemographicOverlay.source == "bls"
        )
    ).scalar_one()
    assert row.badge_slug == "labor_employment"
    assert row.metrics[0]["estimate"] == 2.5
    assert row.metrics[0]["margin_of_error"] is None  # BLS doesn't publish one -- expected, not a bug
    assert row.as_of == "2024-12"


def test_load_bls_county_unemployment_skips_county_with_no_data(db_session, caplog):
    # Only Duval's series has data; Miami-Dade's comes back empty.
    client = FakeBLSClient(series_data={"LAUCN120310000000003": [{"year": "2024", "period": "M12", "value": "3.3"}]})
    count = load_bls_county_unemployment(db_session, year="2024", client=client)
    assert count == 1  # only Duval stored
    assert db_session.execute(
        select(DemographicOverlay).where(DemographicOverlay.geography_id == "Miami-Dade County")
    ).first() is None


def test_store_overlay_upserts_by_unique_key(db_session):
    first = _store_overlay(
        db_session, geography_type="county", geography_id="Duval County", badge_slug="housing",
        source="acs", metrics=[{"label": "x", "estimate": 1.0, "margin_of_error": None, "unit": "u"}], as_of="2022",
    )
    db_session.commit()

    second = _store_overlay(
        db_session, geography_type="county", geography_id="Duval County", badge_slug="housing",
        source="acs", metrics=[{"label": "x", "estimate": 2.0, "margin_of_error": None, "unit": "u"}], as_of="2023",
    )
    db_session.commit()

    assert first.id == second.id  # same row, updated in place
    rows = db_session.execute(select(DemographicOverlay)).scalars().all()
    assert len(rows) == 1
    assert rows[0].metrics[0]["estimate"] == 2.0
    assert rows[0].as_of == "2023"
