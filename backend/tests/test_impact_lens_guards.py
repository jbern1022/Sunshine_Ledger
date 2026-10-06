"""Guards added after the first real run (H1389, 2026-10-06). Each case is a
real entry the unguarded mapper got wrong."""

from app.impact_lens import criteria as C
from app.impact_lens import guards

DATE_COND = {"text": "submitted an application, written request, or notice of intent before July 1, 2026",
             "quote": "who submitted an application ... before July 1, 2026"}
AIRPORT = {"text": "Sections 125.01055(7) and 166.04151(7) do not apply to any of the following, unless the respective application is approved by the governing body of the airport: (a) A proposed development near a runway within one- quarter of a mile (b) A proposed development within any airport noise zone",
           "quote": "Sections 125.01055(7) and 166.04151(7) do not apply to\nany of the following ...\n(a) A proposed development near a runway\n(b) A proposed development within any airport noise zone"}


def run(raw, entry, **kw):
    return C.validate_criteria(
        raw, entry_index=0, n_conditions=len(entry.get("conditions") or []),
        n_exceptions=len(entry.get("exceptions") or []), entry=entry, **kw)


def role(*roles):
    return {"kind": "attr", "attr": "role", "any_of": list(roles)}


def test_anyone_is_only_for_a_group_the_bill_calls_anyone():
    oppaga = {"group": "Office of Program Policy Analysis and Government Accountability (OPPAGA)"}
    out = run({"audience": {"kind": "anyone"}}, oppaga)
    assert out["audience"] is None and "only for a group the bill calls Anyone" in out["unmapped"][0]["reason"]
    assert run({"audience": {"kind": "anyone"}}, {"group": "Courts"})["audience"] is None
    assert run({"audience": {"kind": "anyone"}}, {"group": "Anyone"})["audience"] == {"kind": "anyone"}
    assert run({"audience": {"kind": "anyone"}}, {"group": "any person"})["audience"] == {"kind": "anyone"}


def test_a_role_must_be_named_by_the_group():
    county = {"group": "County"}
    out = run({"audience": role("property_developer", "local_government")}, county)
    assert out["audience"]["any_of"] == ["local_government"]
    assert out["notes"] == ["audience: dropped 'property_developer' (the group 'County' does not name it)"]
    # a county rule the model called "developer" is corrected from the group's own words
    assert run({"audience": role("property_developer")}, {"group": "Municipality"})["audience"]["any_of"] == ["local_government"]
    assert run({"audience": role("local_government")}, {"group": "Counties and municipalities"})["audience"]["any_of"] == ["local_government"]
    assert run({"audience": role("landlord")}, {"group": "Landlords"})["audience"]["any_of"] == ["landlord"]
    # an "applicant" may be a landowner, not a developer: not enough to name the role
    assert run({"audience": role("property_developer")}, {"group": "Applicants for development authorized under s. 125.01055(7)"})["audience"] is None
    assert run({"audience": role("property_developer")}, {"group": "Developer"})["audience"]["any_of"] == ["property_developer"]


def test_a_date_is_never_mapped_to_a_property_type():
    entry = {"group": "Developers", "conditions": [DATE_COND]}
    raw = {"audience": role("property_developer"),
           "requires": [{"attr": "property_type", "op": "in", "values": ["multifamily", "commercial"], "from": {"kind": "condition", "index": 0}}]}
    out = run(raw, entry)
    assert out["requires"] == []
    assert out["unmapped"] == [{"kind": "condition", "index": 0, "reason": "it mentions a date, number or amount the vocabulary cannot test"}]


def test_airport_exception_lists_are_not_mapped_to_a_property_type():
    entry = {"group": "Farms and farm operations", "exceptions": [AIRPORT]}
    raw = {"excludes": [{"attr": "property_type", "op": "in", "values": ["commercial"], "from": {"kind": "exception", "index": 0}}]}
    out = run(raw, entry)
    assert out["excludes"] == [] and out["unmapped"][-1]["reason"] == "it is too long or compound to map exactly"


