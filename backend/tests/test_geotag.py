"""Tests for BRD 5.3 geographic scope tagging (app.pipeline.geotag).
Pure-function, no DB, no network -- uses the real fl_jurisdictions.json
data file (not a fixture copy) so a future edit to that file that breaks
matching shows up here instead of only in production ingestion."""

from app.pipeline.geotag import GeoTag, tag_bill_geography


def test_falls_back_to_the_default_when_no_jurisdiction_is_named():
    tag = tag_bill_geography(
        "This act relates to general education funding statewide.",
        default_scope_type="statewide",
        default_scope_names=["FL"],
    )
    assert tag == GeoTag(scope_type="statewide", scope_names=["FL"])


def test_none_bill_text_falls_back_to_the_default():
    tag = tag_bill_geography(None, default_scope_type="statewide", default_scope_names=["FL"])
    assert tag == GeoTag(scope_type="statewide", scope_names=["FL"])


def test_narrows_to_a_named_county():
    tag = tag_bill_geography(
        "This act applies only to Miami-Dade County.",
        default_scope_type="statewide",
        default_scope_names=["FL"],
    )
    assert tag == GeoTag(scope_type="county", scope_names=["Miami-Dade County"])


def test_county_matching_is_case_insensitive():
    tag = tag_bill_geography(
        "applies to miami-dade county residents",
        default_scope_type="statewide",
        default_scope_names=["FL"],
    )
    assert tag.scope_names == ["Miami-Dade County"]


def test_matches_multiple_named_counties():
    tag = tag_bill_geography(
        "This act applies to Broward County and Palm Beach County.",
        default_scope_type="statewide",
        default_scope_names=["FL"],
    )
    assert tag.scope_type == "county"
    assert set(tag.scope_names) == {"Broward County", "Palm Beach County"}


def test_county_match_takes_priority_over_a_city_match_in_the_same_text():
    # Counties are checked first and return immediately -- a bill naming
    # both a county and a city inside that county should be scoped to the
    # county, not diluted to city-level.
    tag = tag_bill_geography(
        "This act applies to the City of Miami within Miami-Dade County.",
        default_scope_type="statewide",
        default_scope_names=["FL"],
    )
    assert tag.scope_type == "county"
    assert tag.scope_names == ["Miami-Dade County"]


def test_narrows_to_a_named_city_when_no_county_is_named():
    tag = tag_bill_geography(
        "This ordinance applies within Jacksonville city limits.",
        default_scope_type="city",
        default_scope_names=["Duval County"],
    )
    assert tag == GeoTag(scope_type="city", scope_names=["Jacksonville"])


def test_word_boundary_prevents_matching_inside_a_longer_word():
    # "Duval Countywide" should not match "Duval County" -- there's no word
    # boundary between "County" and the "wide" that runs straight into it.
    tag = tag_bill_geography(
        "This is a Duval Countywide initiative with no county-specific carve-out.",
        default_scope_type="statewide",
        default_scope_names=["FL"],
    )
    assert tag == GeoTag(scope_type="statewide", scope_names=["FL"])
