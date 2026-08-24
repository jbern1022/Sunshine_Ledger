"""Status normalisation tests.

Sources disagree about case, and Miami's iQM2 disagrees with itself --
"Discussed" and "DISCUSSED" both appear for the same status. Stored
verbatim that splits one status in two, so filtering for "Adopted" silently
missed the 76 bills recorded as "ADOPTED".
"""

from app.pipeline._status import normalize_status


def test_shouted_status_is_folded_to_title_case():
    assert normalize_status("ADOPTED") == "Adopted"


def test_case_variants_converge_on_one_value():
    """The actual bug: the same status stored twice under different casing."""
    assert normalize_status("ADOPTED") == normalize_status("Adopted")
    assert normalize_status("WITHDRAWN") == normalize_status("Withdrawn")
    assert normalize_status("DISCUSSED") == normalize_status("Discussed")


def test_minor_words_stay_lowercase():
    """Matches the mixed-case values already in the data ("Approved with
    Conditions"), so normalised values don't look foreign beside them."""
    assert normalize_status("PASSED ON FIRST READING") == "Passed on First Reading"


def test_leading_minor_word_is_still_capitalised():
    assert normalize_status("IN COMMITTEE") == "In Committee"


def test_parenthesised_suffix_reads_naturally():
    assert normalize_status("ADOPTED WITH MODIFICATION(S)") == "Adopted with Modification(s)"


def test_mixed_case_is_left_exactly_alone():
    """We can't tell an intentional capitalisation from a shouted one, and
    inventing a house style for another government's vocabulary would be
    worse than inconsistency."""
    for value in ("Approved with Conditions", "Recommended Approval - Passed", "Denied – Passed"):
        assert normalize_status(value) == value


def test_multi_word_shout_with_hyphenation_survives():
    assert normalize_status("INDEFINITELY DEFERRED") == "Indefinitely Deferred"


def test_whitespace_is_trimmed():
    assert normalize_status("  ADOPTED  ") == "Adopted"


def test_none_and_empty_pass_through():
    assert normalize_status(None) is None
    assert normalize_status("") == ""


def test_single_word_lowercase_input_is_untouched():
    """Not all-caps, so not ours to restyle."""
    assert normalize_status("draft") == "draft"
