"""Official election calendar data (BRD 5.8).

BRD 5.8: "The system shall surface Florida's election calendar in relation
to tracked bills, without scoring or predictive claims at MVP."

That constraint shapes what lives here. This module holds *dates published
by the state*, nothing else -- no candidate data, no competitiveness
ratings, no "this bill could matter in November". Those would be
predictive claims, and the Roadmap additionally gates electioneering-adjacent
work behind a legal review that hasn't happened.

Every entry carries the official source it came from, so a reader can check
the date against the state rather than trusting this site -- the same
sourcing rule the rest of the app follows for bills.

Keyed by state per BRD 6's state-agnostic requirement: adding another state
means adding a key here, not changing code. Dates are hand-entered from the
official calendar because no stable machine-readable feed exists; the
`verify_by` field is when someone should re-check them against the source.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class ElectionEvent:
    date: dt.date
    label: str
    # "election" for the elections themselves; the rest are the deadlines
    # that decide whether someone can take part in one.
    kind: str
    note: str = ""


@dataclass(frozen=True)
class ElectionCalendar:
    state: str
    year: int
    source_name: str
    source_url: str
    verify_by: dt.date
    events: tuple[ElectionEvent, ...]


# Florida 2026, from the Division of Elections' published calendar.
# Cross-checked on entry: both elections fall on a Tuesday, registration
# deadlines on the Monday 29 days prior, and early voting runs Saturday to
# Saturday -- the shape Florida law requires.
FLORIDA_2026 = ElectionCalendar(
    state="FL",
    year=2026,
    source_name="Florida Department of State, Division of Elections",
    source_url="https://dos.fl.gov/elections/for-voters/election-dates/",
    verify_by=dt.date(2026, 10, 1),
    events=(
        ElectionEvent(dt.date(2026, 7, 20), "Voter registration deadline (Primary)", "registration"),
        ElectionEvent(dt.date(2026, 8, 6), "Vote-by-mail request deadline (Primary)", "vote_by_mail"),
        ElectionEvent(dt.date(2026, 8, 8), "Early voting begins (Primary)", "early_voting"),
        ElectionEvent(dt.date(2026, 8, 15), "Early voting ends (Primary)", "early_voting"),
        ElectionEvent(dt.date(2026, 8, 18), "Primary Election", "election"),
        ElectionEvent(dt.date(2026, 10, 5), "Voter registration deadline (General)", "registration"),
        ElectionEvent(dt.date(2026, 10, 22), "Vote-by-mail request deadline (General)", "vote_by_mail"),
        ElectionEvent(dt.date(2026, 10, 24), "Early voting begins (General)", "early_voting"),
        ElectionEvent(dt.date(2026, 10, 31), "Early voting ends (General)", "early_voting"),
        ElectionEvent(dt.date(2026, 11, 3), "General Election", "election"),
    ),
)

CALENDARS: dict[str, ElectionCalendar] = {"FL": FLORIDA_2026}


def get_calendar(state: str) -> ElectionCalendar | None:
    return CALENDARS.get(state.upper())
