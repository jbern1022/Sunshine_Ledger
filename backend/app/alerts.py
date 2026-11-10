"""Watchlist alerts and digests, without sending (Todoist 6hWPfQqX443vpgCp).

Two steps, both idempotent and safe to run any number of times:

1. `generate(db)` finds events that match a user's watches and queues one `PendingAlert` per
   (user, event). Only events created AFTER the watch was added count, so following something does
   not flood the user with its history. Officials match events on bills they sponsor or co-sponsor;
   topics match events on bills carrying the topic (optionally within one jurisdiction).
2. `build_digest(db, user)` returns what is waiting, grouped by bill, and `mark_delivered` records a
   send only after the caller confirms it succeeded.

Not here, by design: sending (needs a verified sender, unsubscribe, bounce and suppression handling),
per-user digest schedules, push channels. Transactional versus marketing consent stays separate: an
alert digest for something the user chose to follow is a service message they can turn off by
unfollowing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import BillTag, Entity, Event, PendingAlert, Relationship, Tag, User, Watch

SPONSOR_TYPES = ("sponsor", "co_sponsor")


def _matching_event_ids(db: Session, w: Watch) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(event id, bill entity id) for events matching one watch and created after it."""
    q = select(Event.id, Event.entity_id).where(Event.created_at > w.created_at)
    if w.kind == "bill":
        q = q.where(Event.entity_id == uuid.UUID(w.target))
    elif w.kind == "official":
        bills = select(Relationship.to_entity_id).where(
            Relationship.from_entity_id == uuid.UUID(w.target), Relationship.relationship_type.in_(SPONSOR_TYPES)
        )
        q = q.where(Event.entity_id.in_(bills))
    else:
        tagged = (
            select(BillTag.bill_entity_id).join(Tag, Tag.id == BillTag.tag_id)
            .where(Tag.slug == w.target, BillTag.active.is_(True), Tag.active.is_(True))
        )
        if w.jurisdiction:
            tagged = tagged.join(Entity, Entity.id == BillTag.bill_entity_id).where(Entity.jurisdiction_name == w.jurisdiction)
        q = q.where(Event.entity_id.in_(tagged))
    return [(r[0], r[1]) for r in db.execute(q).all()]


def generate(db: Session) -> int:
    """Queue alerts for every active user's watches. Returns how many new rows were queued."""
    queued = 0
    rows = db.execute(
        select(Watch).join(User, User.id == Watch.user_id).where(User.status == "active").order_by(Watch.created_at)
    ).scalars().all()
    for w in rows:
        for event_id, _bill in _matching_event_ids(db, w):
            res = db.execute(
                pg_insert(PendingAlert).values(id=uuid.uuid4(), user_id=w.user_id, event_id=event_id, watch_id=w.id,
                                               created_at=datetime.now(timezone.utc))
                .on_conflict_do_nothing(constraint="uq_pending_alerts_user_event")
                .returning(PendingAlert.id)
            )
            queued += 1 if res.first() is not None else 0
    db.commit()
    return queued


@dataclass(frozen=True)
class DigestItem:
    alert_id: uuid.UUID
    bill_entity_id: uuid.UUID
    bill_name: str
    event_type: str
    event_title: str
    event_date: date
    why: str  # "You follow this bill" / "You follow <topic>" / "A bill sponsored by an official you follow"


def build_digest(db: Session, user: User) -> list[DigestItem]:
    rows = db.execute(
        select(PendingAlert, Event, Entity, Watch)
        .join(Event, Event.id == PendingAlert.event_id)
        .join(Entity, Entity.id == Event.entity_id)
        .outerjoin(Watch, Watch.id == PendingAlert.watch_id)
        .where(PendingAlert.user_id == user.id, PendingAlert.delivered_at.is_(None))
        .order_by(Entity.name, Event.event_date, Event.id)
    ).all()
    why = {"bill": "You follow this bill", "official": "A bill sponsored by an official you follow",
           "topic": "It is on a topic you follow"}
    return [
        DigestItem(a.id, e.id, e.name, ev.event_type, ev.title, ev.event_date, why.get(w.kind, "You follow this") if w else "You follow this")
        for a, ev, e, w in rows
    ]


def mark_delivered(db: Session, user: User, alert_ids: list[uuid.UUID], *, now: datetime | None = None) -> int:
    """Record a confirmed send. Only this user's rows can be marked."""
    now = now or datetime.now(timezone.utc)
    rows = db.execute(
        select(PendingAlert).where(PendingAlert.user_id == user.id, PendingAlert.id.in_(alert_ids), PendingAlert.delivered_at.is_(None))
    ).scalars().all()
    for r in rows:
        r.delivered_at = now
    db.commit()
    return len(rows)
