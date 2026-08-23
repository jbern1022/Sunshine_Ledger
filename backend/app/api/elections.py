from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.data.elections import get_calendar

router = APIRouter(prefix="/elections", tags=["elections"])


@router.get("")
def election_calendar(
    state: str | None = Query(None, description="Two-letter state code; defaults to the configured state"),
    today: dt.date | None = Query(None, description="Override the current date (testing)"),
) -> dict:
    """Published election dates for a state (BRD 5.8).

    Returns dates and nothing else. No candidates, no competitiveness, no
    suggestion that any tracked bill bears on any race -- BRD 5.8 rules out
    scoring and predictive claims at MVP, and the Roadmap gates
    electioneering-adjacent features behind a legal review that hasn't
    happened.

    Each event is marked past or upcoming rather than listed flat, because a
    calendar that still advertises a finished election as "upcoming" is
    worse than no calendar. `next_event` is the soonest event still ahead.
    """
    code = (state or settings.legiscan_state).upper()
    calendar = get_calendar(code)
    if calendar is None:
        raise HTTPException(status_code=404, detail=f"No election calendar available for '{code}'")

    now = today or dt.date.today()
    events = []
    for event in calendar.events:
        days_away = (event.date - now).days
        events.append(
            {
                "date": event.date.isoformat(),
                "label": event.label,
                "kind": event.kind,
                "is_past": event.date < now,
                "days_away": days_away,
            }
        )

    upcoming = [e for e in events if not e["is_past"]]

    return {
        "state": calendar.state,
        "year": calendar.year,
        "source": {"name": calendar.source_name, "url": calendar.source_url},
        # Surfaced so stale hand-entered data is visible rather than silently
        # trusted -- there's no machine-readable feed behind this.
        "verify_by": calendar.verify_by.isoformat(),
        "as_of": now.isoformat(),
        "next_event": upcoming[0] if upcoming else None,
        "events": events,
    }
