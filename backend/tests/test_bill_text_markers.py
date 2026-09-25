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
underlined in one sentence; the "or" immediately before the new syndrome
name is struck, and "or Tatton-Brown-Rahman syndrome;" is underlined
(added) right after it. A rule under the preceding word ("syndrome,")
grazes only ~11% of its width -- below the >=50% coverage threshold a word
needs to count as marked -- so that word stays plain. The old pypdf path
corrupted this same text to "Phelan-32 McDermid" by gluing the margin line
number onto a hyphenated word.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.pipeline.bill_layers_text import law_as_amended
from app.pipeline.bill_text import (
    clean_legislative_text,
    compare_texts,
    fetch_legistar_bill_text,
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
    assert html_to_marked_text(html) == "foo bar"


def test_html_to_marked_text_keeps_edge_whitespace_outside_the_marker():
    html = '<pre>the purpose of<u class="Insert"> receiving </u>hours</pre>'
    assert html_to_marked_text(html) == "the purpose of [added: receiving] hours"


def test_html_to_marked_text_merges_adjacent_same_kind_markers():
    html = (
        '<pre><u class="Insert">(b)</u><u class="Insert"> </u>'
        '<u class="Insert">High school</u> and '
        '<s class="Remove">old</s><s class="Remove">er</s></pre>'
    )
    assert html_to_marked_text(html) == "[added: (b) High school] and [deleted: older]"


def test_html_to_marked_text_merges_markers_across_a_newline():
    html = (
        '<pre>   1  <u class="Insert">workers for the purpose of</u>\n'
        '   2  <u class="Insert">receiving hours</u></pre>'
    )
    assert html_to_marked_text(html) == "[added: workers for the purpose of receiving hours]"


def test_html_to_marked_text_does_not_merge_into_a_section_heading():
    """An added block opening with "Section N." keeps its own line, so the
    heading is still at a line start in the law-as-amended view."""
    html = (
        '<pre>   1  <u class="Insert">end of section one.</u>\n'
        '   2  <u class="Insert">Section 2. New text.</u></pre>'
    )
    assert html_to_marked_text(html) == (
        "[added: end of section one.]\n[added: Section 2. New text.]"
    )


def test_html_fixture_law_as_amended_keeps_word_boundaries():
    """S0564 wraps "workers for the purpose of" and " receiving community
    service hours to" in separate Insert spans; the second span's leading
    space must survive as a word boundary."""
    text = extract_html_text((FIXTURES / "s0564_c1.html").read_bytes())
    amended = law_as_amended(text)
    assert "purpose of receiving" in amended
    assert "ofreceiving" not in amended
    assert "[added: (b) High school students" in text
    assert "workers for the purpose of receiving community service hours to" in text


# --- PDF: pdfplumber word + rule geometry ---------------------------------


def test_pdf_fixture_marks_struck_and_underlined_text():
    pdf_bytes = (FIXTURES / "h0565_enrolled.pdf").read_bytes()
    text = extract_pdf_text(pdf_bytes)

    assert "[deleted: managers and supervisors]" in text
    assert "[added: all employees]" in text
    # The "or" right before the new syndrome name is struck, and the new
    # name (with its own "or") is added immediately after -- see the
    # module docstring above.
    assert "[deleted: or] Prader-Willi syndrome, [added: or Tatton-Brown-Rahman syndrome;]" in text

    assert "Phelan-32" not in text
    assert "CODING" not in text
    assert not any(re.fullmatch(r"\d+", line.strip()) for line in text.split("\n"))


def test_pdf_fixture_output_unchanged_by_releasing_pages(monkeypatch):
    """extract_pdf_text closes each pdfplumber page once processed (memory:
    H5003 peaked at ~607 MB without it, ~107 MB with). Output must be the
    same as extracting with pages left open."""
    import pdfplumber.page

    pdf_bytes = (FIXTURES / "h0565_enrolled.pdf").read_bytes()
    closed = {"n": 0}
    real_close = pdfplumber.page.Page.close

    def counting_close(self):
        closed["n"] += 1
        return real_close(self)

    import app.pipeline.bill_text as bill_text

    real_mark_words = bill_text.mark_words
    closed_before_each_page: list[int] = []

    def recording_mark_words(words, segments, **kwargs):
        closed_before_each_page.append(closed["n"])
        return real_mark_words(words, segments, **kwargs)

    monkeypatch.setattr(pdfplumber.page.Page, "close", counting_close)
    monkeypatch.setattr(bill_text, "mark_words", recording_mark_words)
    with_close = extract_pdf_text(pdf_bytes)
    # Each page is released before the next one is processed -- not just
    # all at once when the document closes.
    assert closed_before_each_page == list(range(len(closed_before_each_page)))
    assert len(closed_before_each_page) > 1

    monkeypatch.setattr(pdfplumber.page.Page, "close", lambda self: None)
    without_close = extract_pdf_text(pdf_bytes)

    assert with_close == without_close
    assert "[deleted: managers and supervisors]" in with_close


def test_h1171_section_headings_start_their_lines():
    """H1171 (filed): the underlined short title sits a fraction of a point
    higher than the plain "Section 1." heading on the same line. Ordering
    that line by `top` put the heading last."""
    text = extract_pdf_text((FIXTURES / "h1171_filed.pdf").read_bytes())
    lines = text.split("\n")

    assert any(line.startswith("Section 1. [added: This act may be cited as") for line in lines)
    assert any(line.startswith("Section 4. This act shall take effect") for line in lines)
    assert "Marine At-Risk] Section 1." not in text
    headings = re.findall(r"(?m)^Section (\d+)\.(?!\d)", law_as_amended(text))
    assert headings == ["1", "2", "3", "4"]


def test_h1171_glued_renumbering_is_split_into_deleted_and_added():
    """H1171 renumbers a list by printing the new number (underlined) glued
    to the old one (struck): "2.1." is one pdfplumber word. Per-character
    classification splits it, so the law as amended reads "2." alone."""
    text = extract_pdf_text((FIXTURES / "h1171_filed.pdf").read_bytes())
    assert "[added: 3.][deleted: 2.] Section 379.365(2)(c)" in text
    assert "[added: 12.][deleted: 11.] Section 379.4115" in text

    amended = law_as_amended(text)
    assert "3. Section 379.365(2)(c)" in amended
    assert "12. Section 379.4115" in amended
    for glued in ("2.1.", "3.2.", "10.9.", "12.11."):
        assert glued not in amended


# --- Legistar (Jacksonville): pypdf path, no markers ----------------------


class _FakeResponse:
    def __init__(self, *, json_data=None, content=b""):
        self._json = json_data
        self.content = content

    def json(self):
        return self._json

    def raise_for_status(self):
        pass


class _FakeLegistarClient:
    def __init__(self, pdf_bytes):
        self._pdf = pdf_bytes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        if url.endswith("/Attachments"):
            return _FakeResponse(
                json_data=[
                    {"MatterAttachmentName": "Exhibit 1", "MatterAttachmentHyperlink": "https://x/ex1"},
                    {
                        "MatterAttachmentName": "2026-0800 - Original Bill",
                        "MatterAttachmentHyperlink": "https://x/bill.pdf",
                    },
                ]
            )
        assert url == "https://x/bill.pdf"
        return _FakeResponse(content=self._pdf)


def test_legistar_text_uses_pypdf_path_without_markers(monkeypatch):
    """Jacksonville ordinances break the marker extractor (shifted italic/bold
    boxes, underline read as strike, signature rules), so Legistar stays on
    the pypdf path. Before this, "shall not be construed" came back as
    [deleted: ...] and section headings were scrambled off line starts."""
    import httpx

    pdf_bytes = (FIXTURES / "jax_2026_ordinance_8800.pdf").read_bytes()
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _FakeLegistarClient(pdf_bytes))

    text = fetch_legistar_bill_text("jacksonvillefl", 8800)

    assert text
    assert "shall not be construed" in " ".join(text.split())
    assert "[deleted:" not in text
    assert "[added:" not in text
    headings = re.findall(r"(?m)^Section (\d+)\.", text)
    assert headings == ["1", "2", "3", "4", "5", "6"]


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


