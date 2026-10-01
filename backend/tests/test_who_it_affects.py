import json

from app.pipeline.bill_layers import METHOD_VERSIONS, WHO_IT_AFFECTS_PROMPT, build_who_it_affects

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
    assert item["exceptions"] == []


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
    assert METHOD_VERSIONS[("who_it_affects", "sunshine_ledger_ai")] == "who_it_affects/sunshine_ledger_ai/1"


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
