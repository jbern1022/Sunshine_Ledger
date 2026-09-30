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
