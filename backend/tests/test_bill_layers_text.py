from app.pipeline.bill_layers_text import (
    bill_section_numbers,
    extract_effect_section,
    extract_fiscal_section,
    is_conditional,
    is_substantive_finding,
    law_as_amended,
    normalize_ws,
    restates_bill,
    section_for_quote,
    section_number,
    verify_quotes,
)

SENATE = """BILL ANALYSIS AND FISCAL IMPACT STATEMENT
I. Summary:
Short summary.
II. Present Situation:
Current law says X.
III. Effect of Proposed Changes:
Section 1 amends s. 17.11, F.S., to remove references to FLAIR.
Section 2 amends s. 110.113, F.S., by removing the direct deposit requirement.
IV. Constitutional Issues:
A. Municipality/County Mandates Restrictions:
None.
V. Fiscal Impact Statement:
A. Tax/Fee Issues:
None.
B. Private Sector Impact:
Indeterminate.
C. Government Sector Impact:
The department may incur costs to update systems.
VI. Technical Deficiencies:
None.
"""

HOUSE = """FLORIDA HOUSE OF REPRESENTATIVES
SUMMARY
Effect of the Bill:
Summary box effect.
Fiscal or Economic Impact:
Summary box fiscal.
JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION
ANALYSIS
EFFECT OF THE BILL:
The bill requires counties to publish notices online.
JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION
It also repeals s. 50.011, F.S.
FISCAL OR ECONOMIC IMPACT:
STATE GOVERNMENT:
None.
LOCAL GOVERNMENT:
Counties may save publication costs.
PRIVATE SECTOR:
Newspapers may lose notice revenue.
RELEVANT INFORMATION
SUBJECT OVERVIEW:
Background.
"""

HOUSE_SUMMARY_ONLY = """FLORIDA HOUSE OF REPRESENTATIVES
SUMMARY
Effect of the Bill:
Summary box effect.
Fiscal or Economic Impact:
The bill has no fiscal impact on state or local government.
JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION
ANALYSIS
EFFECT OF THE BILL:
Body effect.
RELEVANT INFORMATION
"""

BILL = """Section 1. Subsection (2) of section 110.113, Florida Statutes, is amended to read:
110.113 Pay periods.
(2) Salary payments may be made by direct deposit.
Section 2. This act shall take effect July 1, 2027.
"""


def test_normalize_ws_collapses_runs():
    assert normalize_ws("  a \n\t b  ") == "a b"


def test_verify_quotes_keeps_exact_and_whitespace_variants():
    kept, dropped = verify_quotes(
        [
            {"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."},
            {"section_ref": "Section 1", "quote": "(2) Salary payments   may be made\nby direct deposit."},
        ],
        BILL,
    )
    assert len(kept) == 2 and dropped == []


def test_verify_quotes_drops_paraphrase_and_invention():
    kept, dropped = verify_quotes(
        [
            {"section_ref": "Section 2", "quote": "The act takes effect on July 1, 2027."},
            {"section_ref": "Section 9", "quote": "Employers must pay a $500 fee."},
            {"section_ref": "Section 1", "quote": ""},
        ],
        BILL,
    )
    assert kept == [] and len(dropped) == 3


def test_verify_quotes_drops_definitions_lead_in_and_short_fragments():
    text = (
        "Section 1. 393.063 Definitions.—For the purposes of this chapter, the term:\n"
        "(1) \"Agency\" means the Agency for Persons with Disabilities.\n"
        "Section 2. This act shall take effect July 1, 2027.\n"
    )
    kept, dropped = verify_quotes(
        [
            {"section_ref": "Section 1",
             "quote": "393.063 Definitions.—For the purposes of this chapter, the term:"},
            {"section_ref": "Section 1", "quote": "Short bit here:"},
            {"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."},
        ],
        text,
    )
    assert [c["quote"] for c in kept] == ["This act shall take effect July 1, 2027."]
    assert len(dropped) == 2


