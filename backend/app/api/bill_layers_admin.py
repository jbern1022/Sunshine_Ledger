"""Admin-only human review of bill layer versions.

Review is recorded as an append-only BillLayerReview row -- never an edit
to the reviewed BillLayer. Only the current version can be reviewed: a
superseded one is history. No rejection path in this version; problems go
through a flag and the corrections process.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db import get_db
from app.models import BillLayer, BillLayerReview, BillLayerSource, Entity

router = APIRouter(prefix="/bill-layers/admin", tags=["bill-layers-admin"])


def review_state(layer: BillLayer) -> tuple[str, datetime | None]:
    approvals = [r for r in layer.reviews if r.decision == "approved"]
    if not approvals:
        return "not_reviewed", None
    return "reviewed", min(r.created_at for r in approvals)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^approved$")
    note: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    bill_layer_id: uuid.UUID
    decision: str
    created_at: datetime


class UnreviewedSourceOut(BaseModel):
    url: str
    source_type: str


class UnreviewedOut(BaseModel):
    id: uuid.UUID
    bill_entity_id: uuid.UUID
    bill_number: str
    layer: str
    origin: str
    version: int
    evidence_state: str
    scope_note: str
    items: list[dict]
    created_at: datetime
    sources: list[UnreviewedSourceOut]


@router.get("/unreviewed", response_model=list[UnreviewedOut])
def list_unreviewed(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
) -> list[UnreviewedOut]:
    approved = select(BillLayerReview.bill_layer_id).where(BillLayerReview.decision == "approved")
    rows = db.execute(
        select(BillLayer, Entity)
        .join(Entity, Entity.id == BillLayer.bill_entity_id)
        .where(BillLayer.superseded_at.is_(None), BillLayer.id.not_in(approved))
        .options(selectinload(BillLayer.source_links).selectinload(BillLayerSource.source), selectinload(Entity.bill))
        .order_by(BillLayer.created_at)
        .limit(limit)
    ).all()
    return [
        UnreviewedOut(
            id=layer.id, bill_entity_id=layer.bill_entity_id,
            bill_number=entity.bill.bill_number if entity.bill else "?",
            layer=layer.layer, origin=layer.origin, version=layer.version,
            evidence_state=layer.evidence_state, scope_note=layer.scope_note, items=layer.items,
            created_at=layer.created_at,
            sources=[UnreviewedSourceOut(url=l.source.url, source_type=l.source.source_type) for l in layer.source_links],
        )
        for layer, entity in rows
    ]


@router.post("/{layer_id}/review", response_model=ReviewOut, status_code=201)
def review_layer(
    layer_id: uuid.UUID,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    admin: str = Depends(require_admin),
) -> ReviewOut:
    layer = db.execute(
        select(BillLayer).where(BillLayer.id == layer_id).options(selectinload(BillLayer.reviews))
    ).scalar_one_or_none()
    if layer is None:
        raise HTTPException(status_code=404, detail="Bill layer not found")
    if layer.superseded_at is not None:
        raise HTTPException(status_code=409, detail="This version is superseded; review the current version")
    if review_state(layer)[0] == "reviewed":
        raise HTTPException(status_code=409, detail="Already approved")
    review = BillLayerReview(bill_layer_id=layer.id, decision=payload.decision, reviewer=admin, note=payload.note)
    db.add(review)
    db.commit()
    db.refresh(review)
    return ReviewOut(id=review.id, bill_layer_id=review.bill_layer_id, decision=review.decision, created_at=review.created_at)
