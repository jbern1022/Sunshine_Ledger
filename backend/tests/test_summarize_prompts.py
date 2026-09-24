"""Tests for summary prompt contents and versioning.

Verifies that the prompt constants contain the required marker explanation
and that prompt version changes correctly invalidate cached summaries.
"""

from app.pipeline.summarize import (
    PROMPT_VERSION,
    WHAT_IT_DOES_PROMPT,
    WHO_IT_AFFECTS_PROMPT,
    summary_input_hash,
)


def test_what_it_does_prompt_contains_marker_explanation():
    """The 'what it does' prompt must explain the inline change markers."""
    marker_explanation = "In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds; describe the change, not the markers."
    assert marker_explanation in WHAT_IT_DOES_PROMPT


def test_who_it_affects_prompt_contains_marker_explanation():
    """The 'who it affects' prompt must explain the inline change markers."""
    marker_explanation = "In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds; describe the change, not the markers."
    assert marker_explanation in WHO_IT_AFFECTS_PROMPT


def test_hash_differs_between_prompt_versions():
    """Bumping PROMPT_VERSION must change the hash so cached summaries are
    invalidated and re-generated with the new prompt."""
    test_text = "test bill text"
    test_model = "test-model"

    current_hash = summary_input_hash(test_text, model=test_model)
    old_hash = summary_input_hash(test_text, model=test_model, prompt_version="1")

    assert current_hash != old_hash, "Hash should change when prompt version changes"


def test_prompt_version_is_2():
    """Verify that PROMPT_VERSION has been bumped to 2."""
    assert PROMPT_VERSION == "2"