def test_verify_quotes_drops_definitions_lead_in_even_without_trailing_colon():
    # A Definitions.— lead-in never states a provision on its own, even if
    # the model happens to quote it without the trailing colon.
    text = (
        "Section 1. 393.063 Definitions.—For the purposes of this chapter, "
        "the term means something specific.\n"
        "Section 2. This act shall take effect July 1, 2027.\n"
    )
    kept, dropped = verify_quotes(
        [{"section_ref": "Section 1",
          "quote": "393.063 Definitions.—For the purposes of this chapter, the term"}],
        text,
    )
    assert kept == [] and len(dropped) == 1


def test_bill_section_numbers():
    assert bill_section_numbers(BILL) == {"1", "2"}


def test_section_number_parses_common_forms():
    assert section_number("Section 3") == "3"
    assert section_number("Sec. 12") == "12"
    assert section_number("section 4, subsection (2)") == "4"
    assert section_number("the whole bill") is None
    assert section_number(None) is None


def test_section_number_rejects_statute_citations():
    assert section_number("Section 110.113, F.S.") is None
    assert section_number("s. 20.19") is None


def test_is_conditional():
    assert is_conditional("Employers may need to update payroll.")
    assert is_conditional("Counties are expected to save money.")
    assert not is_conditional("Employers will need to update payroll.")
    assert not is_conditional("The bill removes the requirement.")


def test_is_conditional_excludes_month_may_with_day():
    assert not is_conditional("Beginning May 1, 2027, employers will be required to file reports.")
    assert is_conditional("Employers may need to update payroll.")


def test_bill_section_case_insensitive():
    assert bill_section_numbers("SECTION 1. Something.\nsection 2. Something else.\n") == {"1", "2"}


def test_section_for_quote_uses_last_heading_before_quote():
    text = (
        "Section 1. Subsection (2) of section 110.113, Florida Statutes, is amended to read:\n"
        "(2) Salary payments may be made by direct deposit.\n"
        "Section 2. This act shall take effect July 1, 2027.\n"
    )
    assert section_for_quote("Salary payments may be made by direct deposit.", text) == "Section 1"
    assert section_for_quote("This act shall take effect July 1, 2027.", text) == "Section 2"


def test_section_for_quote_returns_none_before_any_heading_or_when_not_found():
    text = "Preamble text.\nSection 1. Body text here.\n"
    assert section_for_quote("Preamble text.", text) is None
    assert section_for_quote("Nowhere in the text.", text) is None


def test_is_substantive_finding_keeps_real_statements():
    assert is_substantive_finding(
        "The bill will have a significant, negative fiscal impact to residential "
        "facilities and adult day training programs who must conduct level 2 "
        "background screenings on all employees."
    )
    assert is_substantive_finding("Staff found no private sector impact.")
    assert is_substantive_finding("Staff found the private sector impact indeterminate.")


def test_is_substantive_finding_drops_bare_tokens():
    assert not is_substantive_finding("None")
    assert not is_substantive_finding("None.")
    assert not is_substantive_finding("N/A")
    assert not is_substantive_finding("Indeterminate.")
    assert not is_substantive_finding("")
    assert not is_substantive_finding(None)


def test_extract_senate_effect_section():
    section = extract_effect_section(SENATE)
    assert section.startswith("Section 1 amends s. 17.11")
    assert "Constitutional Issues" not in section


def test_extract_house_effect_section_uses_body_and_strips_navigation():
    section = extract_effect_section(HOUSE)
    assert "requires counties to publish notices online" in section
    assert "repeals s. 50.011" in section
    assert "JUMP TO SUMMARY" not in section
    assert "Summary box effect" not in section


def test_extract_senate_fiscal_section():
    section = extract_fiscal_section(SENATE)
    assert "Indeterminate." in section
    assert "may incur costs" in section
    assert "Technical Deficiencies" not in section


