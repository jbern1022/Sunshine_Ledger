from app.pipeline.bill_layers_text import (
    bill_section_numbers,
    extract_effect_section,
    extract_fiscal_section,
    is_conditional,
    law_as_amended,
    normalize_ws,
    section_for_quote,
    section_number,
    states_no_or_unknown_impact,
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


def test_states_no_or_unknown_impact():
    assert states_no_or_unknown_impact("Staff found the private sector impact indeterminate.")
    assert states_no_or_unknown_impact("Staff found no fiscal impact on state government.")
    assert not states_no_or_unknown_impact("Counties save money.")


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
