"""Metes-and-bounds boundary descriptions in local bills (H0509 Collier
Mosquito Control District, H4021, H4025, H4031, H4059, H4091, H4095: every
night since 2026-11-19 at least). The model quoted the boundary, the quote
ran past the 4,096-token output cap inside the FIRST item, nothing could be
salvaged, and the bill failed again the next night."""

from app.pipeline.bill_layers import _law_text
from app.pipeline.bill_layers_text import (
    BOUNDARY_PLACEHOLDER_PREFIX,
    elide_boundary_descriptions,
    verify_quotes,
)

CALLS = "".join(
    f"THENCE NORTH {i} DEGREES EAST ALONG THE WEST LINE OF SECTION {i}, TOWNSHIP 47 SOUTH, RANGE 27 EAST, "
    f"A DISTANCE OF {100 + i}.00 FEET TO A POINT; "
    for i in range(12)
)
BOUNDARY = (
    "BEGINNING WHERE THE NORTH LINE OF TOWNSHIP 47 SOUTH INTERSECTS THE EAST LINE OF RANGE 27 EAST; "
    + CALLS
    + "THENCE WEST TO THE POINT OF BEGINNING."
)
BILL = (
    "Section 1. The district shall control mosquitoes within the following area:\n"
    + BOUNDARY
    + "\nSection 2. The board of commissioners shall adopt an annual budget by October 1."
)


def test_long_boundary_is_replaced_and_the_rest_is_untouched():
    out = elide_boundary_descriptions(BILL)
    assert "THENCE" not in out
    assert BOUNDARY_PLACEHOLDER_PREFIX in out
    assert f"{len(BOUNDARY):,} characters" in out
    assert out.startswith("Section 1. The district shall control mosquitoes within the following area:\n")
    assert out.endswith("\nSection 2. The board of commissioners shall adopt an annual budget by October 1.")


def test_a_few_thence_clauses_are_left_alone():
    short = "Section 1. The line runs north; THENCE east 10 feet; THENCE south 5 feet to the corner."
    assert elide_boundary_descriptions(short) == short


def test_text_without_boundaries_is_identical():
    text = "Section 1. A municipality may not require parking for a qualifying development."
    assert elide_boundary_descriptions(text) == text


def test_law_text_given_to_the_model_has_no_boundary():
    law = _law_text(BILL)
    assert "THENCE" not in law
    assert "shall adopt an annual budget" in law


def test_a_quote_containing_the_placeholder_is_dropped():
    law = _law_text(BILL)
    placeholder = law[law.index(BOUNDARY_PLACEHOLDER_PREFIX):law.index("]") + 1]
    kept, dropped = verify_quotes(
        [
            {"quote": "The board of commissioners shall adopt an annual budget by October 1."},
            {"quote": "The district shall control mosquitoes within the following area:\n" + placeholder},
        ],
        law,
    )
    assert [k["quote"] for k in kept] == ["The board of commissioners shall adopt an annual budget by October 1."]
    assert len(dropped) == 1
