"""Page furniture removed at extraction time and from already-stored text."""

from app.pipeline.bill_text import clean_legislative_text, clean_stored_text, clean_stored_texts
from app.pipeline.text_cleanup import strip_page_artifacts

# Jacksonville ordinance, two pages: numbering restarts at 1 on page 2,
# which clean_legislative_text's forward-only window can't follow.
LEGISTAR_TWO_PAGES = (
    "Section 1. Approval. The Council hereby approves the agreement 1\n"
    "attached hereto as Exhibit 1. 2\n"
    "Section 2. Oversight. The Downtown Investment Authority shall 3\n"
    "- 1 -\n"
    "oversee the Project described herein. 1\n"
    "Section 3. Effective Date. This Ordinance shall become 2\n"
    "effective upon signature by the Mayor. 3\n"
    "4\n"
    "Form Approved: 5\n"
)


def test_legistar_pypdf_cleanup_handles_page_number_restart():
    # The order _extract_pdf_text_pypdf uses.
    out = clean_legislative_text(strip_page_artifacts(LEGISTAR_TWO_PAGES))
    assert out == (
        "Section 1. Approval. The Council hereby approves the agreement\n"
        "attached hereto as Exhibit 1.\n"
        "Section 2. Oversight. The Downtown Investment Authority shall\n"
        "oversee the Project described herein.\n"
        "Section 3. Effective Date. This Ordinance shall become\n"
        "effective upon signature by the Mayor.\n"
        "Form Approved:"
    )


# Raw pypdf text of Ordinance 2026-619 (lines 0-27): "Introduced" split in
# two, whitespace-only lines between numbered lines, and numbers glued to
# the text ("AN16", "-212", "DATE.18").
LEGISTAR_GLUED_NUMBERS = (
    "Int\n"
    "roduced by the Land Use and Zoning Committee: 1 \n"
    "2\n"
    " \n"
    "3\n"
    " \n"
    "ORDINANCE 2026-619 4 \n"
    "BAKER, FROM COMMERCIAL COMMUNITY/GENERAL-1 (CCG-5 \n"
    "ISTRICT TO  COMMERCIAL COMMUNITY/GENERAL -26 \n"
    "(CCG-2) DISTRICT, AS DEFINED AND CLASSIFIED UNDER7 \n"
    "THE ZONING CODE, PURSUANT TO APPLICATION NUMBER8\n"
    " \n"
    "GRANTED HEREIN SHALL NOT BE CONSTRUED AS AN9 \n"
    "EXEMPTION FROM ANY OTHER APPLICABLE LAW S;10\n"
    " \n"
    "PROVIDING AN EFFECTIVE DATE.11 \n"
    "12\n"
    " \n"
    "WHEREAS, the Planning and Development Department has considered 13 \n"
    "the 2045 Comprehensive Plan 14\n"
)


def test_legistar_pypdf_cleanup_handles_blank_lines_and_glued_numbers():
    out = clean_legislative_text(strip_page_artifacts(LEGISTAR_GLUED_NUMBERS))
    assert out == (
        "Introduced by the Land Use and Zoning Committee:\n"
        "ORDINANCE 2026-619\n"
        "BAKER, FROM COMMERCIAL COMMUNITY/GENERAL-1 (CCG-\n"
        "ISTRICT TO  COMMERCIAL COMMUNITY/GENERAL -2\n"
        "(CCG-2) DISTRICT, AS DEFINED AND CLASSIFIED UNDER\n"
        "THE ZONING CODE, PURSUANT TO APPLICATION NUMBER\n"
        "GRANTED HEREIN SHALL NOT BE CONSTRUED AS AN\n"
        "EXEMPTION FROM ANY OTHER APPLICABLE LAW S;\n"
        "PROVIDING AN EFFECTIVE DATE.\n"
        "WHEREAS, the Planning and Development Department has considered\n"
        "the 2045 Comprehensive Plan"
    )


def test_glued_number_only_counts_inside_a_run():
    # Text that merely ends in digits, outside any numbered run, stays.
    text = "Section 5. The fee shall be $25\nunder Schedule A-4\nand ORDINANCE12"
    assert strip_page_artifacts(text) == text
    assert strip_page_artifacts("Int\nerest accrues") == "Int\nerest accrues"


