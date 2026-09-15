from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db import get_db
from app.models import Bill, BillTag, Claim, DemographicOverlay, Entity, Event, Relationship, Tag
from app.pipeline.topic_tagging import set_bill_tag_active
from app.schemas.bill import (
    BillDetail,
    BillListItem,
    BillListResponse,
    BillTagUpdate,
    ClaimOut,
    DemographicMetricOut,
    DemographicOverlayOut,
    IndividualVoteOut,
    NewsItemOut,
    RollCallOut,
    SourceOut,
    SponsorOut,
    StatusCount,
    TagCount,
    TagOut,
)

router = APIRouter(prefix="/bills", tags=["bills"])


def _what_it_does(claims: list[Claim]) -> str | None:
    for claim in claims:
        if claim.claim_type == "what_it_does":
            return claim.claim_text
    return None


def _to_list_item(
    entity: Entity, *, primary_sponsor: str | None = None, tags: list[TagOut] | None = None
) -> BillListItem:
    bill = entity.bill
    claims = entity.claims
    source_count = len({s.source_id for c in claims for s in c.source_links})
    return BillListItem(
        entity_id=entity.id,
        bill_number=bill.bill_number,
        name=entity.name,
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
        tags=tags or [],
    )


def _tag_out(bill_tag: BillTag, tag: Tag) -> TagOut:
    return TagOut(
        bill_tag_id=bill_tag.id,
        slug=tag.slug,
        label=tag.label,
        tag_source=bill_tag.tag_source,
        active=bill_tag.active,
    )


def _active_tags_by_bill(db: Session, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[TagOut]]:
    """One batched query for a whole page of bills, rather than one query per
    bill. Only active (non-hidden) badges are returned -- callers rendering
    a bill's public badges should never see a hidden one."""
    if not entity_ids:
        return {}
    stmt = (
        select(BillTag, Tag)
        .join(Tag, Tag.id == BillTag.tag_id)
        .where(BillTag.bill_entity_id.in_(entity_ids), BillTag.active.is_(True))
    )
    result: dict[uuid.UUID, list[TagOut]] = {}
    for bill_tag, tag in db.execute(stmt).all():
        result.setdefault(bill_tag.bill_entity_id, []).append(_tag_out(bill_tag, tag))
    return result


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
    geo_scope_name: str | None = Query(None, description="e.g. 'Miami-Dade County' -- matches Bill.geo_scope_names"),
    tag: str | None = Query(None, description="Tag slug, e.g. 'housing' -- matches bills with that active badge"),
    sponsor_entity_id: uuid.UUID | None = Query(
        None, description="Only bills sponsored or co-sponsored by this legislator entity"
    ),
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
    if geo_scope_name:
        stmt = stmt.where(Bill.geo_scope_names.any(geo_scope_name))
    if tag:
        stmt = stmt.where(
            Entity.id.in_(
                select(BillTag.bill_entity_id)
                .join(Tag, Tag.id == BillTag.tag_id)
                .where(Tag.slug == tag, BillTag.active.is_(True))
            )
        )
    if sponsor_entity_id:
        sponsored_bill_ids = select(Relationship.to_entity_id).where(
            Relationship.from_entity_id == sponsor_entity_id,
            Relationship.relationship_type.in_(["sponsor", "co_sponsor"]),
        )
        stmt = stmt.where(Entity.id.in_(sponsored_bill_ids))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Entity.name.ilike(like), Bill.bill_number.ilike(like)))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(Bill.last_action_date.desc().nulls_last()).offset(offset).limit(limit)
    entities = db.execute(stmt).scalars().all()

    sponsors_by_bill = _primary_sponsors_by_bill(db, [e.id for e in entities])
    tags_by_bill = _active_tags_by_bill(db, [e.id for e in entities])
    items = [
        _to_list_item(e, primary_sponsor=sponsors_by_bill.get(e.id), tags=tags_by_bill.get(e.id))
        for e in entities
    ]

    return BillListResponse(total=total, items=items)