def test_mark_words_ignores_a_segment_that_only_grazes_a_word():
    """A rule meant for one word can overrun into a neighbor's edge by a
    point or two (rendering, not intent). Coverage below 50% of the word's
    width must not mark it."""
    words = [
        _word("kept", 10, 30, 100),  # width 20
        _word("marked", 35, 75, 100),  # width 40
    ]
    # Underline segment covers all of "marked" (35-75) plus 2pt into
    # "kept" (28-30) -- 2/20 = 10% of "kept"'s width, well under 50%.
    segments = [_seg(28, 75, 111, 111.5)]
    assert mark_words(words, segments) == ["kept [added: marked]"]


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


def test_digit_hyphen_citation_is_not_treated_as_a_glued_line_number():
    """A hyphen only counts as the "Phelan-32" separator when it follows a
    letter. "2026-3" and "316-2" are real statutory citations whose
    trailing digits happen to fall inside the 1-3 resync window -- they
    must survive intact, not get read as a line number and stripped."""
    raw = "\n".join(
        [
            "first line 1",  # sets expected = 1
            "as provided by chapter 2026-3",  # 3 - 1 = 2: inside the window
        ]
    )
    assert clean_legislative_text(raw) == "\n".join(
        ["first line", "as provided by chapter 2026-3"]
    )

    raw2 = "\n".join(
        [
            "first line 1",  # sets expected = 1
            "the exemption under s. 316-2 applies",  # 2 - 1 = 1: inside the window
        ]
    )
    assert clean_legislative_text(raw2).split("\n")[1] == "the exemption under s. 316-2 applies"


