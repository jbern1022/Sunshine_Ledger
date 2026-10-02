import json

from app.pipeline.bill_layers import MAX_WHO_WINDOWS, METHOD_VERSIONS, WHO_IT_AFFECTS_PROMPT, build_who_it_affects

BILL = (
    "A bill to be entitled An act relating to deposits; requiring landlords to return deposits; providing an effective date.\n"
    "Section 1. Section 83.49, Florida Statutes, is amended to read:\n"
    "(1) A landlord shall return a tenant's security deposit within 15 days after the tenant vacates the dwelling unit.\n"
    "(2) This section does not apply to a landlord who owns fewer than three dwelling units.\n"
    "Section 2. A tenant who is 65 years of age or older may apply to the county for a rent assistance grant.\n"
    "(3) A grant under this section is available only in a county with a population of more than 1 million.\n"
    "Section 3. This act shall take effect July 1, 2027.\n"
)


class FakeClient:
    model = "fake:1"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, prompt, *, json_mode=False):
        assert json_mode
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def _landlord(**over):
    item = {
        "group": "Landlords",
        "change": "Must return a tenant's security deposit within 15 days after the tenant moves out.",
        "change_kind": "obligation",
        "quote": "A landlord shall return a tenant's security deposit within 15 days after the tenant vacates the dwelling unit.",
        "conditions": [],
        "exceptions": [{
            "text": "Landlords who own fewer than three units are not covered.",
            "quote": "This section does not apply to a landlord who owns fewer than three dwelling units.",
        }],
    }
    item.update(over)
    return item


def test_keeps_an_entry_with_who_what_why_and_a_quoted_exception():
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [_landlord()]}))
    assert r.evidence_state == "supported"
    [item] = r.items
    assert item["group"] == "Landlords"
    assert item["change_kind"] == "obligation"
    assert item["text"].startswith("Must return")
    # The "why" is the bill's own sentence, located in the text, with the
    # section derived from where it sits rather than taken from the model.
    assert item["quote"].startswith("A landlord shall return")
    assert item["section_ref"] == "Section 1"
    assert item["exceptions"][0]["quote"].startswith("This section does not apply")
    assert item["affected_groups"] == ["Landlords"]


def test_drops_an_entry_whose_supporting_quote_is_not_in_the_bill():
    bad = _landlord(quote="A landlord must pay interest on every deposit.")
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [bad]}))
    assert r.evidence_state == "insufficient_evidence"
    assert r.items == []
    assert r.dropped == [bad]


def test_never_keeps_an_exception_the_bill_does_not_state():
    invented = _landlord(exceptions=[{
        "text": "Small landlords are exempt.",
        "quote": "Landlords with one property are exempt from this section.",
    }])
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [invented]}))
    [item] = r.items
    # Only the bill's own exclusion (R4), never the invented one.
    assert [x["quote"] for x in item["exceptions"]] == [
        "This section does not apply to a landlord who owns fewer than three dwelling units.",
    ]


def test_conditions_are_kept_only_when_quoted_from_the_bill():
    grant = {
        "group": "Tenants 65 or older",
        "change": "May apply to the county for a rent assistance grant.",
        "change_kind": "eligibility",
        "quote": "A tenant who is 65 years of age or older may apply to the county for a rent assistance grant.",
        "conditions": [
            {"text": "Only in counties of more than 1 million people.",
             "quote": "A grant under this section is available only in a county with a population of more than 1 million."},
            {"text": "Only for low-income tenants.", "quote": "Grants are limited to low-income tenants."},
        ],
        "exceptions": [],
    }
    r = build_who_it_affects("HB 1", "Grants", BILL, FakeClient({"items": [grant]}))
    [item] = r.items
    # "may apply" is eligibility, not a forecast -- it is kept.
    assert item["change_kind"] == "eligibility"
    assert [c["text"] for c in item["conditions"]] == ["Only in counties of more than 1 million people."]
    assert item["section_ref"] == "Section 2"


def test_downstream_effects_are_left_to_expected_effect():
    rents = _landlord(group="Tenants", change="Rents could rise as landlords pass on compliance costs.", change_kind="cost")
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [rents, _landlord()]}))
    assert [i["group"] for i in r.items] == ["Landlords"]
    assert r.dropped == [rents]


