from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.api.bills import _active_tags_by_bill
from app.models import Bill, Claim, Entity, Event, Relationship, Source
from app.schemas.person import (
    BillTopic,
    PersonBillItem,
    PersonDetail,
    PersonListItem,
    PersonListResponse,
    PersonVoteItem,
)

router = APIRouter(prefix="/people", tags=["people"])

SPONSOR_TYPES = ("sponsor", "co_sponsor")


# Florida floor roll calls read "House: Third Reading RCS#662"; every other
# roll call is named for the committee that held it (checked 2026-09-26:
# 800 floor, the rest committees).
_FLOOR_VOTE = re.compile(r"(Third|Second) Reading|RCS#", re.IGNORECASE)


def _attrs(entity: Entity) -> dict:
    return entity.attributes or {}


def _is_committee(entity: Entity) -> bool:
    return bool(_attrs(entity).get("committee"))


def _topics(tags_by_bill: dict, bill_id: uuid.UUID) -> list[BillTopic]:
    return [BillTopic(slug=t.slug, label=t.label) for t in tags_by_bill.get(bill_id, [])]


@router.get("", response_model=PersonListResponse)
def list_people(
    q: str | None = Query(None, description="Free-text search over name and district"),
    jurisdiction_name: str | None = Query(None, description="e.g. FL"),
    kind: str | None = Query(None, pattern="^(legislator|committee)$", description="legislator | committee"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> PersonListResponse:
    """Legislators who sponsor tracked bills.

    Sponsorship counts are a plain fact drawn from the bill records, not a
    ranking or a judgement -- BRD 5.8's "no scoring" constraint applies to
    election context, but the same neutrality principle is why this returns
    counts and lets the reader draw conclusions.
    """
    sponsored = (
        select(
            Relationship.from_entity_id.label("person_id"),
            func.count(func.distinct(Relationship.to_entity_id)).label("n"),
        )
        .where(Relationship.relationship_type.in_(SPONSOR_TYPES))
        .group_by(Relationship.from_entity_id)
        .subquery()
    )

    stmt = (
        select(Entity, func.coalesce(sponsored.c.n, 0))
        .join(sponsored, sponsored.c.person_id == Entity.id)
        .where(Entity.entity_type == "person")
    )

    if jurisdiction_name:
        stmt = stmt.where(Entity.jurisdiction_name == jurisdiction_name)
    if kind == "committee":
        stmt = stmt.where(Entity.attributes.has_key("committee"))
    elif kind == "legislator":
        stmt = stmt.where(~Entity.attributes.has_key("committee"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Entity.name.ilike(like), Entity.attributes["district"].as_string().ilike(like))
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(func.coalesce(sponsored.c.n, 0).desc(), Entity.name).offset(offset).limit(limit)
    ).all()

    return PersonListResponse(
        total=total,
        items=[
            PersonListItem(
                entity_id=e.id,
                name=e.name,
                district=_attrs(e).get("district"),
                role=_attrs(e).get("role"),
                party=_attrs(e).get("party"),
                jurisdiction_name=e.jurisdiction_name,
                sponsored_count=n,
                is_committee=_is_committee(e),
            )
            for e, n in rows
        ],
    )


@router.get("/{entity_id}", response_model=PersonDetail)
def get_person(entity_id: uuid.UUID, db: Session = Depends(get_db)) -> PersonDetail:
    """One legislator and every tracked bill they're attached to."""
    person = db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.entity_type == "person")
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    what_it_does = (
        select(Claim.bill_entity_id, func.min(Claim.claim_text).label("text"))
        .where(Claim.claim_type == "what_it_does")
        .group_by(Claim.bill_entity_id)
        .subquery()
    )

    rows = db.execute(
        select(Entity, Bill, Relationship.relationship_type, what_it_does.c.text)
        .join(Bill, Bill.entity_id == Entity.id)
        .join(Relationship, Relationship.to_entity_id == Entity.id)
        .outerjoin(what_it_does, what_it_does.c.bill_entity_id == Entity.id)
        .where(
            Relationship.from_entity_id == person.id,
            Relationship.relationship_type.in_(SPONSOR_TYPES),
        )
        .order_by(Bill.last_action_date.desc().nulls_last())
    ).all()

    bills = [
        PersonBillItem(
            entity_id=bill_entity.id,
            bill_number=bill.bill_number,
            name=bill_entity.name,
            status=bill.status,
            relationship_type=rel_type,
            last_action_date=bill.last_action_date.isoformat() if bill.last_action_date else None,
            what_it_does=text,
        )
        for bill_entity, bill, rel_type, text in rows
    ]

    # The roll call's own date/description live on a `vote` Event attached
    # to the bill, keyed by the same roll_call_id the `voted` Relationship
    # carries -- joined here rather than duplicated onto the Relationship.
    vote_event = aliased(Event)
    vote_source = aliased(Source)
    vote_rows = db.execute(
        select(Bill, Entity, Relationship.attributes, vote_event.event_date, vote_event.title, vote_source.url)
        .join(Entity, Entity.id == Bill.entity_id)
        .join(Relationship, Relationship.to_entity_id == Entity.id)
        .outerjoin(
            vote_event,
            (vote_event.entity_id == Entity.id)
            & (vote_event.event_type == "vote")
            & (
                vote_event.attributes["roll_call_id"].as_string()
                == Relationship.attributes["roll_call_id"].as_string()
            ),
        )
        .outerjoin(vote_source, vote_source.id == vote_event.source_id)
        .where(Relationship.from_entity_id == person.id, Relationship.relationship_type == "voted")
        .order_by(vote_event.event_date.desc().nulls_last())
    ).all()

    tags_by_bill = _active_tags_by_bill(
        db, list({b.entity_id for b in bills} | {bill_entity.id for _, bill_entity, *_ in vote_rows})
    )
    for b in bills:
        b.tags = _topics(tags_by_bill, b.entity_id)

    votes = [
        PersonVoteItem(
            entity_id=bill_entity.id,
            bill_number=bill.bill_number,
            bill_name=bill_entity.name,
            vote=rel_attrs.get("vote", "Unknown"),
            roll_call_description=event_title,
            date=event_date.isoformat() if event_date else None,
            roll_call_id=rel_attrs.get("roll_call_id"),
            stage="floor" if event_title and _FLOOR_VOTE.search(event_title) else "committee",
            source_url=source_url or None,
            tags=_topics(tags_by_bill, bill_entity.id),
        )
        for bill, bill_entity, rel_attrs, event_date, event_title, source_url in vote_rows
    ]

    return PersonDetail(
        entity_id=person.id,
        name=person.name,
        district=_attrs(person).get("district"),
        role=_attrs(person).get("role"),
        party=_attrs(person).get("party"),
        jurisdiction_name=person.jurisdiction_name,
        # Distinct bills, since a legislator can appear as both sponsor and
        # co-sponsor on the same bill.
        sponsored_count=len({b.entity_id for b in bills}),
        is_committee=_is_committee(person),
        bills=bills,
        votes=votes,
    )