# Declared before /{entity_id} for the same route-ordering reason as /statuses.
@router.get("/tags", response_model=list[TagCount])
def list_tags(db: Session = Depends(get_db)) -> list[TagCount]:
    """Active badge categories with counts of (active-tagged) bills carrying
    each, for building a filter UI. Only active Tags are listed -- a
    deactivated badge category shouldn't appear as a filter option."""
    stmt = (
        select(Tag.slug, Tag.label, func.count(BillTag.id).label("n"))
        .join(BillTag, BillTag.tag_id == Tag.id)
        .where(Tag.active.is_(True), BillTag.active.is_(True))
        .group_by(Tag.slug, Tag.label)
        .order_by(func.count(BillTag.id).desc(), Tag.label)
    )
    return [TagCount(slug=slug, label=label, count=n) for slug, label, n in db.execute(stmt).all()]


@router.patch("/tags/{bill_tag_id}", response_model=TagOut)
def update_bill_tag(
    bill_tag_id: uuid.UUID,
    body: BillTagUpdate,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
) -> TagOut:
    """Toggle one badge's visibility on a bill (hide/reactivate). Admin-only,
    same as the flag-review endpoints in app/api/flags.py -- this controls
    what badge is publicly shown on a bill, not a read-only action. Logs a
    tag_hidden/tag_reactivated Event; never deletes the assignment."""
    try:
        bill_tag = set_bill_tag_active(db, bill_tag_id, active=body.active)
    except ValueError:
        raise HTTPException(status_code=404, detail="Bill tag not found")

    return _tag_out(bill_tag, bill_tag.tag)


# Declared before /{entity_id}: FastAPI matches routes in definition order,
# so a dynamic path defined first would swallow "/bills/statuses" and try to
# parse "statuses" as a UUID.
@router.get("/statuses", response_model=list[StatusCount])
def list_statuses(
    jurisdiction_name: str | None = Query(None, description="Scope counts to one jurisdiction"),
    db: Session = Depends(get_db),
) -> list[StatusCount]:
    """Distinct bill statuses with counts, for building a filter.

    Driven by what's actually in the data rather than a hardcoded list. The
    three sources use different vocabularies -- LegiScan has
    Introduced/Engrossed/Passed/Vetoed/Failed, Legistar adds Enacted and
    In Committee, iQM2 has its own ("Recommended Approval with Conditions")
    -- so any fixed list would drift out of step with reality.

    Ordered by count so the statuses that describe most bills come first;
    the long tail of one-off municipal statuses sorts to the bottom rather
    than crowding the top of a dropdown.
    """
    stmt = (
        select(Bill.status, func.count().label("n"))
        .join(Entity, Entity.id == Bill.entity_id)
        .where(Entity.entity_type == "bill", Bill.status.isnot(None))
        .group_by(Bill.status)
        .order_by(func.count().desc(), Bill.status)
    )
    if jurisdiction_name:
        stmt = stmt.where(Entity.jurisdiction_name == jurisdiction_name)

    return [StatusCount(status=status, count=n) for status, n in db.execute(stmt).all()]


def _bill_geography(db: Session, entity: Entity, bill: Bill) -> tuple[str, str] | None:
    """Which geography a bill's demographic overlay should be keyed to.
    Local bills already carry a real county (geo_scope_names); state bills
    have no inherent geography of their own, so this uses the primary
    sponsor's district instead -- same logic as the district-sponsorship
    map (app/api/map.py). Returns None when neither is resolvable (e.g. a
    state bill with no primary sponsor on file)."""
    if entity.jurisdiction_level == "city":
        if bill.geo_scope_names:
            return "county", bill.geo_scope_names[0]
        return None

    sponsor = db.execute(
        select(Entity)
        .join(Relationship, Relationship.from_entity_id == Entity.id)
        .where(Relationship.to_entity_id == entity.id, Relationship.relationship_type == "sponsor")
    ).scalars().first()
    district = (sponsor.attributes or {}).get("district") if sponsor else None
    if not district:
        return None
    return "district", district