def test_one_group_may_appear_in_several_roles():
    as_landlord = _landlord(group="Small-business owners")
    as_tenant = {
        "group": "Small-business owners",
        "change": "May apply for a rent assistance grant if 65 or older.",
        "change_kind": "eligibility",
        "quote": "A tenant who is 65 years of age or older may apply to the county for a rent assistance grant.",
        "conditions": [], "exceptions": [],
    }
    r = build_who_it_affects("HB 1", "Mixed", BILL, FakeClient({"items": [as_landlord, as_tenant]}))
    assert [i["change_kind"] for i in r.items] == ["obligation", "eligibility"]


def test_unknown_change_kind_becomes_other_and_empty_entries_are_skipped():
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [
        _landlord(change_kind="vibes"),
        {"group": "", "change": "", "quote": ""},
    ]}))
    assert [i["change_kind"] for i in r.items] == ["other"]


def test_requirement_wording_for_a_may_provision_is_dropped():
    overstated = {
        "group": "Tenants 65 or older",
        "change": "Must apply to the county for a rent assistance grant.",
        "change_kind": "obligation",
        "quote": "A tenant who is 65 years of age or older may apply to the county for a rent assistance grant.",
        "conditions": [], "exceptions": [],
    }
    r = build_who_it_affects("HB 1", "Grants", BILL, FakeClient({"items": [overstated]}))
    assert r.items == []


def test_prompt_and_method_version():
    client = FakeClient({"items": []})
    r = build_who_it_affects("HB 1", "Deposits", BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "No group the bill directly applies to could be tied to its text"
    assert "Do not invent" in WHO_IT_AFFECTS_PROMPT
    assert "HB 1" in client.prompts[0]
    assert METHOD_VERSIONS[("who_it_affects", "sunshine_ledger_ai")] == "who_it_affects/sunshine_ledger_ai/2"


def test_quotes_from_the_title_paragraph_are_not_the_law():
    title = _landlord(quote="requiring landlords to return deposits")
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [title]}))
    assert r.items == [] and r.dropped == [title]


def test_the_effective_date_is_never_a_condition():
    item = _landlord(conditions=[{"text": "Starts July 1, 2027.", "quote": "This act shall take effect July 1, 2027."}])
    [kept] = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [item]})).items
    assert kept["conditions"] == []


def test_a_requirement_needs_a_mandatory_quote():
    # The bill says "may apply"; the entry says "must apply" with the quote's
    # wording changed enough that the sentence matcher alone might miss it.
    item = {
        "group": "Older tenants", "change": "Must file with the county to get a grant.", "change_kind": "obligation",
        "quote": "A tenant who is 65 years of age or older may apply to the county for a rent assistance grant.",
        "conditions": [], "exceptions": [],
    }
    assert build_who_it_affects("HB 1", "Grants", BILL, FakeClient({"items": [item]})).items == []


def test_a_may_provision_labeled_obligation_becomes_a_permission():
    item = {
        "group": "Tenants 65 or older", "change": "May apply to the county for a rent assistance grant.",
        "change_kind": "obligation",
        "quote": "A tenant who is 65 years of age or older may apply to the county for a rent assistance grant.",
        "conditions": [], "exceptions": [],
    }
    [kept] = build_who_it_affects("HB 1", "Grants", BILL, FakeClient({"items": [item]})).items
    assert kept["change_kind"] == "permission"


def test_a_window_that_is_all_title_has_nothing_operative():
    long_title = "A bill to be entitled An act relating to insurance; " + "amending s. 624.01, F.S.; requiring insurers to file reports; " * 3000
    bill = long_title + "\nSection 1. Insurers shall file reports.\n"
    item = {"group": "Insurers", "change": "Must file reports.", "change_kind": "obligation",
            "quote": "requiring insurers to file reports", "conditions": [], "exceptions": []}
    r = build_who_it_affects("HB 9", "Insurance", bill, FakeClient({"items": [item]}))
    assert r.evidence_state == "insufficient_evidence"


def test_a_prohibition_worded_as_a_permission_is_dropped():
    item = _landlord(group="Anyone", change_kind="prohibition", change="May return the deposit within 15 days.")
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [item]}))
    assert r.items == []


