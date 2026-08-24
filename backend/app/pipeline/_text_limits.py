"""Shared column-width guards for ingested free-text fields.

External sources supply free text with no length contract, and several
columns here are bounded. A value that overflows raises mid-transaction and,
because the scheduled runner aborts on first error, takes down every later
step in the nightly job with it -- that is how a single 69-character
Jacksonville committee name stopped ingestion for four consecutive nights.

Columns are sized generously enough that these guards should never fire.
They exist so that when a source produces something unexpected, one bill is
imperfect rather than the whole run being lost.
"""

from __future__ import annotations

# Keep in sync with the models. Duplicated deliberately: importing the model
# metadata here would make the pipeline depend on the ORM for a constant.
ENTITY_NAME_MAX_LENGTH = 500
CHAMBER_MAX_LENGTH = 200


def fit(value: str | None, max_length: int) -> str | None:
    """Trim `value` to `max_length`, marking it with an ellipsis when cut.

    Returns None unchanged so callers can pass optional fields straight
    through.
    """
    if value is None or len(value) <= max_length:
        return value
    return value[: max_length - 1] + "…"
