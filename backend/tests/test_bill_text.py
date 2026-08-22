"""Tests for legislative-PDF text cleaning.

`clean_legislative_text` is a pure function, so these run without LegiScan,
a PDF, or a database. The fixtures below are verbatim-shaped excerpts of
real Florida bill PDFs (HB 95 / HB 11, 2026 session) -- keep them that way,
since the whole point is matching the actual layout.
"""

from app.pipeline.bill_text import clean_legislative_text


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