# R1 (HB 1389 validation, 2026-10-02): the model saw only the first 12,000
# chars -- Section 1 of 13 -- so every group in Sections 2-12 was missing.
# Who it affects now reads the whole bill, one window of sections at a time.
class SequenceClient:
    """Answers each call with the next payload; records every prompt."""
    model = "fake:1"

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def generate(self, prompt, *, json_mode=False):
        assert json_mode
        self.prompts.append(prompt)
        return json.dumps(self.payloads.pop(0) if self.payloads else {"items": []})


def _section(n: int, sentence: str, size: int = 7_000) -> str:
    filler = "".join(f"({i}) The department shall keep record number {n}-{i} on file.\n" for i in range(size // 55))
    return f"Section {n}. {sentence}\n{filler}"


def _entry(group: str, quote: str, kind: str = "obligation") -> dict:
    change = "Must " + quote.split(" shall ", 1)[1].rstrip(".") if " shall " in quote else quote
    return {"group": group, "change": change, "change_kind": kind, "quote": quote, "conditions": [], "exceptions": []}


TITLE = "A bill to be entitled An act relating to records; amending s. 1.01, F.S.; providing an effective date.\n"
COUNTIES = "Each county shall publish its land records online."
CITIES = "Each municipality shall publish its zoning maps online."
SCHOOLS = "Each school district shall publish its property list online."
LONG_BILL = (
    TITLE
    + _section(1, COUNTIES)
    + _section(2, CITIES)
    + _section(3, SCHOOLS)
    + "Section 4. This act shall take effect July 1, 2027.\n"
)


def test_reads_every_section_of_a_long_bill():
    client = SequenceClient(
        {"items": [_entry("Counties", COUNTIES)]},
        {"items": [_entry("Municipalities", CITIES)]},
        {"items": [_entry("School districts", SCHOOLS)]},
    )
    r = build_who_it_affects("HB 2", "Records", LONG_BILL, client)
    assert len(client.prompts) == 3
    assert [(i["group"], i["section_ref"]) for i in r.items] == [
        ("Counties", "Section 1"), ("Municipalities", "Section 2"), ("School districts", "Section 3"),
    ]
    assert r.scope_note == "Bill text"
    # Each window is the law, never the title.
    assert all("A bill to be entitled" not in p for p in client.prompts)


def test_a_quote_must_be_in_the_window_the_model_saw():
    # The model answering for Section 1's window can't cite Section 3.
    client = SequenceClient({"items": [_entry("School districts", SCHOOLS)]})
    r = build_who_it_affects("HB 2", "Records", LONG_BILL, client)
    assert r.items == [] and len(r.dropped) == 1


def test_later_sections_are_not_crowded_out_by_the_first():
    first = [_entry(f"Group {i}", f"({i}) The department shall keep record number 1-{i} on file.") for i in range(6)]
    client = SequenceClient({"items": first}, {"items": [_entry("Municipalities", CITIES)]}, {"items": []})
    r = build_who_it_affects("HB 2", "Records", LONG_BILL, client)
    assert len(r.items) == 7
    assert [i["group"] for i in r.items][:2] == ["Group 0", "Municipalities"]


def test_a_section_larger_than_one_window_is_split_on_line_breaks():
    big = _section(1, COUNTIES, size=30_000)
    tail = "(999) Each county shall report its totals to the department.\n"
    bill = TITLE + big + tail + "Section 2. This act shall take effect July 1, 2027.\n"
    client = SequenceClient({"items": []}, {"items": []}, {"items": [_entry("Counties", tail.strip())]})
    r = build_who_it_affects("HB 3", "Records", bill, client)
    assert len(client.prompts) == 3
    [item] = r.items
    # The section is found from the whole bill, not the window the quote came from.
    assert item["section_ref"] == "Section 1"


def test_a_very_long_bill_says_which_sections_were_read():
    sections = "".join(_section(n, f"Agency {n} shall publish its records online.", size=11_000) for n in range(1, 8))
    bill = TITLE + sections + "Section 8. This act shall take effect July 1, 2027.\n"
    client = SequenceClient({"items": [_entry("Agency 1", "Agency 1 shall publish its records online.")]})
    r = build_who_it_affects("HB 4", "Records", bill, client)
    assert len(client.prompts) == 4
    assert r.scope_note == "Sections 1-4 of 8"


def test_hb1389_is_read_in_full():
    # The bill that found the gap: stored enrolled text, 13 sections, ~32k chars.
    from pathlib import Path

    text = (Path(__file__).parent / "fixtures" / "bill_text" / "hb1389_2026_enrolled.txt").read_text()
    client = SequenceClient()
    r = build_who_it_affects("H1389", "Affordable Housing", text, client)
    seen = "".join(client.prompts)
    assert len(client.prompts) <= MAX_WHO_WINDOWS
    assert "An act relating to affordable housing" not in seen
    for n in range(1, 14):
        assert f"Section {n}." in seen
    # Sections 1 and 2 (counties, municipalities) are each ~9-10k chars.
    assert "Section 1." in client.prompts[0] and "Section 2." in client.prompts[1]
    assert r.scope_note == "No group the bill directly applies to could be tied to its text"


# R3 (HB 1389 validation): entry 1 quoted "... if at least 40 percent of the
# residential units ... are affordable" and listed no condition. The model
# returned conditions: [] for every item; the condition was in its own quote.
ZONING = (
    "Section 1. A county must authorize multifamily residential as an allowable use in any area zoned for "
    "commercial use; and on property owned by a school district, regardless of the underlying zoning, if at "
    "least 40 percent of the residential units are rental units that, for a period of at least 30 years, are "
    "affordable as defined in s. 420.0004.\n"
    "Section 2. An airport-area development may proceed unless the application is denied by the airport; "
    "the county shall record the decision.\n"
    "Section 3. This act shall take effect July 1, 2026.\n"
)
COUNTY_QUOTE = ZONING.split("\n")[0].removeprefix("Section 1. ")


def _county(**over):
    item = {"group": "Counties", "change": "Must allow multifamily housing in commercial areas.",
            "change_kind": "obligation", "quote": COUNTY_QUOTE, "conditions": [], "exceptions": []}
    item.update(over)
    return item


def test_a_condition_stated_in_the_entrys_own_quote_is_listed():
    [item] = build_who_it_affects("HB 5", "Housing", ZONING, FakeClient({"items": [_county()]})).items
    [cond] = item["conditions"]
    assert cond["quote"].startswith("if at least 40 percent of the residential units")
    assert cond["quote"].endswith("affordable as defined in s. 420.0004")
    assert cond["text"].startswith("If at least 40 percent")


def test_a_condition_the_model_already_listed_is_not_repeated():
    given = {"text": "At least 40% of units affordable for 30 years.",
             "quote": "at least 40 percent of the residential units are rental units"}
    [item] = build_who_it_affects("HB 5", "Housing", ZONING, FakeClient({"items": [_county(conditions=[given])]})).items
    assert [c["text"] for c in item["conditions"]] == [given["text"]]


def test_an_unless_clause_stops_at_the_semicolon():
    entry = {"group": "Developers", "change": "May build near an airport.", "change_kind": "permission",
             "quote": "An airport-area development may proceed unless the application is denied by the airport; "
                      "the county shall record the decision.",
             "conditions": [], "exceptions": []}
    [item] = build_who_it_affects("HB 5", "Housing", ZONING, FakeClient({"items": [entry]})).items
    assert [c["quote"] for c in item["conditions"]] == ["unless the application is denied by the airport"]


def test_a_quote_with_no_condition_gets_none():
    [item] = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [_landlord()]})).items
    assert item["conditions"] == []


