"""Impact Lens vocabulary and criteria validation (phase 1)."""

import pytest

from app.impact_lens import criteria as C
from app.impact_lens.vocabulary import (
    FLORIDA_COUNTIES, MUNICIPALITY_COUNTIES, NUMBER, REGISTRY, Attribute, county_value,
    is_forbidden, jurisdiction_label, municipality_value,
)


def validate(raw, conditions=1, exceptions=1, **kw):
    return C.validate_criteria(raw, entry_index=0, n_conditions=conditions, n_exceptions=exceptions, **kw)


GOOD = {
    "audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]},
    "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Duval", "county:Miami-Dade"],
                  "from": {"kind": "condition", "index": 0}}],
    "excludes": [{"attr": "property_type", "op": "in", "values": ["single_family"],
                  "from": {"kind": "exception", "index": 0}}],
}


def test_jurisdiction_covers_counties_and_municipalities():
    values = set(REGISTRY["jurisdiction"].values)
    assert len(FLORIDA_COUNTIES) == 67 and len(set(FLORIDA_COUNTIES)) == 67
    assert len(MUNICIPALITY_COUNTIES) == 412
    assert county_value("Duval") in values and municipality_value("Jacksonville") in values
    # every municipality lies in real counties; a few span two
    assert all(c in FLORIDA_COUNTIES for cs in MUNICIPALITY_COUNTIES.values() for c in cs)
    assert MUNICIPALITY_COUNTIES["Jacksonville"] == ("Duval",)
    assert MUNICIPALITY_COUNTIES["Longboat Key"] == ("Manatee", "Sarasota")
    assert jurisdiction_label("county:Duval") == "Duval County"
    assert jurisdiction_label("municipality:Miami") == "Miami (municipality)"


def test_one_condition_can_mix_counties_and_municipalities():
    mixed = {**GOOD, "requires": [{"attr": "jurisdiction", "op": "in", "from": {"kind": "condition", "index": 0},
                                   "values": ["county:Duval", "municipality:Miami"]}]}
    out = validate(mixed)
    assert out["requires"][0]["values"] == ["county:Duval", "municipality:Miami"]
    # a bare name, with no level, is not a value
    bare = validate({**mixed, "requires": [{**mixed["requires"][0], "values": ["Duval"]}]})
    assert bare["requires"] == []


def test_registry_has_no_forbidden_dimension():
    assert not [k for k in REGISTRY if is_forbidden(k)]
    assert REGISTRY["role"].audience and not REGISTRY["jurisdiction"].audience


@pytest.mark.parametrize("key", ["immigration_status", "household_income_exact", "political_party", "religion", "home_address"])
def test_excluded_dimensions_are_refused(key):
    assert is_forbidden(key)
    out = validate({**GOOD, "requires": [{"attr": key, "op": "in", "values": ["x"], "from": {"kind": "condition", "index": 0}}]})
    assert out["requires"] == []
    assert out["unmapped"] == [{"kind": "condition", "index": 0, "reason": f"'{key}' is an excluded dimension"}]


def test_a_good_mapping_is_kept_and_fully_mapped():
    out = validate(GOOD)
    assert out["audience"] == {"kind": "attr", "attr": "role", "any_of": ["landlord"]}
    assert out["requires"][0]["from"] == {"kind": "condition", "index": 0}
    assert out["excludes"][0]["values"] == ["single_family"]
    assert out["unmapped"] == [] and C.is_fully_mapped(out)
    assert out["vocabulary_version"] == 1 and out["relevance"] == "direct"


def test_unknown_attribute_or_value_is_unmapped_not_kept():
    bad_attr = validate({**GOOD, "requires": [{"attr": "lease_start", "op": "in", "values": ["x"],
                                               "from": {"kind": "condition", "index": 0}}]})
    assert bad_attr["unmapped"][0]["reason"] == "'lease_start' is not in the vocabulary"
    bad_val = validate({**GOOD, "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Gotham"],
                                              "from": {"kind": "condition", "index": 0}}]})
    assert bad_val["requires"] == [] and "county:Gotham" in bad_val["unmapped"][0]["reason"]
    assert not C.is_fully_mapped(bad_val)


