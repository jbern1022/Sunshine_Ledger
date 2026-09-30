"""When a bill says it takes effect, read from its own text.

Florida acts end with an effective-date section ("This act shall take
effect July 1, 2026." / "... upon becoming a law."), and Jacksonville
ordinances with "... shall become effective upon signature by the Council
President ...". Checked 2026-09-30 against every stored text: those shapes
cover ~90% of state bills. This is what the bill says, not a legal
determination -- a vetoed bill never takes effect, and some sections can
carry their own dates ("Except as otherwise provided ...").
"""

from __future__ import annotations

import re

from app.pipeline.bill_layers_text import law_as_amended

_CLAUSE = re.compile(
    r"(?P<sentence>[^.]*?\bthis (?:act|ordinance|resolution)\b[^.]{0,200}?"
    r"\b(?:takes?|becomes?|shall become) (?:effect|effective)\s+(?P<when>[^.]{3,200}?)\.)(?=\s|$)",
    re.IGNORECASE,
)
_VERB = re.compile(r"\b(?:takes?|becomes?|shall become) (?:effect|effective)\s+", re.IGNORECASE)
_TAIL_CHARS = 20_000  # the clause is the last section; don't scan a 1.6 MB budget


def effective_clause(text: str | None) -> tuple[str, bool] | None:
    """(when, has_exceptions) from the bill's last effective-date clause:
    ("July 1, 2026", False), ("upon becoming a law", True), or None."""
    if not text:
        return None
    tail = " ".join(law_as_amended(text[-_TAIL_CHARS:]).split())
    matches = list(_CLAUSE.finditer(tail))
    if not matches:
        return None
    last = matches[-1]
    # "..., except for this section, which shall take effect upon this act
    # becoming a law, this act shall take effect July 1, 2026." -- the act's
    # own date is the last one in the sentence.
    when = _VERB.split(last.group("sentence"))[-1].strip().rstrip(".").strip()
    return when, "except" in last.group("sentence").lower()