def test_hyphen_glued_number_still_stripped_after_a_letter():
    """The original fix target -- a hyphenated word broken by a glued
    margin number -- must keep working alongside the digit-hyphen guard."""
    raw = "\n".join(["first line 1", "Down syndrome, Phelan-2"])
    assert clean_legislative_text(raw) == "\n".join(["first line", "Down syndrome, Phelan-"])


def test_mark_words_orders_a_line_by_x0_not_top():
    """An underlined word 0.3pt higher than the plain heading word on the
    same line must still come after it (H1171's "Section 1.")."""
    words = [
        _word("Section", 108, 158, 450.42),
        _word("1.", 162, 176, 450.42),
        _word("This", 190, 220, 450.12),  # 0.3pt higher -- sorts first by top
        _word("act", 225, 245, 450.12),
    ]
    segments = [_seg(190, 245, 461.0, 461.5)]  # underline under "This act"
    assert mark_words(words, segments) == ["Section 1. [added: This act]"]


def _word_with_chars(text, x0, top, char_width=7.2):
    chars = [
        {"text": ch, "x0": x0 + i * char_width, "x1": x0 + (i + 1) * char_width,
         "top": top, "bottom": top + 12}
        for i, ch in enumerate(text)
    ]
    return {"text": text, "x0": x0, "x1": x0 + len(text) * char_width,
            "top": top, "bottom": top + 12, "chars": chars}


def test_mark_words_splits_a_word_whose_chars_are_struck_and_underlined():
    """"(6)(1)" printed as one word: "(6)" struck, "(1)" underlined."""
    word = _word_with_chars("(6)(1)", 100, 200)
    segments = [
        _seg(100, 121.6, 205.7, 206.3),  # strike through "(6)" (mid = 206)
        _seg(121.6, 143.2, 212.5, 213.0),  # underline under "(1)" (bottom = 212)
    ]
    following = _word("Commission", 150, 220, 200, 212)
    assert mark_words([word, following], segments) == [
        "[deleted: (6)][added: (1)] Commission"
    ]
    assert law_as_amended(mark_words([word, following], segments)[0]) == "(1) Commission"


