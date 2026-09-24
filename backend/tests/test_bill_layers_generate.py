import json

import pytest

from app.pipeline.bill_layers import (
    AI_EXPECTED_EFFECT_PROMPT,
    AI_INTERPRETATION_PROMPT,
    BILL_SAYS_PROMPT,
    LayerGenerationError,
    build_ai_expected_effect,
    build_ai_interpretation,
    build_bill_says,
    build_staff_expected_effect,
    build_staff_interpretation,
)

BILL = """Section 1. Subsection (2) of section 110.113, Florida Statutes, is amended to read:
(2) Salary payments may be made by direct deposit.
Section 2. This act shall take effect July 1, 2027.
"""

BILL_MARKED = """Section 1. Subsection (2) of section 110.113, Florida Statutes, is amended to read:
(2) Salary payments [deleted: may not] [added: may] be made by direct deposit.
Section 2. This act shall take effect July 1, 2027.
"""

EE_BILL = (
    "Section 1. The agency shall contract with a state university to provide research services.\n"
    "Section 2. The commission may not renew licenses after the deadline.\n"
    "Section 3. This act shall take effect July 1, 2027.\n"
)


class FakeClient:
    model = "fake:1"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, prompt, *, json_mode=False):
        assert json_mode, "layer prompts must request JSON"
        self.prompts.append(prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def test_bill_says_keeps_only_verified_quotes():
    client = FakeClient({"items": [
        {"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."},
        {"section_ref": "Section 1", "quote": "Employers must pay a fee."},
    ]})
    r = build_bill_says("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "supported"
    assert [i["quote"] for i in r.items] == ["This act shall take effect July 1, 2027."]
    assert r.items[0]["text"] == r.items[0]["quote"]
    assert len(r.dropped) == 1
    assert r.scope_note == "Bill text"


def test_bill_says_with_no_verified_quotes_is_insufficient():
    client = FakeClient({"items": [{"section_ref": "Section 1", "quote": "Invented."}]})
    r = build_bill_says("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.items == []
    assert r.scope_note == "Quotes could not be verified against the bill text"


def test_bill_says_with_no_verified_quotes_notes_truncation():
    long_text = BILL + ("x" * 20_000)
    client = FakeClient({"items": [{"section_ref": "Section 1", "quote": "Invented."}]})
    r = build_bill_says("HB 1", "Pay", long_text, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "Quotes could not be verified against the bill text in the first part of a long bill"


def test_bill_says_notes_truncation():
    long_text = BILL + ("x" * 20_000)
    client = FakeClient({"items": [{"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."}]})
    r = build_bill_says("HB 1", "Pay", long_text, client)
    assert r.scope_note == "Drawn from the first part of a long bill"


def test_bill_says_corrects_wrong_model_section_ref_from_text():
    client = FakeClient({"items": [
        {"section_ref": "Section 99", "quote": "This act shall take effect July 1, 2027."},
    ]})
    r = build_bill_says("HB 1", "Pay", BILL, client)
    assert r.items[0]["section_ref"] == "Section 2"


def test_ai_interpretation_normalizes_items():
    client = FakeClient({"items": [
        {"text": "Removes the direct deposit requirement.", "section_ref": "Section 1",
         "assumptions": [], "affected_groups": ["State employees"]},
    ]})
    r = build_ai_interpretation("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "supported"
    assert r.items == [{
        "text": "Removes the direct deposit requirement.", "section_ref": "Section 1", "quote": None,
        "assumptions": ["None identified"], "affected_groups": ["State employees"],
    }]


def test_ai_expected_effect_drops_uncited_and_unconditional():
    client = FakeClient({"items": [
        {"text": "State employees may be paid by paper check.", "section_ref": "Section 1", "assumptions": ["Agencies offer checks"]},
        {"text": "State employees will be paid by paper check.", "section_ref": "Section 1", "assumptions": []},
        {"text": "Banks may lose deposits.", "section_ref": "Section 7", "assumptions": []},
        {"text": "Payroll may change.", "section_ref": None, "assumptions": []},
    ]})
    r = build_ai_expected_effect("HB 1", "Pay", BILL, client)
    assert [i["text"] for i in r.items] == ["State employees may be paid by paper check."]
    assert len(r.dropped) == 3


def test_ai_expected_effect_all_dropped_is_insufficient():
    client = FakeClient({"items": [{"text": "Payroll will change.", "section_ref": "Section 1"}]})
    r = build_ai_expected_effect("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "No effects traceable to a specific bill section"


def test_ai_expected_effect_all_dropped_notes_truncation():
    long_text = BILL + ("x" * 20_000)
    client = FakeClient({"items": [{"text": "Payroll will change.", "section_ref": "Section 1"}]})
    r = build_ai_expected_effect("HB 1", "Pay", long_text, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "No effects traceable to a specific bill section in the first part of a long bill"


def test_staff_interpretation_without_section_is_insufficient_and_skips_model():
    client = FakeClient({"items": []})
    r = build_staff_interpretation(None, "Staff analysis, Rules Committee, 2026-03-01", client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "Staff analysis, Rules Committee, 2026-03-01 has no Effect of Proposed Changes section"
    assert client.prompts == []


def test_staff_interpretation_uses_scope_label():
    client = FakeClient({"items": [{"text": "Section 1 removes FLAIR references.", "section_ref": "Section 1"}]})
    r = build_staff_interpretation("Section 1 amends s. 17.11 ...", "Staff analysis, Rules Committee, 2026-03-01", client)
    assert r.evidence_state == "supported"
    assert r.scope_note == "Staff analysis, Rules Committee, 2026-03-01"


def test_staff_expected_effect_keeps_literal_none_and_conditional():
    client = FakeClient({"items": [
        {"text": "Staff found the private sector impact indeterminate.", "section_ref": None},
        {"text": "The department may incur costs to update systems.", "section_ref": None},
        {"text": "The department will save $2 million.", "section_ref": None},
    ]})
    r = build_staff_expected_effect("A. Tax/Fee Issues: None ...", "Staff analysis, Rules Committee, 2026-03-01", client)
    assert [i["text"] for i in r.items] == [
        "Staff found the private sector impact indeterminate.",
        "The department may incur costs to update systems.",
    ]


def test_staff_expected_effect_without_fiscal_section_is_insufficient():
    r = build_staff_expected_effect(None, "Staff analysis, Rules Committee, 2026-03-01", FakeClient({"items": []}))
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "Staff analysis, Rules Committee, 2026-03-01 has no fiscal impact section"


def test_unparseable_model_output_raises():
    with pytest.raises(LayerGenerationError):
        build_ai_interpretation("HB 1", "Pay", BILL, FakeClient("not json"))


def test_bill_says_drops_duplicate_quotes():
    client = FakeClient({"items": [
        {"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."},
        {"section_ref": "Section 2", "quote": "This act shall take effect   July 1, 2027."},
    ]})
    r = build_bill_says("HB 1", "Pay", BILL, client)
    assert [i["quote"] for i in r.items] == ["This act shall take effect July 1, 2027."]
    assert len(r.dropped) == 1


def test_bill_says_verifies_against_law_as_amended_view():
    client = FakeClient({"items": [
        {"section_ref": "Section 1", "quote": "(2) Salary payments may be made by direct deposit."},
    ]})
    r = build_bill_says("HB 1", "Pay", BILL_MARKED, client)
    assert r.evidence_state == "supported"
    assert r.items[0]["quote"] == "(2) Salary payments may be made by direct deposit."
    assert r.items[0]["section_ref"] == "Section 1"
    # The model was shown the amended view, not the raw markers.
    assert "[deleted:" not in client.prompts[0]
    assert "[added:" not in client.prompts[0]


def test_bill_says_drops_quote_with_deleted_words():
    client = FakeClient({"items": [
        {"section_ref": "Section 1", "quote": "(2) Salary payments may not be made by direct deposit."},
    ]})
    r = build_bill_says("HB 1", "Pay", BILL_MARKED, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.items == []
    assert len(r.dropped) == 1


def test_bill_says_prompt_describes_law_as_amended():
    assert "law as it will read" in BILL_SAYS_PROMPT


def test_interpretation_and_expected_effect_prompts_explain_markers():
    marker_sentence = "In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds."
    assert marker_sentence in AI_INTERPRETATION_PROMPT
    assert marker_sentence in AI_EXPECTED_EFFECT_PROMPT


def test_ai_expected_effect_drops_bill_sentence_with_may_inserted():
    client = FakeClient({"items": [
        {"text": "The agency may contract with a state university to provide research services.",
         "section_ref": "Section 1", "assumptions": []},
    ]})
    r = build_ai_expected_effect("HB 1", "Research", EE_BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.items == []
    assert len(r.dropped) == 1


def test_ai_expected_effect_drops_may_not_copied_from_bill():
    client = FakeClient({"items": [
        {"text": "The commission may not renew licenses after the deadline.",
         "section_ref": "Section 2", "assumptions": []},
    ]})
    r = build_ai_expected_effect("HB 1", "Research", EE_BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.items == []
    assert len(r.dropped) == 1


def test_ai_expected_effect_keeps_genuine_consequence():
    client = FakeClient({"items": [
        {"text": "Universities may see increased demand for research staff as a result of the contract requirement.",
         "section_ref": "Section 1", "assumptions": ["The agency selects at least one university"]},
    ]})
    r = build_ai_expected_effect("HB 1", "Research", EE_BILL, client)
    assert r.evidence_state == "supported"
    assert [i["text"] for i in r.items] == [
        "Universities may see increased demand for research staff as a result of the contract requirement."
    ]


def test_ai_interpretation_clears_section_ref_not_present_in_bill():
    client = FakeClient({"items": [
        {"text": "Removes the direct deposit requirement.", "section_ref": "Section 99",
         "assumptions": [], "affected_groups": []},
    ]})
    r = build_ai_interpretation("HB 1", "Pay", BILL, client)
    assert r.items[0]["section_ref"] is None
    assert r.items[0]["text"] == "Removes the direct deposit requirement."


def test_ai_interpretation_clears_unparseable_section_ref():
    client = FakeClient({"items": [
        {"text": "Declares support for the program.", "section_ref": "WHEREAS, the program exists",
         "assumptions": [], "affected_groups": []},
    ]})
    r = build_ai_interpretation("HB 1", "Pay", BILL, client)
    assert r.items[0]["section_ref"] is None


def test_ai_interpretation_keeps_section_ref_that_resolves_with_subsection():
    client = FakeClient({"items": [
        {"text": "Removes the direct deposit requirement.", "section_ref": "Section 1(2)(a)",
         "assumptions": [], "affected_groups": []},
    ]})
    r = build_ai_interpretation("HB 1", "Pay", BILL, client)
    assert r.items[0]["section_ref"] == "Section 1(2)(a)"


def test_ai_interpretation_clears_section_ref_for_resolution_text_with_no_sections():
    resolution_text = (
        "WHEREAS, the Legislature finds that the program benefits residents; and\n"
        "WHEREAS, the program has operated successfully; NOW, THEREFORE,\n"
        "BE IT RESOLVED that the Legislature expresses its support.\n"
    )
    client = FakeClient({"items": [
        {"text": "Expresses legislative support for the program.", "section_ref": "WHEREAS",
         "assumptions": [], "affected_groups": []},
    ]})
    r = build_ai_interpretation("HR 1", "Support", resolution_text, client)
    assert r.items[0]["section_ref"] is None
    assert r.items[0]["text"] == "Expresses legislative support for the program."


def test_staff_expected_effect_dedupes_by_category_keeping_first():
    client = FakeClient({"items": [
        {"category": "tax_fee", "text": "Staff found the tax/fee impact none."},
        {"category": "tax_fee", "text": "Staff found the tax/fee impact indeterminate."},
        {"category": "tax_fee", "text": "Staff found the tax/fee impact insignificant."},
        {"category": "state_government", "text": "The department may incur costs to update systems."},
    ]})
    r = build_staff_expected_effect("A. Tax/Fee Issues: None / Indeterminate / Insignificant ...",
                                     "Staff analysis, Rules Committee, 2026-03-01", client)
    assert [i["text"] for i in r.items] == [
        "Staff found the tax/fee impact none.",
        "The department may incur costs to update systems.",
    ]
    assert len(r.dropped) == 2


def test_staff_expected_effect_does_not_dedupe_other_category():
    client = FakeClient({"items": [
        {"category": "other", "text": "Staff note the bill is expected to take effect July 1."},
        {"category": "other", "text": "Staff note the department may need new rulemaking authority."},
    ]})
    r = build_staff_expected_effect("Fiscal section text", "Staff analysis", client)
    assert len(r.items) == 2


def test_ai_expected_effect_section_guard_uses_law_as_amended():
    # "Section 316.1895, F.S." must not be read as a heading for section 316
    # under the amended view either.
    text = (
        "Section 316.1895, F.S., requires signage.\n"
        "Section 1. [deleted: Old] [added: New] rule applies.\n"
    )
    client = FakeClient({"items": [
        {"text": "Drivers may see new signage.", "section_ref": "Section 316", "assumptions": []},
        {"text": "The rule may change.", "section_ref": "Section 1", "assumptions": []},
    ]})
    r = build_ai_expected_effect("HB 1", "Pay", text, client)
    assert [i["text"] for i in r.items] == ["The rule may change."]
    assert len(r.dropped) == 1