def test_extract_house_fiscal_section():
    section = extract_fiscal_section(HOUSE)
    assert "LOCAL GOVERNMENT:" in section and "Newspapers may lose" in section
    assert "SUBJECT OVERVIEW" not in section


def test_extract_house_fiscal_falls_back_to_summary_box():
    assert extract_fiscal_section(HOUSE_SUMMARY_ONLY) == "The bill has no fiscal impact on state or local government."


def test_extract_returns_none_when_absent():
    assert extract_effect_section("Unrelated document text.") is None
    assert extract_fiscal_section("Unrelated document text.") is None


def test_law_as_amended_removes_deletion_and_collapses_space():
    assert law_as_amended("An [deleted: No] agency") == "An agency"


def test_law_as_amended_unwraps_addition():
    text = (
        "McDermid syndrome, [deleted: or] Prader-Willi syndrome, "
        "[added: or Tatton-Brown-Rahman syndrome;] that manifests"
    )
    assert law_as_amended(text) == (
        "McDermid syndrome, Prader-Willi syndrome, or Tatton-Brown-Rahman syndrome; that manifests"
    )


def test_law_as_amended_keeps_line_structure():
    text = "Section 1. Foo [deleted: bar] baz.\nSection 2. Qux.\n"
    assert law_as_amended(text) == "Section 1. Foo baz.\nSection 2. Qux.\n"


def test_law_as_amended_drops_unterminated_deleted_fragment():
    text = "Words before [deleted: cut off with no closing bracket"
    assert law_as_amended(text) == "Words before"


def test_law_as_amended_unwraps_unterminated_added_fragment():
    text = "Words before [added: cut off with no closing"
    assert law_as_amended(text) == "Words before cut off with no closing"


def test_bill_section_rejects_statute_citation_at_line_start():
    text = "Section 316.1895, F.S., requires signage.\nSection 2. Something else.\n"
    assert bill_section_numbers(text) == {"2"}


def test_is_conditional_excludes_bare_may_not():
    assert not is_conditional("The commission may not renew licenses after the deadline.")
    assert not is_conditional("The agency may not issue, renew, or approve licenses.")


def test_is_conditional_still_true_for_plain_may_and_other_cues():
    assert is_conditional("Employers may need to update payroll.")
    assert is_conditional("Counties are expected to save money.")


def test_is_conditional_true_when_may_not_accompanies_another_conditional_cue():
    assert is_conditional("Costs may not fall, but administrative burden is expected to rise.")


def test_is_conditional_treats_may_not_be_have_need_as_forecast():
    assert is_conditional("The agency may not be able to complete the review on time.")
    assert is_conditional("The agency may not have enough staff to process applications.")
    assert is_conditional("The department may not need additional funding.")


def test_is_conditional_still_excludes_may_not_prohibition_form():
    assert not is_conditional("The commission may not issue, renew, or approve licenses.")
    assert not is_conditional("The association may not adopt rules without notice.")


def test_law_as_amended_removes_space_stranded_before_punctuation_by_deletion():
    assert law_as_amended("the [deleted: agency], as defined by rule") == "the, as defined by rule"
    assert law_as_amended("Foo [deleted: X]. Bar") == "Foo. Bar"
    assert law_as_amended("Foo [deleted: X]; bar") == "Foo; bar"
    assert law_as_amended("Foo [deleted: X]: bar") == "Foo: bar"
    assert law_as_amended("Foo [deleted: X]) bar") == "Foo) bar"


def test_law_as_amended_does_not_touch_ordinary_spacing():
    text = "Foo , bar ; baz : qux ) end . Section 2. More text here , with commas."
    assert law_as_amended(text) == text


# --- restates_bill -----------------------------------------------------

EE_BILL = (
    "Section 1. The agency shall contract with a state university to provide research services.\n"
    "Section 2. The commission may not renew licenses after the deadline.\n"
    "Section 3. This act shall take effect July 1, 2027.\n"
)


