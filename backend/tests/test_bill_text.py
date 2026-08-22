"""Tests for legislative-PDF text cleaning.

`clean_legislative_text` is a pure function, so these run without LegiScan,
a PDF, or a database. The fixtures below are verbatim-shaped excerpts of
real Florida bill PDFs (HB 95 / HB 11, 2026 session) -- keep them that way,
since the whole point is matching the actual layout.
"""

from app.pipeline.bill_text import clean_html_legislative_text, clean_legislative_text


def test_strips_trailing_line_numbers():
    raw = "\n".join(
        [
            "A bill to be entitled 1",
            "An act relating to the security services on religious 2",
            "premises; amending s. 493.6102, F.S.; exempting 3",
        ]
    )
    assert clean_legislative_text(raw) == "\n".join(
        [
            "A bill to be entitled",
            "An act relating to the security services on religious",
            "premises; amending s. 493.6102, F.S.; exempting",
        ]
    )


def test_strips_page_furniture():
    raw = "\n".join(
        [
            "HB 95  2026",
            "CODING: Words stricken are deletions; words underlined are additions.",
            "hb95-00",
            "Page 1 of 2",
            "F L O R I D A  H O U S E  O F  R E P R E S E N T A T I V E S",
            "A bill to be entitled 1",
        ]
    )
    assert clean_legislative_text(raw) == "A bill to be entitled"


def test_keeps_numbers_that_are_not_line_numbers():
    """The sequence check is what makes this safe: statutory references and
    dollar figures routinely end a line, and a blunt trailing-digit strip
    would silently corrupt them."""
    raw = "\n".join(
        [
            "first line 1",
            "a valid license issued pursuant s. 790.06",
            "an appropriation of $479,997",
            "second content line 2",
        ]
    )
    cleaned = clean_legislative_text(raw).split("\n")
    assert cleaned == [
        "first line",
        "a valid license issued pursuant s. 790.06",
        "an appropriation of $479,997",
        "second content line",
    ]


def test_out_of_sequence_number_is_left_alone():
    """A trailing number that doesn't continue the sequence is content, not
    a line number."""
    raw = "\n".join(["first line 1", "the fee shall not exceed 500"])
    assert clean_legislative_text(raw).split("\n")[1] == "the fee shall not exceed 500"


def test_sequence_continues_across_page_furniture():
    """Line numbering runs continuously through the bill while headers
    repeat mid-document, so furniture must not reset the expected value."""
    raw = "\n".join(
        [
            "content line one 1",
            "content line two 2",
            "Page 1 of 2",
            "F L O R I D A  H O U S E  O F  R E P R E S E N T A T I V E S",
            "content line three 3",
        ]
    )
    assert clean_legislative_text(raw) == "\n".join(
        ["content line one", "content line two", "content line three"]
    )


def test_drops_blank_and_whitespace_only_lines():
    raw = "first 1\n\n   \nsecond 2\n"
    assert clean_legislative_text(raw) == "first\nsecond"


def test_senate_and_joint_resolution_headers():
    raw = "\n".join(["SB 1234  2026", "CS/HB 7  2026", "SJR 88  2026", "real content 1"])
    assert clean_legislative_text(raw) == "real content"


def test_empty_input():
    assert clean_legislative_text("") == ""


def test_text_with_no_furniture_is_unchanged():
    raw = "Be It Enacted by the Legislature of the State of Florida:"
    assert clean_legislative_text(raw) == raw


# --- HTML documents ------------------------------------------------------


def test_html_strips_leading_line_numbers():
    raw = "\n".join(
        [
            "    1                          Senate Resolution",
            "    2         A resolution designating February 3, 2026, as “Space",
            "    3         Day” in Florida.",
        ]
    )
    assert clean_html_legislative_text(raw) == "\n".join(
        [
            "Senate Resolution",
            "A resolution designating February 3, 2026, as “Space",
            "Day” in Florida.",
        ]
    )


def test_html_empty_numbered_line_does_not_break_the_sequence():
    """Regression: bills contain numbered lines with no content ("    4  ").
    Those arrive rstripped, so a pattern requiring whitespace after the
    digits fails to match, the expected sequence stalls, and every
    following line keeps its number embedded in the text."""
    raw = "\n".join(
        [
            "    1         first line",
            "    2         second line",
            "    3  ",
            "    4         fourth line",
        ]
    )
    assert clean_html_legislative_text(raw) == "\n".join(
        ["first line", "second line", "fourth line"]
    )


def test_html_strips_drafting_stamp():
    raw = "\n".join(["8-02178-26                                            20261780__", "    1         content"])
    assert clean_html_legislative_text(raw) == "content"


def test_html_keeps_out_of_sequence_numbers():
    """A line that legitimately opens with a number keeps it."""
    raw = "\n".join(["    1         first line", "2026 Regular Session begins"])
    assert clean_html_legislative_text(raw).split("\n")[1] == "2026 Regular Session begins"


def test_html_empty_input():
    assert clean_html_legislative_text("") == ""