def test_dropped_conditions_and_exceptions_are_reported():
    invented = {"text": "Only in Miami.", "quote": "This applies only in Miami-Dade County."}
    r = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [_landlord(conditions=[invented])]}))
    assert {"dropped": "condition", "group": "Landlords", **invented} in r.dropped


def test_a_quote_that_opens_with_if_is_not_repeated_as_its_own_condition():
    bill = "Section 1. If the tenant vacates early, the landlord may keep one month of rent.\n"
    entry = {"group": "Landlords", "change": "May keep one month of rent if the tenant leaves early.",
             "change_kind": "permission", "quote": "If the tenant vacates early, the landlord may keep one month of rent.",
             "conditions": [], "exceptions": []}
    [item] = build_who_it_affects("HB 6", "Leases", bill, FakeClient({"items": [entry]})).items
    assert item["conditions"] == []


def test_entries_cite_the_statute_they_amend():
    from pathlib import Path

    text = (Path(__file__).parent / "fixtures" / "bill_text" / "hb1389_2026_enrolled.txt").read_text()
    setbacks = ("A municipality may not restrict height below the height authorized under this paragraph through "
                "other dimensional means, such as establishing setbacks or stepbacks by height, or require setbacks "
                "or stepbacks that are more restrictive than the minimum permitted in the proposed development.")
    entry = {"group": "Municipalities", "change": "May not use setbacks to cut the allowed height.",
             "change_kind": "prohibition", "quote": setbacks, "conditions": [], "exceptions": []}
    client = SequenceClient({"items": []}, {"items": [entry]}, {"items": []})
    [item] = build_who_it_affects("H1389", "Affordable Housing", text, client).items
    assert (item["section_ref"], item["statute_ref"]) == ("Section 2", "s. 166.04151(7)(d)1.")