def test_restates_bill_detects_provision_with_may_inserted():
    # The classic pattern from the quality report: the bill's own sentence,
    # copied with a "may" swapped in for "shall".
    assert restates_bill(
        "The agency may contract with a state university to provide research services.",
        EE_BILL,
    )


def test_restates_bill_detects_may_not_copied_verbatim():
    assert restates_bill("The commission may not renew licenses after the deadline.", EE_BILL)


def test_restates_bill_false_for_genuine_consequence():
    assert not restates_bill(
        "Universities may see increased demand for research staff as a result of the contract requirement.",
        EE_BILL,
    )


def test_restates_bill_false_for_short_statement_with_few_content_words():
    assert not restates_bill("Costs may rise.", EE_BILL)


def test_restates_bill_is_fast_on_a_long_bill():
    import time

    long_bill = EE_BILL + (
        "Section 4. Additional unrelated provisions establish reporting deadlines, "
        "funding formulas, and administrative procedures for various agencies. " * 150
    )
    assert len(long_bill) > 12_000
    start = time.monotonic()
    for _ in range(20):
        restates_bill(
            "Universities may see increased demand for research staff as a result of the contract requirement.",
            long_bill,
        )
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


def test_restates_bill_catches_h1171_paraphrase_default_autojunk_would_miss():
    # Real pair from the 2026-09-23 quality report. Both sentences are long
    # (> 200 chars), which is exactly where SequenceMatcher's default
    # autojunk=True heuristic collapses the ratio on ordinary English prose
    # and would let this restated provision through.
    bill_text = (
        "Section 1. 379.3671 Marine life; endangered and threatened species.\n"
        "(3) The commission may not issue, renew, or approve an "
        "education-exhibition special activity license or other authorization "
        "that would allow a person to collect or transport any endangered or "
        "threatened marine animal from state waters for purposes prohibited "
        "in subsection (2).\n"
        "Section 2. This act shall take effect July 1, 2027.\n"
    )
    model_statement = (
        "The Fish and Wildlife Conservation Commission may not issue, renew, "
        "or approve licenses that would allow the collection or "
        "transportation of endangered or threatened marine animals for "
        "educational or exhibition purposes."
    )
    assert restates_bill(model_statement, bill_text)


def test_restates_bill_skips_ratio_when_lengths_rule_out_a_match(monkeypatch):
    """ratio() can't exceed 2*min(len)/(len_a+len_b); a sentence far longer
    than the statement is skipped without the O(n*m) ratio() call, even
    when it shares plenty of content words."""
    import difflib

    calls = {"ratio": 0}
    real_ratio = difflib.SequenceMatcher.ratio

    def counting_ratio(self):
        calls["ratio"] += 1
        return real_ratio(self)

    monkeypatch.setattr(difflib.SequenceMatcher, "ratio", counting_ratio)
    long_sentence = (
        "Section 1. The agency shall contract with a state university to provide research "
        "services, together with laboratory space, staffing plans, annual budgets, reporting "
        "schedules, audit procedures, data-sharing agreements, and publication rules that the "
        "agency and the university jointly adopt and revise each fiscal year.\n"
    )
    assert not restates_bill("The agency may contract with a state university.", long_sentence)
    assert calls["ratio"] == 0


def test_restates_bill_skips_ratio_when_quick_ratio_is_too_low(monkeypatch):
    """quick_ratio() is a cheap upper bound on ratio(): when it is already
    below 0.6, ratio() is never computed."""
    import difflib

    calls = {"ratio": 0}
    real_ratio = difflib.SequenceMatcher.ratio

    def counting_ratio(self):
        calls["ratio"] += 1
        return real_ratio(self)

    monkeypatch.setattr(difflib.SequenceMatcher, "ratio", counting_ratio)
    bill = "Section 1. Agency university contract research xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.\n"
    # Same length ballpark and the same content words, but almost no shared
    # characters beyond them.
    stmt = "Agency university contract research zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz."
    assert not restates_bill(stmt, bill)
    assert calls["ratio"] == 0
