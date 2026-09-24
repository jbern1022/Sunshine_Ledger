"""Tests for inline change-marker extraction (`[deleted: ...]` / `[added:
...]`) from real bill documents, plus the `clean_legislative_text` fixes
that ride along with it.

HTML fixture: `s0564_c1.html` (Florida CS/SB 564, committee substitute 1).
Known from the 2026-09-23 spike: the struck word is "No" (in "An No
agency"), and there are 17 `class="Insert"` spans. `<u class="Insert">An</u>`
sits immediately before the struck "No" in the markup, so it becomes its
own `[added: An]` marker rather than plain text -- see the concern in the
task report for detail.

PDF fixture: `h0565_enrolled.pdf` (Florida CS/CS/HB 565, enrolled). Known
from the spike: "managers and supervisors" is struck and "all employees" is
underlined in one sentence; "Tatton-Brown-Rahman syndrome" is underlined
(added) elsewhere, together with the "or" immediately before it -- the
underline segment also grazes ~11% of the preceding "syndrome," at the
word's trailing edge, which the any-overlap rule (as specified) sweeps into
the same marker. The old pypdf path corrupted this same text to "Phelan-32
McDermid" by gluing the margin line number onto a hyphenated word.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.pipeline.bill_text import (
    clean_legislative_text,
    extract_html_text,
    extract_pdf_text,
    html_to_marked_text,
    mark_words,
)

FIXTURES = Path(__file__).parent / "fixtures" / "bill_text"


# --- HTML: Senate <s class="Remove"> / <u class="Insert"> ----------------


def test_html_fixture_marks_deletions_and_additions():
    html_bytes = (FIXTURES / "s0564_c1.html").read_bytes()
    text = extract_html_text(html_bytes)

    assert "[deleted: No] agency" in text
    assert "[added: " in text
    assert "<" not in text  # no raw tags leaked through


def test_html_to_marked_text_wraps_remove_and_insert():
    html = (
        '<pre>An <s class="Remove">No</s> agency or '
        '<u class="Insert">a</u> state official</pre>'
    )
    assert html_to_marked_text(html) == "An [deleted: No] agency or [added: a] state official"


def test_html_to_marked_text_collapses_whitespace_only_insert():
    """A span holding only a space (an inserted space) shouldn't produce an
    empty `[added: ]` marker."""
    html = '<pre>foo<u class="Insert"> </u>bar</pre>'
    assert html_to_marked_text(html) == "foobar" or html_to_marked_text(html) == "foo bar"


# --- PDF: pdfplumber word + rule geometry ---------------------------------


def test_pdf_fixture_marks_struck_and_underlined_text():
    pdf_bytes = (FIXTURES / "h0565_enrolled.pdf").read_bytes()
    text = extract_pdf_text(pdf_bytes)

    assert "[deleted: managers and supervisors]" in text
    assert "[added: all employees]" in text
    # The added run includes the "or" that immediately precedes the new
    # definition name -- see the module docstring above.
    assert re.search(r"\[added: [^\]]*Tatton-Brown-Rahman syndrome", text)

    assert "Phelan-32" not in text
    assert "CODING" not in text
    assert not any(re.fullmatch(r"\d+", line.strip()) for line in text.split("\n"))


# --- mark_words: pure geometry over synthetic words/segments -------------


def _word(text, x0, x1, top, bottom=None):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom or top + 10}


def _seg(x0, x1, top, bottom):
    return {"x0": x0, "x1": x1, "top": top, "bottom": bottom}


def test_mark_words_strike_through():
    words = [_word("old", 10, 30, 100)]
    # Segment across the word's vertical middle (mid = 105).
    segments = [_seg(10, 30, 104.5, 105.5)]
    assert mark_words(words, segments) == ["[deleted: old]"]


def test_mark_words_underline():
    words = [_word("new", 10, 30, 100)]
    # Segment just below the word's bottom (bottom = 110).
    segments = [_seg(10, 30, 111, 111.5)]
    assert mark_words(words, segments) == ["[added: new]"]


def test_mark_words_run_merging():
    words = [
        _word("all", 10, 25, 100),
        _word("employees", 30, 90, 100),
        _word("of", 95, 105, 100),
    ]
    segments = [_seg(10, 90, 111, 111.5)]  # underline under "all employees" only
    assert mark_words(words, segments) == ["[added: all employees] of"]


def test_mark_words_drops_left_margin_line_numbers():
    words = [
        _word("58", 40, 54, 100),  # numeric, x0 < margin_x -> dropped
        _word("content", 70, 120, 100),
    ]
    assert mark_words(words, []) == ["content"]


def test_mark_words_keeps_numeric_word_outside_margin():
    """A number that isn't in the left margin is content, not a line
    number -- e.g. a year or a statute subsection."""
    words = [_word("2026", 200, 230, 100)]
    assert mark_words(words, []) == ["2026"]


def test_mark_words_groups_by_top_within_tolerance():
    words = [
        _word("line", 10, 40, 100.0),
        _word("one", 45, 65, 101.5),  # within 2pt -- same line
        _word("line", 10, 40, 120.0),
        _word("two", 45, 65, 120.0),
    ]
    assert mark_words(words, []) == ["line one", "line two"]


# --- clean_legislative_text: hyphen-glued numbers and resync -------------


def test_hyphen_glued_line_number_is_stripped():
    raw = "\n".join(
        [
            "first line 1",
            "Down syndrome, Phelan-2",
            "McDermid syndrome 3",
        ]
    )
    assert clean_legislative_text(raw) == "\n".join(
        [
            "first line",
            "Down syndrome, Phelan-",
            "McDermid syndrome",
        ]
    )


def test_sequence_resyncs_when_next_number_is_a_few_ahead():
    """A line that legitimately has no trailing number (or lost it in
    extraction) shouldn't permanently desync the sequence -- the next
    number a small hop ahead is still accepted."""
    raw = "\n".join(
        [
            "first line 1",
            "second line without a number",
            "third line 4",
        ]
    )
    assert clean_legislative_text(raw) == "\n".join(
        [
            "first line",
            "second line without a number",
            "third line",
        ]
    )


def test_sequence_does_not_resync_across_a_large_gap():
    raw = "\n".join(["first line 1", "the fee shall not exceed 500"])
    assert clean_legislative_text(raw).split("\n")[1] == "the fee shall not exceed 500"
