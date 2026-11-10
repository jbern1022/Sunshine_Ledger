"""Watchlists: bills, officials and jurisdiction-scoped topics (Todoist 6hWPfQgc9xWJqxJG).

Storage and rules only. There are no routes yet (accounts do not exist) and no alerts (they wait on
email delivery). Every function takes the acting `User` and only ever touches that user's rows, so a
request handler cannot reach another account's list by passing a different id.

Cap: 300 entries per account (proposed in docs/ACCOUNTS_DESIGN_QUESTIONS.md; owner to confirm).
Officials are the electioneering-adjacent kind: the owner approved building them (2026-10-29) while
public release stays gated on the scoped legal review; `ENABLED_KINDS` is the switch.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Entity, Tag, User, Watch

MAX_WATCHES = 300
KINDS = ("bill", "official", "topic")
ENABLED_KINDS: frozenset[str] = frozenset(KINDS)


class WatchError(ValueError):
    """The request is not acceptable; the message is safe to show."""


def add(db: Session, user: User, kind: str, target: str, jurisdiction: str = "") -> Watch:
    if kind not in KINDS or kind not in ENABLED_KINDS:
        raise WatchError(f"you can't follow a {kind!r}")
    target = target.strip()
    jurisdiction = jurisdiction.strip()
    if jurisdiction and kind != "topic":
        raise WatchError("only topics can be limited to a jurisdiction")
    if kind == "topic":
        if db.execute(select(Tag.id).where(Tag.slug == target)).first() is None:
            raise WatchError("unknown topic")
    else:
        try:
            eid = uuid.UUID(target)
        except ValueError as exc:
            raise WatchError(f"unknown {kind}") from exc
        wanted = "bill" if kind == "bill" else "person"
        if db.execute(select(Entity.id).where(Entity.id == eid, Entity.entity_type == wanted)).first() is None:
            raise WatchError(f"unknown {kind}")
        target = str(eid)
    existing = db.execute(select(Watch).where(
        Watch.user_id == user.id, Watch.kind == kind, Watch.target == target, Watch.jurisdiction == jurisdiction
    )).scalar_one_or_none()
    if existing is not None:
        return existing  # following twice is not an error
    count = db.execute(select(func.count()).select_from(Watch).where(Watch.user_id == user.id)).scalar_one()
    if count >= MAX_WATCHES:
        raise WatchError(f"you can follow up to {MAX_WATCHES} things")
    row = Watch(user_id=user.id, kind=kind, target=target, jurisdiction=jurisdiction)
    db.add(row)
    db.commit()
    return row


def remove(db: Session, user: User, watch_id: uuid.UUID) -> bool:
    """Remove one of THIS user's watches. Another account's id is simply not found."""
    row = db.execute(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.id)).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def listing(db: Session, user: User, kind: str | None = None) -> list[Watch]:
    q = select(Watch).where(Watch.user_id == user.id).order_by(Watch.created_at, Watch.id)
    if kind:
        q = q.where(Watch.kind == kind)
    return list(db.execute(q).scalars())