def _demographic_overlays_for_bill(
    db: Session, entity: Entity, bill: Bill, tags: list[TagOut]
) -> list[DemographicOverlayOut]:
    """ACS/BLS context for this bill's active badges, at whatever geography
    _bill_geography resolves. A badge with no matching overlay row (either
    because it has no table mapping yet, or the geography couldn't be
    resolved) simply contributes nothing -- never an error."""
    if not tags:
        return []
    geography = _bill_geography(db, entity, bill)
    if geography is None:
        return []
    geography_type, geography_id = geography

    slugs = [t.slug for t in tags]
    overlays = db.execute(
        select(DemographicOverlay).where(
            DemographicOverlay.geography_type == geography_type,
            DemographicOverlay.geography_id == geography_id,
            DemographicOverlay.badge_slug.in_(slugs),
        )
    ).scalars().all()

    label_by_slug = {t.slug: t.label for t in tags}
    return [
        DemographicOverlayOut(
            badge_slug=o.badge_slug,
            badge_label=label_by_slug.get(o.badge_slug, o.badge_slug),
            source=o.source,
            geography_type=o.geography_type,
            geography_id=o.geography_id,
            as_of=o.as_of,
            metrics=[DemographicMetricOut(**m) for m in o.metrics],
        )
        for o in overlays
    ]


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
    tags_out = _active_tags_by_bill(db, [entity_id]).get(entity_id, [])
    list_item = _to_list_item(entity, primary_sponsor=primary_sponsor, tags=tags_out)

    news_out = [
        NewsItemOut(id=e.id, title=e.title, url=e.source.url, publisher=e.source.publisher, published_date=e.event_date)
        for e in entity.events
        if e.event_type == "news_mention" and e.source is not None
    ]

    vote_events = [e for e in entity.events if e.event_type == "vote"]
    votes_out: list[RollCallOut] = []
    if vote_events:
        roll_call_ids = [e.attributes.get("roll_call_id") for e in vote_events]
        individual_stmt = (
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(
                Relationship.to_entity_id == entity_id,
                Relationship.relationship_type == "voted",
                Relationship.attributes["roll_call_id"].as_string().in_(roll_call_ids),
            )
        )
        individual_by_roll_call: dict[str, list[IndividualVoteOut]] = {}
        for rel, person in db.execute(individual_stmt).all():
            individual_by_roll_call.setdefault(rel.attributes.get("roll_call_id"), []).append(
                IndividualVoteOut(
                    person_entity_id=person.id,
                    person_name=person.name,
                    vote=rel.attributes.get("vote", "Unknown"),
                )
            )

        for e in sorted(vote_events, key=lambda e: e.event_date):
            roll_call_id = e.attributes.get("roll_call_id")
            votes_out.append(
                RollCallOut(
                    id=e.id,
                    roll_call_id=roll_call_id,
                    chamber=e.attributes.get("chamber"),
                    description=e.title,
                    date=e.event_date,
                    yea=e.attributes.get("yea"),
                    nay=e.attributes.get("nay"),
                    nv=e.attributes.get("nv"),
                    absent=e.attributes.get("absent"),
                    total=e.attributes.get("total"),
                    passed=bool(e.attributes.get("passed")),
                    source_url=e.source.url if e.source else None,
                    votes=individual_by_roll_call.get(roll_call_id, []),
                )
            )

    return BillDetail(
        **list_item.model_dump(),
        last_action=bill.last_action,
        full_text=bill.full_text,
        sponsors=sponsors_out,
        claims=claims_out,
        news=news_out,
        votes=votes_out,
        demographic_overlays=_demographic_overlays_for_bill(db, entity, bill, tags_out),
    )
