"""Promises: what 2026 winners said they would do, in their own words.

Everything public here is machine-collected text copied verbatim from a page
the official published, with the snapshot it came from. Nothing is a
paraphrase, nothing is scored, and no fulfillment status exists. Review is by
a sole reviewer in order of risk (flagged items first); the response says so.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.db import get_db
from app.models import ElectionWinner, OfficialSite, PromiseFlag, PromiseItem, PromiseReview, SiteSnapshot
from app.rate_limit import limiter
from app.tenures import LEFT_OFFICE_STATUS, has_left_office, person_tenures

router = APIRouter(prefix="/promises", tags=["promises"])

DISCLOSURE = (
    "These statements were collected automatically from pages the official published. "
    "The wording is copied exactly; labels shown as automated are drafts by a model. "
    "Items marked Unreviewed have not been checked by a person. Review is done by one "
    "reviewer, flagged items first. No item says whether a promise was kept."
)
PUBLIC_STATES = ("unreviewed", "flagged", "approved")
STATE_LABEL = {"unreviewed": "Unreviewed", "flagged": "Flagged - under review", "approved": "Reviewed"}


def _office_status(db: Session, w: ElectionWinner) -> str | None:
    """'Left office before outcome could be determined' when the official's
    recorded tenures have all ended. Never an 'unfulfilled' verdict."""
    if w.person_entity_id is None:
        return None
    tenures = person_tenures(db, w.person_entity_id)
    return LEFT_OFFICE_STATUS if has_left_office(tenures, today=datetime.now(timezone.utc).date()) else None


def _item_out(i: PromiseItem, db: Session | None = None) -> dict:
    snap, w = i.snapshot, i.winner
    return {
        "id": i.id,
        "quote": i.quote_text,
        "source_url": i.source_url,
        "captured_at": i.captured_at,
        "statement_date": i.statement_date,
        "review_state": i.review_state,
        "review_label": STATE_LABEL.get(i.review_state, i.review_state),
        "classification": i.reviewed_classification,
        "automated_labels": i.auto_labels if not i.reviewed_classification else {**i.auto_labels, "overridden_by_reviewer": True},
        "snapshot": {
            "id": snap.id,
            "fetched_at": snap.fetched_at,
            "content_hash": snap.content_hash,
            "internet_archive_capture": snap.from_archive_timestamp,
        },
        "official": {
            "name": w.name,
            "chamber": w.chamber,
            "district": w.district,
            "party": w.party,
            "result_status": w.result_status,
            "office_status": _office_status(db, w) if db is not None else None,
        },
    }


def _base_stmt():
    return (
        select(PromiseItem)
        .options(joinedload(PromiseItem.snapshot), joinedload(PromiseItem.winner))
    )


@router.get("")
def list_promises(
    chamber: Literal["house", "senate"] | None = None,
    district: int | None = Query(None, ge=1),
    topic: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    stmt = _base_stmt().join(ElectionWinner, ElectionWinner.id == PromiseItem.winner_id).where(
        PromiseItem.review_state.in_(PUBLIC_STATES)
    )
    if chamber:
        stmt = stmt.where(ElectionWinner.chamber == chamber)
    if district:
        stmt = stmt.where(ElectionWinner.district == district)
    if topic:
        stmt = stmt.where(PromiseItem.auto_labels["topics"].contains([topic]))
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(ElectionWinner.chamber, ElectionWinner.district, PromiseItem.char_start).limit(limit).offset(offset)
    ).unique().scalars().all()
    return {"disclosure": DISCLOSURE, "total": total, "items": [_item_out(i, db) for i in rows]}


@router.get("/coverage")
def coverage(db: Session = Depends(get_db)) -> dict:
    """What is and is not covered: winners without a site, sites we could not
    read, and how many statements are in each review state."""
    winners = db.execute(select(func.count()).select_from(ElectionWinner)).scalar_one()
    with_site = db.execute(select(func.count(func.distinct(OfficialSite.winner_id)))).scalar_one()
    with_snap = db.execute(
        select(func.count(func.distinct(OfficialSite.winner_id)))
        .join(SiteSnapshot, SiteSnapshot.site_id == OfficialSite.id)
        .where(SiteSnapshot.status == "ok")
    ).scalar_one()
    site_status = dict(db.execute(select(OfficialSite.status, func.count()).group_by(OfficialSite.status)).all())
    states = dict(db.execute(select(PromiseItem.review_state, func.count()).group_by(PromiseItem.review_state)).all())
    return {
        "winners": winners,
        "winners_with_a_site": with_site,
        "winners_without_a_site": winners - with_site,
        "winners_with_a_snapshot": with_snap,
        "sites_by_status": site_status,
        "statements_by_review_state": states,
        "disclosure": DISCLOSURE,
    }


@router.get("/admin/queue")
def review_queue(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Highest risk first: flagged (most flags first), then statements the
    model drafted as commitments, then everything else unreviewed, oldest first."""
    risk = case(
        (PromiseItem.review_state == "flagged", 0),
        (PromiseItem.auto_labels["commitment_type"].as_string() == "commitment", 1),
        else_=2,
    )
    stmt = _base_stmt().where(PromiseItem.review_state.in_(("flagged", "unreviewed")))
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(risk, PromiseItem.flag_count.desc(), PromiseItem.created_at).limit(limit).offset(offset)
    ).unique().scalars().all()
    out = []
    for i in rows:
        d = _item_out(i, db)
        d["flag_count"] = i.flag_count
        d["open_flags"] = [f.reason_text for f in i.flags if f.resolved_at is None]
        out.append(d)
    return {"total": total, "items": out}