def test_clean_stored_text_drops_page_header_between_added_blocks():
    stored = (
        "Section 3. [added: (1)(a) The agency shall contract with a state university. "
        "b. Attributes and behaviors that define high-quality support coordination.]\n"
        "hb565 -02-er\n"
        "ENROLLED\n"
        "CS/CS/HB 565 2026 Legislature\n"
        "[added: c. Best practices and areas for improvement.]\n"
        "Section 4. This act shall take effect July 1, 2026."
    )
    assert clean_stored_text(stored) == (
        "Section 3. [added: (1)(a) The agency shall contract with a state university. "
        "b. Attributes and behaviors that define high-quality support coordination.]\n"
        "[added: c. Best practices and areas for improvement.]\n"
        "Section 4. This act shall take effect July 1, 2026."
    )


def test_clean_stored_text_is_idempotent_and_leaves_clean_text_alone():
    clean = "Section 1. The fee is increased to 25\ndollars under subsection 2.\nSection 2. Effective July 1, 2027."
    assert clean_stored_text(clean) == clean
    once = clean_stored_text(LEGISTAR_TWO_PAGES)
    assert clean_stored_text(once) == once


def test_clean_stored_texts_dry_run_then_apply(db_session, bill_factory):
    dirty = bill_factory()
    dirty.bill.full_text = "Section 1. Text.\nhb495-01-c1\nMore text."
    clean = bill_factory()
    clean.bill.full_text = "Section 1. Already clean."
    db_session.commit()

    stats = clean_stored_texts(db_session, apply=False)
    assert stats["changed"] == 1 and stats["checked"] == 2
    db_session.refresh(dirty.bill)
    assert "hb495" in dirty.bill.full_text

    clean_stored_texts(db_session, apply=True)
    db_session.refresh(dirty.bill)
    assert dirty.bill.full_text == "Section 1. Text.\nMore text."
    assert clean_stored_texts(db_session, apply=False)["changed"] == 0


SENATE_AMENDMENT = (
    "Florida Senate - 2026                          SENATOR AMENDMENT\n"
    "Bill No. SB 7040\n"
    "Ì877368ZÎ877368\n"
    "LEGISLATIVE ACTION\n"
    "Senate             .             House\n"
    ".\n"
    ".\n"
    "Floor: 1/AD/RM         .            Floor: C\n"
    "03/13/2026 02:39 PM       .      03/13/2026 03:12 PM\n"
    "—————————————————————————————————————————————————————————————————\n"
    "Senator Hooper moved the following:\n"
    "Delete lines 6 - 65\n"
    "and insert:\n"
    "[added: within the Executive Office of the Governor.]"
)

HOUSE_AMENDMENT = (
    "COMMITTEE/SUBCOMMITTEE AMENDMENT\n"
    "Bill No. HB 657 (2026)\n"
    "Amendment No.\n"
    "[added: COMMITTEE/SUBCOMMITTEE ACTION]\n"
    "ADOPTED (Y/N)\n"
    "ADOPTED AS AMENDED (Y/N)\n"
    "ADOPTED W/O OBJECTION (Y/N)\n"
    "FAILED TO ADOPT (Y/N)\n"
    "WITHDRAWN (Y/N)\n"
    "OTHER\n"
    "Representative Porras offered the following:\n"
    "Between lines 53 and 54, insert:"
)


def test_strip_amendment_furniture_senate_cover_box():
    from app.pipeline.text_cleanup import strip_amendment_furniture

    assert strip_amendment_furniture(SENATE_AMENDMENT) == (
        "Florida Senate - 2026                          SENATOR AMENDMENT\n"
        "Bill No. SB 7040\n"
        "Floor: 1/AD/RM         .            Floor: C\n"
        "03/13/2026 02:39 PM       .      03/13/2026 03:12 PM\n"
        "Senator Hooper moved the following:\n"
        "Delete lines 6 - 65\n"
        "and insert:\n"
        "[added: within the Executive Office of the Governor.]"
    )


def test_strip_amendment_furniture_house_checkbox_form():
    from app.pipeline.text_cleanup import strip_amendment_furniture

    assert strip_amendment_furniture(HOUSE_AMENDMENT) == (
        "COMMITTEE/SUBCOMMITTEE AMENDMENT\n"
        "Bill No. HB 657 (2026)\n"
        "Amendment No.\n"
        "Representative Porras offered the following:\n"
        "Between lines 53 and 54, insert:"
    )


def test_strip_amendment_furniture_leaves_body_text_alone():
    from app.pipeline.text_cleanup import strip_amendment_furniture

    body = "Section 1. The fee is $25.\n(a) Other provisions apply.\nSenate Bill 12 is repealed."
    assert strip_amendment_furniture(body) == body
    assert strip_amendment_furniture(strip_amendment_furniture(SENATE_AMENDMENT)) == strip_amendment_furniture(
        SENATE_AMENDMENT
    )