def test_a_value_must_appear_in_the_cited_text():
    entry = {"group": "Landlords", "conditions": [{"text": "Applies in Duval County.", "quote": "This section applies in Duval County."}]}
    raw = {"audience": role("landlord"),
           "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Duval", "county:Orange"], "from": {"kind": "condition", "index": 0}}]}
    out = run(raw, entry)
    assert out["requires"][0]["values"] == ["county:Duval"]
    assert out["notes"] == ["condition 0: dropped 'county:Orange' (the condition does not state it)"]
    nothing = run({**raw, "requires": [{**raw["requires"][0], "values": ["county:Orange"]}]}, entry)
    assert nothing["requires"] == [] and "does not state any" in nothing["unmapped"][0]["reason"]


def test_statute_citations_do_not_count_as_numbers():
    ok = {"text": "Applies in Duval County under s. 125.01055(7), Florida Statutes.", "quote": "In Duval County, as provided in ss. 166.04151(7)."}
    assert guards.too_complex(ok["text"], ok["quote"]) is None
    assert guards.too_complex("Applies to buildings over 3 stories.", "") is not None
    assert guards.too_complex("A 40 percent share is required", "") is not None


def test_a_clean_entry_still_maps_fully():
    entry = {"group": "Landlords",
             "conditions": [{"text": "Applies in Duval and Miami-Dade counties.", "quote": "This section applies in Duval County and Miami-Dade County."}],
             "exceptions": [{"text": "Not single-family homes rented by their owner.", "quote": "This section does not apply to a single-family home rented by its owner."}]}
    raw = {"audience": role("landlord"),
           "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Duval", "county:Miami-Dade"], "from": {"kind": "condition", "index": 0}}],
           "excludes": [{"attr": "property_type", "op": "in", "values": ["single_family"], "from": {"kind": "exception", "index": 0}}]}
    out = run(raw, entry)
    assert C.is_fully_mapped(out) and out["notes"] == []


def test_a_rejected_audience_falls_back_to_the_groups_own_words():
    out = run({"audience": {"kind": "anyone"}}, {"group": "Counties and municipalities"})
    assert out["audience"] == {"kind": "attr", "attr": "role", "any_of": ["local_government"]}
    assert out["notes"] == ["audience: taken from the group's own words ('Counties and municipalities'), not from the model"]
    assert run({}, {"group": "County"})["audience"]["any_of"] == ["local_government"]
    # no role in the group's words: stays unmapped, never guessed
    assert run({"audience": {"kind": "anyone"}}, {"group": "Courts"})["audience"] is None
    assert run({}, {"group": "Anyone"})["audience"] is None
    assert run({"audience": role("property_developer")}, {"group": "Owner of a property in a multifamily project"})["audience"] is None


def test_a_role_word_must_be_the_head_noun_of_the_group():
    # S1166 entry 6: small employer carriers are insurers, not employers
    assert run({"audience": role("employer")}, {"group": "Small employer carriers"})["audience"] is None
    assert run({"audience": role("employer")}, {"group": "Employers"})["audience"]["any_of"] == ["employer"]
    assert run({"audience": role("employer")}, {"group": "Each employer"})["audience"]["any_of"] == ["employer"]
    assert run({"audience": role("renter")}, {"group": "Tenants in covered properties"})["audience"]["any_of"] == ["renter"]
    assert run({"audience": role("landlord")}, {"group": "Landlords of residential property"})["audience"]["any_of"] == ["landlord"]
    for g in ("County or municipality", "Counties and municipalities", "Local government", "Municipality"):
        assert run({}, {"group": g})["audience"]["any_of"] == ["local_government"], g
    # a county word inside a longer noun phrase is not the group
    assert run({}, {"group": "County tax collectors"})["audience"] is None


