"""Recording and labelling when an official leaves office
(Todoist 6hvxq2x37jGMjR5G).

A tenure ends with a date, a reason from a fixed list, and a source for the
reason. Former officials keep their pages and records; they get a visible
"Former ..." label. A promise by someone who left office is never marked
unfulfilled because of the exit.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ElectionWinner, Entity, OfficeTenure
from app.models.office_tenure import END_REASONS

LEFT_OFFICE_STATUS = "Left office before outcome could be determined"

OFFICE_NAMES = {
    "us_house": "U.S. Representative",
    "us_senate": "U.S. Senator",
    "fl_house": "Florida House member",
    "fl_senate": "Florida Senator",
}
REASON_TEXT = {
    "lost_general": "lost the general election",
    "lost_primary": "lost the primary",
    "term_limited": "term-limited",
    "did_not_run": "did not run again",
    "resigned": "resigned",
    "removed": "removed from office",
    "died": "died in office",
    "other_office": "moved to another office",
}


class TenureError(ValueError):
    pass


def set_tenure_end(
    db: Session, tenure: OfficeTenure, *, end_date: date, reason: str, source_url: str
) -> OfficeTenure:
    """Close a tenure. All three are required: a bare end date with no stated
    reason or no source would be an unsupported claim about a person."""
    if reason not in END_REASONS:
        raise TenureError(f"reason must be one of {', '.join(END_REASONS)}")
    if not source_url.strip():
        raise TenureError("a source for the reason is required")
    if end_date < tenure.start_date:
        raise TenureError("a tenure cannot end before it starts")
    tenure.end_date, tenure.end_reason, tenure.end_reason_source_url = end_date, reason, source_url.strip()
    db.flush()
    return tenure


def office_label(t: OfficeTenure) -> str:
    where = f", District {t.district}" if t.district else ""
    return f"{OFFICE_NAMES.get(t.office_type, t.office_type)}{where}"


def tenure_label(t: OfficeTenure) -> str | None:
    """'Former U.S. Representative, District 12, 2013-2027, lost the general
    election'. None for a sitting official, and for a past term whose holder
    is back in the same office (that is a continuous career, not an exit)."""
    if t.end_date is None:
        return None
    reason = f", {REASON_TEXT[t.end_reason]}" if t.end_reason else ""
    return f"Former {office_label(t)}, {t.start_date.year}-{t.end_date.year}{reason}"


def person_tenures(db: Session, person_id: uuid.UUID) -> list[OfficeTenure]:
    """Tenures of a person and of anyone a human confirmed is the same person."""
    person = db.get(Entity, person_id)
    ids = {person_id}
    other = (person.attributes or {}).get("same_person_as") if person else None
    if other:
        ids.add(uuid.UUID(other))
    return list(
        db.execute(
            select(OfficeTenure).where(OfficeTenure.person_entity_id.in_(ids)).order_by(OfficeTenure.start_date)
        ).scalars()
    )


def has_left_office(tenures: list[OfficeTenure], *, today: date) -> bool:
    """True when the person holds no office now. A tenure counts as held
    while it has no end date, or its end is still ahead. Needs at least one
    recorded tenure; with none we know nothing and say nothing."""
    if not tenures:
        return False
    return not any(t.end_date is None or t.end_date > today for t in tenures)


def left_office_label(tenures: list[OfficeTenure], *, today: date) -> str | None:
    if not has_left_office(tenures, today=today):
        return None
    last = max(tenures, key=lambda t: t.end_date or date.max)
    return tenure_label(last)


def seat_changes(db: Session, *, cycle: int) -> list[dict]:
    """Seats where the certified winner is not the person who held it, for a
    human to attach a reason to (we cannot tell 'lost' from 'retired' from
    results alone). Nothing is written."""
    out = []
    winners = db.execute(
        select(ElectionWinner).where(ElectionWinner.cycle == cycle, ElectionWinner.result_status == "certified")
    ).scalars()
    for w in winners:
        office = "fl_house" if w.chamber == "house" else "fl_senate"
        held = db.execute(
            select(OfficeTenure).where(
                OfficeTenure.office_type == office, OfficeTenure.district == w.district, OfficeTenure.end_date.is_(None)
            )
        ).scalars().all()
        for t in held:
            if w.person_entity_id != t.person_entity_id:
                out.append({"tenure_id": t.id, "person_entity_id": t.person_entity_id, "seat": f"{office} {w.district}", "new_winner": w.name})
    return out