def test_mark_words_split_pieces_stay_glued_inside_the_word():
    word = _word_with_chars("2.1.", 100, 200)
    nxt = _word_with_chars("new", 140, 200)
    segments = [
        _seg(100, 114.4, 212.5, 213.0),  # underline "2."
        _seg(114.4, 128.8, 205.7, 206.3),  # strike "1."
    ]
    # "new" is plain: the pieces keep their own markers, no space inside the word.
    assert mark_words([word, nxt], segments) == ["[added: 2.][deleted: 1.] new"]


def test_mark_words_does_not_split_a_partly_covered_word():
    """Characters that are merely unmarked (a rule stopping short of the
    ";") don't split the word -- only a struck/underlined disagreement does."""
    word = _word_with_chars("syndrome;", 100, 200)
    segments = [_seg(100, 157.6, 212.5, 213.0)]  # covers 8 of 9 chars
    assert mark_words([word], segments) == ["[added: syndrome;]"]


# --- compare_texts: stored vs re-extracted text ---------------------------


def test_compare_texts_identical_text_is_not_flagged():
    text = "Section 1. The agency shall act.\nSection 2. Effective July 1."
    result = compare_texts(text, text)
    assert result["length_ratio"] == 1.0
    assert result["old_headings"] == result["new_headings"] == 2
    assert result["deleted_pct"] == 0.0
    assert result["number_only_lines"] == 0
    assert result["flag"] is False
    assert result["reasons"] == []


def test_compare_texts_measures_on_law_as_amended():
    old = "Section 1. The agency shall act now."
    new = "Section 1. The agency [deleted: may] shall act [added: now]."
    result = compare_texts(old, new)
    assert result["old_len"] == result["new_len"]
    assert result["flag"] is False


def test_compare_texts_flags_length_change_over_15_percent():
    old = "Section 1. " + "word " * 100
    new = "Section 1. " + "word " * 80
    result = compare_texts(old, new)
    assert result["length_ratio"] < 0.85
    assert "length" in result["reasons"]
    assert result["flag"] is True

    within = compare_texts(old, "Section 1. " + "word " * 90)
    assert "length" not in within["reasons"]


def test_compare_texts_flags_mostly_deleted_text():
    old = "Section 1. keep"
    new = "Section 1. keep [deleted: " + "gone " * 40 + "]"
    result = compare_texts(old, new)
    assert result["deleted_pct"] > 60
    assert "deleted" in result["reasons"]


def test_compare_texts_flags_dropped_headings():
    old = "Section 1. A.\nSection 2. B.\nSection 3. C."
    new = "Section 1. A.\n[added: Section 2.] B. Section 3. C."
    result = compare_texts(old, new)
    assert result["old_headings"] == 3
    assert result["new_headings"] == 2
    assert "headings" in result["reasons"]


def test_compare_texts_flags_number_only_lines():
    old = "Section 1. A.\nB."
    new = "Section 1. A.\n12\nB."
    result = compare_texts(old, new)
    assert result["number_only_lines"] == 1
    assert "numbers" in result["reasons"]


def test_h1171_inserted_list_keeps_one_item_per_line():
    """The whole new s. 379.24312 is one underlined passage. Merging the
    per-line [added: ...] markers folded it onto a single line; list items
    now keep their own lines while each item's wrapped lines still join."""
    text = extract_pdf_text((FIXTURES / "h1171_filed.pdf").read_bytes())
    lines = text.split("\n")
    for item in ('(1) As used in this section', '(a) "Collect" means', '(b) "Endangered or threatened species"',
                 '(e) "Transport" means', "(2) A person may not collect", "(5)(a) This section does not"):
        assert any(line.startswith(f"[added: {item}") for line in lines), item
    # A wrapped item is still one line: its continuation isn't left behind.
    assert any(
        line.startswith('[added: (c) "Educational or exhibition purposes" means the holding, displaying')
        for line in lines
    )
    assert not any(line.startswith("[added: highway, waterway") for line in lines)


def test_merge_keeps_statute_citation_continuation_joined():
    from app.pipeline.bill_text import _merge_adjacent_markers

    text = "[added: as provided in]\n[added: s. 393.063, the agency shall act.]"
    assert _merge_adjacent_markers(text) == "[added: as provided in s. 393.063, the agency shall act.]"
