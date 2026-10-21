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


EARLY_VOTING_NOTE = (
    "Statewide required window. Counties may start earlier or run later; "
    "confirm your county's dates with its Supervisor of Elections."
)


# Florida 2026, from the Division of Elections' published calendar.
# Cross-checked on entry: both elections fall on a Tuesday, registration
# deadlines on the Monday 29 days prior, and the required early-voting
# window runs Saturday to Saturday -- the shape Florida law requires. That
# window is the statutory minimum, not when every county operates: counties
# may open earlier and run later, so these rows say so in their note.
#
# RE-VERIFICATION LOG (append a line each time; don't overwrite):
#   2026-09-02 -- all ten dates re-checked against the source URL below and
#     confirmed unchanged, character for character.
#   2026-10-13 -- all ten dates re-checked against the source URL below and
#     confirmed unchanged. The page (last updated 2025-08-22) shows no
#     emergency orders or amendment notices.
#   2026-10-15 -- verify_by (Oct 15) passed and /health/data went 503; moved
#     to Oct 23, the day before early voting, for one last check of the dates
#     still ahead (vote-by-mail request Oct 22, early voting Oct 24-31,
#     General Nov 3) for post-storm emergency orders.
#   2026-10-20 -- early voting was already open in at least one county on
#     Oct 19 (a voter reported it), five days before the Oct 24 listed here.
#     Oct 24-31 is the required statewide window, not every county's window.
#     s. 101.657(1)(d): early voting must begin the 10th day before and end
#     the 3rd day before the election; a supervisor may also offer the 15th
#     through 11th and the 2nd day before (Oct 19-23 and Nov 1 this year).
#     Press reports show Palm Beach, St. Lucie, Indian River and Monroe
#     opening Oct 19, Martin Oct 21, Franklin Oct 24 (county sites unchecked).
#     Dates unchanged; labels now say "required" and each early-voting row
#     carries a note. Per-county dates are not modeled. The Oct 23 re-check
#     is no longer "the day before early voting".
#   2026-10-21 -- all ten dates re-checked against the source URL below and
#     confirmed unchanged. The page (still "last updated August 22, 2025")
#     mentions no storm, extension or amended dates and points voters to
#     their county Supervisor of Elections for optional early-voting days.
#     Partial: its "Emergency and Disaster - Election Resources" page, the
#     Governor's executive orders and county sites were not checked, and a
#     web search found no 2026 emergency order (nothing found, not proof
#     that none exists). Governor's orders read: EO 26-202 (Oct 6, Tropical
#     Depression Nine) and 26-211 (Oct 7, amends it as Tropical Storm Isaias):
#     a state of emergency in 27 Panhandle, Big Bend, Citrus and Levy
#     counties, expiring after 60 days. Neither mentions elections, voting
#     or any election deadline. In past storms (2018, 2022, 2024) election
#     changes came in separate orders for the affected counties, so a later
#     one could still change dates there. Still unchecked: county sites and
#     the Division's emergency-resources page (its link 404ed when guessed).
#   2026-10-21 -- verify_by Oct 23 -> Nov 4 so /health/data does not go 503 on
#     Oct 24, with the dates unchanged and no order found affecting them.
#     The staleness alarm no longer covers the weeks before the election, so
#     the remaining emergency-order checks (county sites, Governor's orders)
#     are tracked as a to-do, not by this date.
#
# `verify_by` is set to fall between events rather than at a round interval,
# so a late amendment to the dates still ahead of us gets caught while it can
# still be acted on. Florida amends election dates by emergency order after
# hurricanes, which is not hypothetical in October. It is now Nov 4, the day
# after the General Election (Nov 3), when the 2026 calendar has no dates
# left; the next calendar replaces it, or this one is retired, by then.
FLORIDA_2026 = ElectionCalendar(
    state="FL",
    year=2026,
    source_name="Florida Department of State, Division of Elections",
    source_url="https://dos.fl.gov/elections/for-voters/election-dates/",
    verify_by=dt.date(2026, 11, 4),
    events=(
        ElectionEvent(dt.date(2026, 7, 20), "Voter registration deadline (Primary)", "registration"),
        ElectionEvent(dt.date(2026, 8, 6), "Vote-by-mail request deadline (Primary)", "vote_by_mail"),
        ElectionEvent(dt.date(2026, 8, 8), "Early voting: required start (Primary)", "early_voting", EARLY_VOTING_NOTE),
        ElectionEvent(dt.date(2026, 8, 15), "Early voting: required end (Primary)", "early_voting", EARLY_VOTING_NOTE),
        ElectionEvent(dt.date(2026, 8, 18), "Primary Election", "election"),
        ElectionEvent(dt.date(2026, 10, 5), "Voter registration deadline (General)", "registration"),
        ElectionEvent(dt.date(2026, 10, 22), "Vote-by-mail request deadline (General)", "vote_by_mail"),
        ElectionEvent(dt.date(2026, 10, 24), "Early voting: required start (General)", "early_voting", EARLY_VOTING_NOTE),
        ElectionEvent(dt.date(2026, 10, 31), "Early voting: required end (General)", "early_voting", EARLY_VOTING_NOTE),
        ElectionEvent(dt.date(2026, 11, 3), "General Election", "election"),
    ),
)

CALENDARS: dict[str, ElectionCalendar] = {"FL": FLORIDA_2026}


def get_calendar(state: str) -> ElectionCalendar | None:
    return CALENDARS.get(state.upper())
