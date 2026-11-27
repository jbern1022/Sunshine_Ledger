"""The status a reader sees, for filtering and counting bills.

LegiScan leaves many Florida bills at "Introduced" (or "Engrossed") after their
final action (D9 in docs/grant-ready/W1_BASELINE_2026-11-25.md: 352 bills of
the ended 2026 Regular Session on 2026-11-25). Bill cards and pages read the
real outcome from the last action (frontend/lib/displayStatus.ts); the status
filter and its counts use this module so a filter never disagrees with the
cards it returns. KEEP THE RULES IN STEP WITH displayStatus.ts. The frontend
shows "Replaced by CS/HB 1219"; here every replacement is one group,
"Replaced", because a filter cannot have one option per companion bill.

The stored `Bill.status` is never changed.
"""

import re

from sqlalchemy import case

from app.models import Bill

REREAD = ("Introduced", "Engrossed")

# (Python regex, PostgreSQL regex, reader group), most specific first. Both
# are case-insensitive. PostgreSQL writes a word boundary as \y, Python \b.
RULES: list[tuple[str, str, str]] = [
    (r"^Laid on Table,?\s+refer(\s+to)?\s+\S", r"^Laid on Table,?\s+refer(\s+to)?\s+\S", "Replaced"),
    (r"^Adopted,\s+companion bill\(s\) passed,\s+see\s+\S", r"^Adopted,\s+companion bill\(s\) passed,\s+see\s+\S", "Replaced"),
    (r"^Adopted by Publication", r"^Adopted by Publication", "Adopted"),
    (r"^Died\b", r"^Died\y", "Died"),
    (r"^Withdrawn\b", r"^Withdrawn\y", "Withdrawn"),
    (r"^Laid on Table\.?\s*$", r"^Laid on Table\.?\s*$", "Tabled"),
]
_COMPILED = [(re.compile(py, re.IGNORECASE), group) for py, _, group in RULES]


def reader_status(status: str | None, last_action: str | None) -> str | None:
    s = (status or "").strip() or None
    if s in REREAD and last_action:
        action = last_action.strip()
        for pattern, group in _COMPILED:
            if pattern.search(action):
                return group
    return s


def reader_status_expr():
    """SQL twin of reader_status(), over Bill.status and Bill.last_action."""
    whens = [
        (Bill.status.in_(REREAD) & Bill.last_action.op("~*")(pg), group)
        for _, pg, group in RULES
    ]
    return case(*whens, else_=Bill.status)


def reader_status_filter(value: str):
    """WHERE clause: bills whose reader status is `value`."""
    return reader_status_expr() == value

