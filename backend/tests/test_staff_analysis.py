"""Tests for FL staff-analysis PDF cleaning and supplement filtering.

Both are pure functions, so these run without LegiScan, a PDF, or a
database. `clean_analysis_text`'s fixtures mirror the real layout confirmed
2026-09-21 against a live FL House analysis (HB 11, "Designation of the
State Birds") -- keep them shaped that way.
"""

from app.pipeline.staff_analysis import clean_analysis_text, is_staff_analysis


def test_strips_repeating_nav_footer():
    raw = "\n".join(
        [
            "EFFECT OF THE BILL:",
            "The bill designates the American flamingo as the official state bird.",
            "JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION BILL HISTORY",
            "RELEVANT INFORMATION",
        ]
    )
    assert clean_analysis_text(raw) == "\n".join(
        [
            "EFFECT OF THE BILL:",
            "The bill designates the American flamingo as the official state bird.",
            "RELEVANT INFORMATION",
        ]
    )


def test_strips_bare_page_number_lines():
    raw = "\n".join(["first page content", " 2 ", "second page content"])
    assert clean_analysis_text(raw) == "first page content\nsecond page content"


def test_keeps_footnote_markers_and_citations():
    """Footnotes are real content (citations a reader may want), unlike a
    filed bill's trailing line numbers -- must not be stripped."""
    raw = "protected under the Federal Migratory Bird Treaty Act.8"
    assert clean_analysis_text(raw) == raw


def test_keeps_numbered_list_style_content():
    """A line that happens to be a bare number mid-sentence context (not a
    page marker) is rare in practice, but ordinary section numbers embedded
    in real sentences must survive -- only a *fully* bare line is dropped."""
    raw = "\n".join(["(Sections 1 and 2)", "The effective date of the bill is July 1, 2026."])
    assert clean_analysis_text(raw) == raw


def test_drops_blank_and_whitespace_only_lines():
    raw = "first line\n\n   \nsecond line\n"
    assert clean_analysis_text(raw) == "first line\nsecond line"


def test_empty_input():
    assert clean_analysis_text("") == ""


def test_text_with_no_furniture_is_unchanged():
    raw = "This bill analysis was prepared by nonpartisan committee staff."
    assert clean_analysis_text(raw) == raw


# --- supplement filtering --------------------------------------------------


def test_is_staff_analysis_true_for_analysis_title():
    """LegiScan's type/type_id are uniformly ("Veto Letter", 8) on every
    real FL analysis observed 2026-09-21 -- title is the only reliable
    signal, confirmed by sampling 25 live bills, so a real analysis must
    still match even with that misleading type."""
    assert is_staff_analysis({"title": "Analysis", "type": "Veto Letter", "type_id": 8})


def test_is_staff_analysis_false_for_other_titles():
    assert not is_staff_analysis({"title": "Fiscal Note"})
    assert not is_staff_analysis({"title": None})
    assert not is_staff_analysis({})
