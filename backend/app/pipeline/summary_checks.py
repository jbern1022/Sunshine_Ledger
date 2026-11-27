"""Checks on a generated "what it does" summary that the prompt alone didn't fix.

From the 2026-11-27 accuracy re-run (docs/grant-ready/ACCURACY_RERUN_2026-11-27.md):

- Open Government Sunset Review bills: the model inverted the sunset
  ("will remain in place unless it is repealed") even after a prompt rule, so
  the sunset sentence is written by rule from the bill text instead.
- Status words: "has passed", "has agreed", "is now renamed" on records that
  were never enacted or adopted. A summary says what a measure does, not
  whether it passed.
- Dropped conditions on title-only local items: "accept, if awarded, grant
  funding" became "accept grant funding".

Modality on title-only items lives with the other modal checks:
bill_layers_text.overstates_title_modal.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.pipeline.bill_layers_text import law_as_amended

# --- Enacted -------------------------------------------------------------------------

# Exact statuses (lower-cased) that mean the measure took effect or was finally
# adopted. Substring tests don't work: "Passed on First Reading", "Passed
# Senate" and "Recommended Approval" are not final.
ENACTED_STATUSES = frozenset({
    "passed",  # LegiScan: passed both chambers; a veto shows as "Vetoed"
    "became law",  # Congress.gov
    "enacted",
    "adopted",
    "adopted with modification(s)",
    "approved",
    "approved with conditions",
    "commission approval",
    "recommended approval - passed",
    "recommended approval with conditions - passed",
})


def is_enacted(status: str | None) -> bool:
    return (status or "").strip().lower() in ENACTED_STATUSES


# --- Status words --------------------------------------------------------------------

_STATUS_VERB = r"(?:passed|agreed|approved|adopted|enacted|ratified|signed)"
# The legislature, a chamber or a governing body as the subject: "Margate has
# agreed", "The Florida Senate has passed", "the City Commission has approved".
_BODY = (
    r"(?:legislature|senate|house(?:\s+of\s+representatives)?|congress|commission|council|board|"
    r"city|county|town|village|government|governor|mayor)"
)
_STATUS_PATTERNS = [
    re.compile(rf"\b{_BODY}(?:'s\s+\w+(?:\s+\w+)?)?\s+(?:has|have)\s+(?:now\s+|already\s+)?{_STATUS_VERB}\b", re.IGNORECASE),
    re.compile(rf"\b(?:this|the)\s+(?:bill|resolution|ordinance|measure|act|legislation)\s+(?:has|was)\s+(?:been\s+)?(?:passed|adopted|enacted|signed|approved)\b", re.IGNORECASE),
    re.compile(r"\bhas\s+been\s+(?:passed|enacted|signed\s+into\s+law)\b", re.IGNORECASE),
    re.compile(r"\b(?:became|has\s+become)\s+law\b", re.IGNORECASE),
    # "X is now renamed / called / known as / law / in effect"
    re.compile(r"\bis\s+now\s+(?:renamed|called|named|known\s+as|law|in\s+effect|officially)\b", re.IGNORECASE),
]


def overstates_status(text: str, *, jurisdiction: str | None = None) -> bool:
    """True when the summary reports the measure's progress ("has passed",
    "has agreed", "is now renamed") rather than what it does."""
    if any(p.search(text) for p in _STATUS_PATTERNS):
        return True
    if jurisdiction:
        name = re.escape(jurisdiction.strip())
        pattern = rf"\b{name}(?:'s\s+\w+(?:\s+\w+)?)?\s+(?:has|have)\s+(?:now\s+|already\s+)?{_STATUS_VERB}\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# --- Open Government Sunset Review ---------------------------------------------------

_OGSR_TITLE = re.compile(r"\bOGSR\b|open\s+government\s+sunset\s+review", re.IGNORECASE)
_SUNSET = re.compile(
    r"shall\s+stand\s+repealed\s+on\s+([A-Z][a-z]+\s+\d{1,2},\s*\d{4}),?\s+unless\s+reviewed\s+and\s+saved\s+"
    r"from\s+repeal\s+through\s+reenactment\s+by\s+the\s+Legislature",
    re.IGNORECASE,
)
# A summary sentence about the sunset: the one the rule replaces.
_SUNSET_TALK = re.compile(
    r"\b(?:repeal\w*|reenact\w*|sunset\w*|expir\w*|remain\w*\s+in\s+(?:place|effect)|saved\s+from)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def is_sunset_review(title: str | None, bill_text: str | None) -> bool:
    if _OGSR_TITLE.search(title or ""):
        return True
    head = (bill_text or "")[:1500]  # the act title, before "Be It Enacted"
    return bool(_OGSR_TITLE.search(" ".join(head.split())))


def _normalize_date(d: str) -> str:
    return re.sub(r",\s*", ", ", " ".join(d.split()))


def _date_key(d: str) -> tuple:
    try:
        return (0, datetime.strptime(d, "%B %d, %Y").date())
    except ValueError:  # an unparseable date keeps its place after the real ones
        return (1, d)


def sunset_sentence(bill_text: str) -> str | None:
    """The sunset as the law will read after the bill, as one fixed sentence.

    None when the bill has no Open Government sunset clause before or after.
    """
    flat = " ".join((bill_text or "").split())
    after = []
    for m in _SUNSET.finditer(" ".join(law_as_amended(bill_text or "").split())):
        d = _normalize_date(m.group(1))
        if d not in after:
            after.append(d)
    if after:
        after.sort(key=_date_key)
        if len(after) == 1:
            return f"The exemption is repealed on {after[0]}, unless the Legislature reenacts it."
        dates = after[0] + " and " + after[1] if len(after) == 2 else "; ".join(after[:-1]) + "; and " + after[-1]
        return f"The exemptions are repealed on {dates}, unless the Legislature reenacts them."
    if _SUNSET.search(flat):
        # The clause is in the bill but struck out: the exemption is saved from repeal.
        return "The bill removes the scheduled repeal, so the exemption no longer expires."
    return None


def apply_sunset_rule(summary: str, bill_text: str, title: str | None = None) -> str:
    """Replace whatever the summary says about the sunset with the rule-based sentence.

    Only for Open Government Sunset Review bills; anything else is returned unchanged.
    """
    if not is_sunset_review(title, bill_text):
        return summary
    rule = sunset_sentence(bill_text)
    if rule is None:
        return summary
    kept = [s for s in _SENTENCE.split(summary.strip()) if s and not _SUNSET_TALK.search(s)]
    return " ".join([*kept, rule])


# --- Dropped conditions --------------------------------------------------------------

# (condition in the source, what the summary must still say).
_CONDITIONS = [
    # "if received" and "pending an award" keep the condition in other words.
    (re.compile(r"\bif\s+awarded\b", re.IGNORECASE), re.compile(r"\b(?:if|once|when|provided|unless|pending|contingent)\b[^.]{0,80}?\b(?:award\w*|receiv\w*|granted)\b", re.IGNORECASE)),
    (re.compile(r"\bif\s+(?:funded|funding\s+is\s+(?:available|approved))\b", re.IGNORECASE), re.compile(r"\b(?:if|once|when|provided|subject\s+to)\b[^.]{0,80}\bfund", re.IGNORECASE)),
    (re.compile(r"\bsubject\s+to\s+(?:the\s+)?appropriation\b", re.IGNORECASE), re.compile(r"\bappropriat", re.IGNORECASE)),
    (re.compile(r"\bsubject\s+to\s+(?:the\s+)?availability\s+of\s+funds\b", re.IGNORECASE), re.compile(r"\bavailab", re.IGNORECASE)),
    (re.compile(r"\bcontingent\s+(?:up)?on\b", re.IGNORECASE), re.compile(r"\b(?:contingent|only\s+if|if|once|provided)\b", re.IGNORECASE)),
]


def drops_condition(summary: str, source: str) -> bool:
    """True when the source attaches a condition ("if awarded", "subject to
    appropriation") that the summary leaves out."""
    flat_source = " ".join((source or "").split())
    return any(cond.search(flat_source) and not kept.search(summary) for cond, kept in _CONDITIONS)