class FlagIn(BaseModel):
    reason_text: str = Field(min_length=5, max_length=2000)
    reporter_email: str | None = Field(default=None, max_length=320)


@router.get("/{item_id}")
def get_promise(item_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    item = db.execute(_base_stmt().where(PromiseItem.id == item_id)).unique().scalar_one_or_none()
    if item is None or item.review_state not in PUBLIC_STATES:
        raise HTTPException(status_code=404, detail="Not found")
    return {"disclosure": DISCLOSURE, **_item_out(item, db)}


@router.post("/{item_id}/flag", status_code=201)
@limiter.limit("5/minute")
def flag_promise(request: Request, item_id: uuid.UUID, payload: FlagIn, db: Session = Depends(get_db)) -> dict:
    item = db.get(PromiseItem, item_id)
    if item is None or item.review_state not in PUBLIC_STATES:
        raise HTTPException(status_code=404, detail="Not found")
    db.add(PromiseFlag(item_id=item.id, reason_text=payload.reason_text, reporter_email=payload.reporter_email))
    item.flag_count += 1
    item.review_state = "flagged"
    db.commit()
    return {"id": item.id, "review_state": item.review_state, "flag_count": item.flag_count}


Action = Literal["approve", "reject", "not_a_commitment", "reclassify", "unflag"]
_NEXT_STATE = {"approve": "approved", "reject": "rejected", "not_a_commitment": "not_a_commitment", "unflag": "unreviewed"}


class ReviewIn(BaseModel):
    action: Action
    note: str | None = Field(default=None, max_length=2000)
    classification: str | None = Field(default=None, max_length=40)


@router.post("/admin/{item_id}/review")
def review_item(
    item_id: uuid.UUID,
    payload: ReviewIn,
    reviewer: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Record a reviewer action. Every action is kept (who, when, why); an
    item's history is never rewritten. Open flags are closed by any action
    that decides the item."""
    item = db.get(PromiseItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.action == "reclassify" and not payload.classification:
        raise HTTPException(status_code=422, detail="classification is required to reclassify")
    from_state = item.review_state
    to_state = _NEXT_STATE.get(payload.action, from_state)
    if payload.action == "reclassify":
        item.reviewed_classification = payload.classification
    if payload.action == "approve" and payload.classification:
        item.reviewed_classification = payload.classification
    item.review_state = to_state
    now = datetime.now(timezone.utc)
    if payload.action != "reclassify":
        for f in item.flags:
            if f.resolved_at is None:
                f.resolved_at = now
    db.add(
        PromiseReview(
            item_id=item.id, action=payload.action, reviewer=reviewer, note=payload.note,
            classification=payload.classification, from_state=from_state, to_state=to_state,
        )
    )
    db.commit()
    return {"id": item.id, "review_state": item.review_state, "classification": item.reviewed_classification}
