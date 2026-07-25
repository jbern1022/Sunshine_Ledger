from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Bill, Claim, Entity, Event, Relationship
from app.schemas.bill import (
    BillDetail,
    BillListItem,
    BillListResponse,
    ClaimOut,
    NewsItemOut,
    SourceOut,
    SponsorOut,
)

router = APIRouter(prefix="/bills", tags=["bills"])


def _what_it_does(claims: list[Claim]) -> str | None:
    for claim in claims:
        if claim.claim_type == "what_it_does":
            return claim.claim_text
    return None


def _to_list_item(entity: Entity, *, primary_sponsor: str | None = None) -> BillListItem:
    bill = entity.bill
    claims = entity.claims
    source_count = len({s.source_id for c in claims for s in c.source_links})
    return BillListItem(
        entity_id=entity.id,
        bill_number=bill.bill_number,
        session=bill.session,
        chamber=bill.chamber,
        status=bill.status,
        jurisdiction_level=entity.jurisdiction_level,
        jurisdiction_name=entity.jurisdiction_name,
        geo_scope_type=bill.geo_scope_type,
        geo_scope_names=bill.geo_scope_names,
        introduced_date=bill.introduced_date,
        last_action_date=bill.last_action_date,
        what_it_does=_what_it_does(claims),
        source_count=source_count,
        full_text_url=bill.full_text_url,
        primary_sponsor=primary_sponsor,
    )


def _primary_sponsors_by_bill(db: Session, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """One batched query for a whole page of bills, rather than one query per bill."""
    if not entity_ids:
        return {}
    stmt = (
        select(Relationship.to_entity_id, Entity.name)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id.in_(entity_ids), Relationship.relationship_type == "sponsor")
    )
    result: dict[uuid.UUID, str] = {}
    for bill_entity_id, sponsor_name in db.execute(stmt).all():
        result.setdefault(bill_entity_id, sponsor_name)  # first sponsor found per bill
    return result


@router.get("", response_model=BillListResponse)
def list_bills(
    q: str | None = Query(None, description="Free-text search over bill number and title"),
    jurisdiction_name: str | None = Query(None, description="e.g. FL, Miami, Jacksonville"),
    jurisdiction_level: str | None = Query(None, description="state | city"),
    status: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> BillListResponse:
    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill")
        .options(selectinload(Entity.bill), selectinload(Entity.claims).selectinload(Claim.source_links))
    )

    if jurisdiction_name:
        stmt = stmt.where(Entity.jurisdiction_name == jurisdiction_name)
    if jurisdiction_level:
        stmt = stmt.where(Entity.jurisdiction_level == jurisdiction_level)
    if status:
        stmt = stmt.where(Bill.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Entity.name.ilike(like), Bill.bill_number.ilike(like)))

    total = len(db.execute(stmt).scalars().all())
    stmt = stmt.order_by(Bill.last_action_date.desc().nulls_last()).offset(offset).limit(limit)
    entities = db.execute(stmt).scalars().all()

    sponsors_by_bill = _primary_sponsors_by_bill(db, [e.id for e in entities])
    items = [_to_list_item(e, primary_sponsor=sponsors_by_bill.get(e.id)) for e in entities]

    return BillListResponse(total=total, items=items)


@router.get("/{entity_id}", response_model=BillDetail)
def get_bill(entity_id: uuid.UUID, db: Session = Depends(get_db)) -> BillDetail:
    stmt = (
        select(Entity)
        .where(Entity.id == entity_id, Entity.entity_type == "bill")
        .options(
            selectinload(Entity.bill),
            selectinload(Entity.claims).selectinload(Claim.source_links),
            selectinload(Entity.events).selectinload(Event.source),
        )
    )
    entity = db.execute(stmt).scalar_one_or_none()
    if entity is None or entity.bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")

    bill = entity.bill

    claims_out = [
        ClaimOut(
            id=c.id,
            claim_type=c.claim_type,
            claim_text=c.claim_text,
            generated_by=c.generated_by,
            source_count=len(c.source_links),
            sources=[SourceOut.model_validate(link.source) for link in c.source_links],
        )
        for c in entity.claims
    ]

    sponsor_stmt = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity_id, Relationship.relationship_type.in_(["sponsor", "co_sponsor"]))
    )
    sponsors_out = [
        SponsorOut(entity_id=e.id, name=e.name, relationship_type=r.relationship_type)
        for r, e in db.execute(sponsor_stmt).all()
    ]
    primary_sponsor = next((s.name for s in sponsors_out if s.relationship_type == "sponsor"), None)
    list_item = _to_list_item(entity, primary_sponsor=primary_sponsor)

    news_out = [
        NewsItemOut(id=e.id, title=e.title, url=e.source.url, publisher=e.source.publisher, published_date=e.event_date)
        for e in entity.events
        if e.event_type == "news_mention" and e.source is not None
    ]

    return BillDetail(
        **list_item.model_dump(),
        last_action=bill.last_action,
        sponsors=sponsors_out,
        claims=claims_out,
        news=news_out,
    )
