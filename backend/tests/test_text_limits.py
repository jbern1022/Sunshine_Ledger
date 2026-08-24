"""Guards against bounded columns overflowing on external free text.

The nightly ingestion aborted on four consecutive runs because a
69-character Jacksonville committee name didn't fit a 50-character column.
The column is now wider, but the guard exists so the next surprise costs one
imperfect field rather than a whole night's pipeline.
"""

from app.pipeline._text_limits import CHAMBER_MAX_LENGTH, ENTITY_NAME_MAX_LENGTH, fit


def test_short_values_pass_through_untouched():
    assert fit("Finance Committee", CHAMBER_MAX_LENGTH) == "Finance Committee"


def test_none_passes_through():
    """Callers hand optional source fields straight in."""
    assert fit(None, CHAMBER_MAX_LENGTH) is None


def test_value_at_the_limit_is_not_trimmed():
    value = "x" * CHAMBER_MAX_LENGTH
    assert fit(value, CHAMBER_MAX_LENGTH) == value


def test_overlong_value_is_trimmed_to_the_limit():
    result = fit("x" * (CHAMBER_MAX_LENGTH + 50), CHAMBER_MAX_LENGTH)
    assert len(result) == CHAMBER_MAX_LENGTH


def test_trimmed_value_is_marked_as_trimmed():
    """A silently truncated name reads as the real name. The ellipsis makes
    the loss visible to anyone reading the data."""
    assert fit("x" * 400, CHAMBER_MAX_LENGTH).endswith("…")


def test_real_committee_names_now_fit():
    """The longest Jacksonville body name observed via the Legistar API was
    87 characters -- the case that broke ingestion."""
    longest = "Special Committee on Assessing the City's Building and Development Permitting Processes"
    assert len(longest) > 50, "regression fixture should exceed the old column width"
    assert fit(longest, CHAMBER_MAX_LENGTH) == longest


def test_entity_name_limit_is_defined():
    assert ENTITY_NAME_MAX_LENGTH == 500
