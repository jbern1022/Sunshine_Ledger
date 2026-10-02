import pytest

from app.pipeline.effective_date import effective_clause


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Section 5. This act shall take effect July 1, 2026.", ("July 1, 2026", False)),
        ("Section 9. This act shall take effect upon becoming a\nlaw.", ("upon becoming a law", False)),
        (
            "Section 12. Except as otherwise expressly provided in this act, this act shall take effect July 1, 2025.",
            ("July 1, 2025", True),
        ),
        (
            "Section 4. Effective Date. Adoption of this Ordinance\nshall be deemed to constitute a quasi -judicial action "
            "of the City Council and shall become effective upon signature by the Council President and Council Secretary.",
            ("upon signature by the Council President and Council Secretary", False),
        ),
        ("Section 2. This ordinance shall become effective upon signature by the Mayor.", ("upon signature by the Mayor", False)),
        ("[deleted: This act shall take effect July 1, 2025.] [added: This act shall take effect July 1, 2026.]", ("July 1, 2026", False)),
        (
            "Section 4. Except as otherwise expressly provided in this act and except for this section, which "
            "shall take effect upon this act becoming a law, this act shall take effect July 1, 2026.",
            ("July 1, 2026", True),
        ),
        ("A resolution recognizing a local hero.", None),
        (None, None),
    ],
)
def test_effective_clause(text, expected):
    assert effective_clause(text) == expected


# R8 (HB 1389 validation): the bill's one effective date hid four other
# dates: a retroactive section, a first tax roll, a 2030 sunset, deadlines.
def _hb1389():
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "bill_text" / "hb1389_2026_enrolled.txt").read_text()


def test_hb1389_provision_dates():
    from app.pipeline.effective_date import provision_dates

    found = [(d["kind"], d["when"], d["date"], d["section"], d["scopes"]) for d in provision_dates(_hb1389())]
    assert found == [
        ("expires", "July 1, 2030", "2030-07-01", "Section 1", ["s. 125.01055(7)(a)2."]),
        ("expires", "July 1, 2030", "2030-07-01", "Section 2", ["s. 166.04151(7)(a)2."]),
        ("retroactive", "January 1, 2024", "2024-01-01", "Section 3", ["s. 125.01055(7)(n)", "s. 166.04151(7)(n)"]),
        ("deadline", "July 1, 2026", "2026-07-01", "Section 4", ["Section 4"]),
        ("tax_roll", "the 2027 tax roll", None, "Section 6", ["s. 196.1978"]),
        ("deadline", "December 31, 2027", "2027-12-31", "Section 12", ["Section 12"]),
    ]


def test_provision_date_quotes_are_whole_sentences():
    from app.pipeline.effective_date import provision_dates

    by_kind = {d["kind"]: d for d in provision_dates(_hb1389())}
    assert by_kind["expires"]["quote"] == "This subparagraph expires July 1, 2030."
    assert by_kind["tax_roll"]["quote"] == (
        "The amendments made by this act to s. 196.1978, Florida Statutes, first apply to the 2027 property tax roll."
    )


def test_the_acts_own_effective_date_and_the_title_are_not_provision_dates():
    from app.pipeline.effective_date import provision_dates

    text = ("A bill to be entitled An act relating to fees; requiring reports by a specified date; "
            "providing an effective date.\n"
            "Section 1. The clerk shall keep fee records.\n"
            "Section 2. This act shall take effect July 1, 2027.\n")
    assert provision_dates(text) == []


def test_a_section_with_its_own_effective_date():
    from app.pipeline.effective_date import provision_dates

    text = ("Section 1. The clerk shall keep fee records.\n"
            "Section 2. This section shall take effect upon becoming a law. Section 1 shall take effect January 1, 2028.\n"
            "Section 3. Except as otherwise provided, this act shall take effect July 1, 2027.\n")
    [d] = provision_dates(text)
    assert (d["kind"], d["date"], d["section"]) == ("takes_effect", "2028-01-01", "Section 2")