def test_a_role_cannot_be_used_as_a_condition_or_exception():
    entry = {"group": "Health maintenance organizations",
             "exceptions": [{"text": "unless the contract is for a small employer", "quote": "unless the contract is for a small employer"}]}
    out = run({"excludes": [{"attr": "role", "op": "in", "values": ["employer"], "from": {"kind": "exception", "index": 0}}]}, entry)
    assert out["excludes"] == []
    assert out["unmapped"][-1] == {"kind": "exception", "index": 0, "reason": "'role' can only be an audience, not a condition"}


def test_the_affected_party_must_be_mentioned_in_the_entrys_own_words():
    entry = {"group": "Each health insurer", "text": "shall disclose to every insured that payments count toward the deductible",
             "quote": "A health insurer shall disclose to each policyholder that ..."}
    aff = {"kind": "attr", "attr": "role", "any_of": ["insured", "renter", "healthcare_provider"]}
    out = run({"affected": aff}, entry)
    assert out["affected"] == {"kind": "attr", "attr": "role", "any_of": ["insured"]}
    assert out["notes"] == ["affected: dropped 'renter' (the entry's own words do not mention it)",
                            "affected: dropped 'healthcare_provider' (the entry's own words do not mention it)"]
    assert C.review_tier(out) == "needs_review"  # an affected party always needs a person
    assert run({}, entry)["affected"] is None
    assert run({"affected": {"kind": "anyone"}}, entry)["affected"] is None
    # a role already bound by the group is not repeated as affected
    both = run({"audience": role("healthcare_provider"), "affected": {"kind": "attr", "attr": "role", "any_of": ["healthcare_provider", "insured"]}},
               {"group": "Treating physicians", "text": "must notify the insured", "quote": "The physician shall notify the insured."})
    assert both["audience"]["any_of"] == ["healthcare_provider"] and both["affected"]["any_of"] == ["insured"]


def test_insured_and_provider_roles_are_head_nouns_of_their_groups():
    assert run({}, {"group": "Treating physicians"})["audience"]["any_of"] == ["healthcare_provider"]
    assert run({}, {"group": "Insureds"})["audience"]["any_of"] == ["insured"]
    assert run({}, {"group": "Health maintenance organizations"})["audience"] is None
    assert run({}, {"group": "Pharmacy benefit managers"})["audience"] is None


def test_a_protected_person_offered_as_the_audience_moves_to_affected():
    insurer = {"group": "Each health insurer", "text": "shall disclose to every insured that payments count toward the deductible",
               "quote": "A health insurer shall disclose to each policyholder that ..."}
    out = run({"audience": role("insured")}, insurer)
    assert out["audience"] is None and out["affected"] == {"kind": "attr", "attr": "role", "any_of": ["insured"]}
    assert out["notes"] == ["audience: moved 'insured' to the affected party (the group 'Each health insurer' does not name it, the entry's words do)"]
    # merged with what the model already put in `affected`, no duplicates
    both = run({"audience": role("insured"), "affected": {"kind": "attr", "attr": "role", "any_of": ["insured", "healthcare_provider"]}},
               {**insurer, "text": insurer["text"] + " and to each physician"})
    assert both["affected"]["any_of"] == ["insured", "healthcare_provider"]


def test_only_people_roles_move_and_only_when_the_entry_mentions_them():
    taxing = {"group": "Taxing authority", "text": "must find that a county that is part of its jurisdiction is in a region ...", "quote": "a county that is part of the jurisdiction"}
    out = run({"audience": role("local_government")}, taxing)
    assert out["affected"] is None  # a government is never moved, only dropped
    farm = {"group": "Farms and farm operations", "text": "are excluded from commercial use", "quote": "are not commercial use"}
    out2 = run({"audience": role("renter", "homeowner")}, farm)
    assert out2["affected"] is None and out2["audience"] is None  # not mentioned: dropped