# R4 (HB 1389 validation): neither entry listed the (7)(o) exclusions or the
# s. 333.03(5) airport carve-out, which govern every rule in (7).
def _hb1389_text():
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "bill_text" / "hb1389_2026_enrolled.txt").read_text()


COUNTY_MANDATE = "A county must authorize multifamily and mixed-use residential as allowable uses in any area zoned for commercial, industrial, or mixed use;"


def test_exclusions_reach_the_entries_they_govern():
    entry = {"group": "Counties", "change": "Must allow multifamily housing in commercial areas.",
             "change_kind": "obligation", "quote": COUNTY_MANDATE, "conditions": [], "exceptions": []}
    client = SequenceClient({"items": [entry]})
    [item] = build_who_it_affects("H1389", "Affordable Housing", _hb1389_text(), client).items
    quotes = [" ".join(x["quote"].split()) for x in item["exceptions"]]
    assert len(quotes) == 2
    subsection, airports = quotes
    assert subsection.startswith("This subsection does not apply to:")
    assert "The Wekiva Study Area" in subsection and "recorded conservation easement" in subsection
    assert "Section 2." not in subsection  # stops at the end of the list
    assert airports.startswith("Sections 125.01055(7) and 166.04151(7) do not apply to any of the following, unless")
    assert "maximum height restrictions" in airports


def test_an_exclusion_for_another_statute_is_not_attached():
    discrimination = "It is unlawful to discriminate in land use decisions or in the permitting of development"
    entry = {"group": "Local governments", "change": "May not discriminate in land use decisions.",
             "change_kind": "prohibition", "quote": discrimination, "conditions": [], "exceptions": []}
    client = SequenceClient({"items": []}, {"items": []}, {"items": [entry]})
    [item] = build_who_it_affects("H1389", "Affordable Housing", _hb1389_text(), client).items
    assert item["exceptions"] == []


def test_an_exclusion_the_model_listed_is_not_repeated():
    [item] = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [_landlord()]})).items
    assert [x["quote"] for x in item["exceptions"]] == [
        "This section does not apply to a landlord who owns fewer than three dwelling units.",
    ]


def test_an_exclusion_the_model_missed_is_added():
    [item] = build_who_it_affects("HB 1", "Deposits", BILL, FakeClient({"items": [_landlord(exceptions=[])]})).items
    assert [x["quote"] for x in item["exceptions"]] == [
        "This section does not apply to a landlord who owns fewer than three dwelling units.",
    ]


def test_an_entry_on_unchanged_law_is_labeled():
    # HB 1389's (7)(d)2 height cap near single-family homes is existing law.
    cap = ("the county may restrict the height of the proposed development to 150 percent of the tallest building "
           "on any property adjacent to the proposed development")
    entry = {"group": "Counties", "change": "May cap height near single-family neighborhoods.",
             "change_kind": "permission", "quote": cap, "conditions": [], "exceptions": []}
    setbacks = ("A county may not restrict height below the height authorized under this paragraph through other "
                "dimensional means, such as establishing setbacks or stepbacks by height")
    new = {"group": "Counties", "change": "May not use setbacks to cut the allowed height.",
           "change_kind": "prohibition", "quote": setbacks, "conditions": [], "exceptions": []}
    client = SequenceClient({"items": [entry, new]})
    items = build_who_it_affects("H1389", "Affordable Housing", _hb1389_text(), client).items
    assert [i["restates_existing_law"] for i in items] == [True, False]