def test_a_pointer_must_be_the_right_kind_and_in_range():
    wrong_kind = validate({**GOOD, "requires": [{**GOOD["requires"][0], "from": {"kind": "exception", "index": 0}}]})
    assert wrong_kind["requires"] == []
    out_of_range = validate({**GOOD, "excludes": [{**GOOD["excludes"][0], "from": {"kind": "exception", "index": 5}}]})
    assert out_of_range["excludes"] == []
    # Either way the entry's real exception still shows up as unmapped.
    assert {"kind": "exception", "index": 0} == {k: out_of_range["unmapped"][0][k] for k in ("kind", "index")}


def test_nothing_is_dropped_silently():
    out = validate({"audience": GOOD["audience"]}, conditions=2, exceptions=1)
    assert [(u["kind"], u["index"]) for u in out["unmapped"]] == [("condition", 0), ("condition", 1), ("exception", 0)]
    assert all(u["reason"] == "the mapper did not address it" for u in out["unmapped"])


def test_the_mappers_own_unmapped_reason_is_kept():
    out = validate({"audience": GOOD["audience"], "unmapped": [{"kind": "condition", "index": 0, "reason": "depends on the lease date"}]},
                   conditions=1, exceptions=0)
    assert out["unmapped"] == [{"kind": "condition", "index": 0, "reason": "depends on the lease date"}]


def test_audience_anyone_unmapped_and_non_audience_attribute():
    assert validate({"audience": {"kind": "anyone"}}, 0, 0)["audience"] == {"kind": "anyone"}
    none = validate({}, 0, 0)
    assert none["audience"] is None and none["unmapped"][0] == {"kind": "audience", "index": None, "reason": "the group was not mapped"}
    county = validate({"audience": {"kind": "attr", "attr": "jurisdiction", "any_of": ["county:Duval"]}}, 0, 0)
    assert county["audience"] is None and "cannot be an audience" in county["unmapped"][0]["reason"]
    bad_role = validate({"audience": {"kind": "attr", "attr": "role", "any_of": ["wizard"]}}, 0, 0)
    assert bad_role["audience"] is None and not C.is_fully_mapped(bad_role)


def test_garbage_input_never_raises_and_maps_nothing():
    for raw in (None, "text", [], 3, {"requires": "x", "excludes": 5, "audience": 7, "unmapped": {"a": 1}}):
        out = validate(raw, conditions=1, exceptions=1)
        assert out["audience"] is None and out["requires"] == [] and out["excludes"] == []
        assert len(out["unmapped"]) == 3  # audience, condition 0, exception 0


def test_ambiguity_needs_a_verified_quote():
    q = "The agency shall adopt rules."
    ok = validate({**GOOD, "ambiguous": {"question": "Which agency?", "quote": q}}, entry_quotes={q})
    assert ok["ambiguous"] == {"question": "Which agency?", "quote": q} and not C.is_fully_mapped(ok)
    bad = validate({**GOOD, "ambiguous": {"question": "Which agency?", "quote": "invented"}}, entry_quotes={q})
    assert bad["ambiguous"] is None and bad["unmapped"][-1]["kind"] == "ambiguity"


def test_numeric_operators_with_a_custom_registry():
    reg = {**REGISTRY, "units": Attribute("units", "Units", NUMBER, "How many units?")}
    mk = lambda op, vals: validate({**GOOD, "requires": [{"attr": "units", "op": op, "values": vals, "from": {"kind": "condition", "index": 0}}]}, registry=reg)
    assert mk("gte", [70])["requires"][0]["values"] == [70]
    assert mk("between", [10, 50])["requires"]
    assert mk("between", [50, 10])["requires"] == []
    assert mk("gte", [1, 2])["requires"] == []
    assert mk("in", ["a"])["requires"] == []  # wrong operator for a number
    assert mk("gte", ["70"])["requires"] == []


def test_relevance_must_be_known():
    assert validate(GOOD, relevance="indirect")["relevance"] == "indirect"
    with pytest.raises(ValueError):
        validate(GOOD, relevance="maybe")
