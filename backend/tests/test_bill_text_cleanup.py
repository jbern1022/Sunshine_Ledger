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