# R9 (HB 1389 validation): ss. 125.x (counties) and 166.x (municipalities)
# repeat the same rule; two entries per rule spent the cap twice, and the
# cap hid every group past the sixth.
def _parallel(local: str, section_hint: str) -> dict:
    quote = (f"A {local} may not restrict height below the height authorized under this paragraph through other "
             "dimensional means, such as establishing setbacks or stepbacks by height")
    group = "Counties" if local == "county" else "Municipalities"
    return {"group": group, "change": "May not use setbacks to cut the allowed height.",
            "change_kind": "prohibition", "quote": quote, "conditions": [], "exceptions": []}


def test_parallel_county_and_municipal_entries_merge():
    client = SequenceClient({"items": [_parallel("county", "1")]}, {"items": [_parallel("municipality", "2")]})
    [item] = build_who_it_affects("H1389", "Affordable Housing", _hb1389_text(), client).items
    assert item["group"] == "Counties and municipalities"
    assert item["affected_groups"] == ["Counties", "Municipalities"]
    assert (item["section_ref"], item["statute_ref"]) == ("Section 1", "s. 125.01055(7)(d)1.")
    [also] = item["also_in"]
    assert (also["section_ref"], also["statute_ref"]) == ("Section 2", "s. 166.04151(7)(d)1.")
    assert also["quote"].startswith("A municipality may not restrict height")
    # The (7)(o) lists read the same in both statutes: listed once.
    subsection = [x for x in item["exceptions"] if x["quote"].startswith("This subsection does not apply to")]
    assert len(subsection) == 1


def test_rules_that_differ_beyond_the_local_government_stay_separate():
    county = ("Notwithstanding any other law, local ordinance, or regulation to the contrary, a county may not "
              "require a proposed multifamily development to obtain a zoning or land use change")
    city = ("Notwithstanding any other law, local ordinance, or regulation to the contrary, a municipality may not "
            "require a proposed multifamily development to obtain a zoning or land use change, special exception")
    a = {"group": "Counties", "change": "May not require rezoning.", "change_kind": "prohibition",
         "quote": county, "conditions": [], "exceptions": []}
    b = {"group": "Municipalities", "change": "May not require rezoning.", "change_kind": "prohibition",
         "quote": city, "conditions": [], "exceptions": []}
    client = SequenceClient({"items": [a]}, {"items": [b]})
    items = build_who_it_affects("H1389", "Affordable Housing", _hb1389_text(), client).items
    assert [i["group"] for i in items] == ["Counties", "Municipalities"]


def test_up_to_twelve_entries_are_kept_and_more_are_counted():
    lines = "".join(f"({i}) Agency {i} shall file report number {i} with the clerk.\n" for i in range(1, 15))
    bill = "Section 1. Reports.\n" + lines
    items = [_entry(f"Agency {i}", f"Agency {i} shall file report number {i} with the clerk.") for i in range(1, 15)]
    r = build_who_it_affects("HB 7", "Reports", bill, FakeClient({"items": items}))
    assert len(r.items) == 12
    assert r.scope_note == "Bill text · first 12 of 14 entries"


class QuoteRoutingClient:
    """Answers each window with the entries whose quote that window contains."""
    model = "fake:1"

    def __init__(self, *entries):
        self.entries = entries
        self.prompts = []

    def generate(self, prompt, *, json_mode=False):
        self.prompts.append(prompt)
        flat = " ".join(prompt.split())
        return json.dumps({"items": [e for e in self.entries if " ".join(e["quote"].split()) in flat]})


def test_provision_dates_reach_the_entries_they_govern():
    assemblage = ("A multifamily or mixed-use residential development proposed under this section shall not exclude "
                  "an assemblage of parcels under common ownership or control")
    a = {"group": "Developers", "change": "Must be allowed to include nearby parcels under common ownership.",
         "change_kind": "eligibility", "quote": assemblage, "conditions": [], "exceptions": []}
    notice = "may notify the county or municipality by July 1, 2026, of its intent to proceed"
    b = {"group": "Pending applicants", "change": "May choose to proceed under the old rules.",
         "change_kind": "permission", "quote": notice, "conditions": [], "exceptions": []}
    client = QuoteRoutingClient(a, b)
    items = {i["group"]: i for i in build_who_it_affects("H1389", "Affordable Housing", _hb1389_text(), client).items}
    assert {"text": "Expires July 1, 2030", "quote": "This subparagraph expires July 1, 2030."} in items["Developers"]["conditions"]
    # The deadline is in the entry's own quote: not repeated as a condition.
    assert items["Pending applicants"]["conditions"] == []
