"""Status normalisation for ingested bills.

Sources disagree about case, and one source disagrees with itself: Miami's
iQM2 emits both "Discussed" and "DISCUSSED" for the same status. Stored
verbatim, that splits one status into two -- a reader filtering for
"Adopted" silently misses the 76 bills recorded as "ADOPTED", and status
badges shout at them in the UI.

Only all-caps values are touched. Anything already mixed-case is left
exactly as the source wrote it, because we can't tell an intentional
capitalisation from a shouted one, and inventing a house style for
another government's vocabulary would be worse than inconsistency.
"""

from __future__ import annotations

# Words a title-cased status leaves lowercase unless they lead. Matches how
# the mixed-case values already in the data read ("Approved with
# Conditions", "Passed on First Reading"), so normalised values sit
# alongside untouched ones without looking foreign.
_MINOR_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
)


def normalize_status(status: str | None) -> str | None:
    """Fold a shouted status into title case, leaving anything else alone.

    >>> normalize_status("ADOPTED")
    'Adopted'
    >>> normalize_status("PASSED ON FIRST READING")
    'Passed on First Reading'
    >>> normalize_status("Approved with Conditions")
    'Approved with Conditions'
    """
    if not status:
        return status

    stripped = status.strip()
    if not stripped or not stripped.isupper():
        return stripped

    words = stripped.split()
    out: list[str] = []
    for index, word in enumerate(words):
        lowered = word.lower()
        # Keep parenthesised suffixes readable: "MODIFICATION(S)" should
        # become "Modification(s)", not "Modification(S)".
        if index > 0 and lowered.strip("()") in _MINOR_WORDS:
            out.append(lowered)
        else:
            out.append(lowered[:1].upper() + lowered[1:])
    return " ".join(out)
