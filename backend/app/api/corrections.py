"""Public corrections log, corrections not started by a challenge, and
right-of-reply responses (Notion correction-process spec, agreed 2026-10-01).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.flags import _check_target, record_correction
from app.auth import require_admin
from app.db import get_db
from app.models import Bill, CorrectionRecord, Entity, Flag, Response
from app.schemas.flag import CorrectionCreate, CorrectionLogOut, CorrectionOut, DisputeOut, ResponseCreate, ResponseOut

router = APIRouter(tags=["corrections"])


@router.get("/corrections", response_model=list[CorrectionLogOut])
def list_corrections(
    severity: str = Query("material", pattern="^(material|critical|all)$"),
    change_type: str | None = Query(None, pattern="^(update|correction|clarification|retraction|source_correction)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[CorrectionLogOut]:
    """The site-wide corrections log, newest first. Material and Critical by
    default (`severity=critical` narrows to Critical); `severity=all`
    includes Minor fixes too (each bill page lists all of its own).
    `change_type` narrows to one kind of change."""
    stmt = (
        select(CorrectionRecord, Bill.bill_number, Entity.name)
        .join(Entity, Entity.id == CorrectionRecord.bill_entity_id)
        .outerjoin(Bill, Bill.entity_id == CorrectionRecord.bill_entity_id)
        .order_by(CorrectionRecord.decided_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if severity == "material":
        stmt = stmt.where(CorrectionRecord.severity.in_(("material", "critical")))
    elif severity == "critical":
        stmt = stmt.where(CorrectionRecord.severity == "critical")
    if change_type:
        stmt = stmt.where(CorrectionRecord.change_type == change_type)
    return [
        CorrectionLogOut.model_validate(record).model_copy(update={"bill_number": number, "bill_name": name})
        for record, number, name in db.execute(stmt)
    ]


@router.post("/corrections/admin", response_model=CorrectionOut, status_code=201)
def create_correction(
    payload: CorrectionCreate, db: Session = Depends(get_db), admin: str = Depends(require_admin)
) -> CorrectionRecord:
    """Record a correction found by internal review, a source's own change,
    or a methodology change -- anything not started by a public challenge."""
    bill = db.get(Entity, payload.bill_entity_id)
    if bill is None or bill.entity_type != "bill":
        raise HTTPException(status_code=404, detail="Bill not found")
    _check_target(db, payload.bill_entity_id, payload.object_type, payload.object_id)
    record = record_correction(
        db, bill_entity_id=payload.bill_entity_id, object_type=payload.object_type, object_id=payload.object_id,
        fields=payload, trigger=payload.trigger, flag_id=None, admin=admin,
    )
    db.commit()
    db.refresh(record)
    return record


@router.post("/responses/admin", response_model=ResponseOut, status_code=201)
def create_response(
    payload: ResponseCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
) -> Response:
    """Publish a verified response. Only after identity was confirmed through
    the contact on the responder's official filing (decision 3)."""
    bill = db.get(Entity, payload.bill_entity_id)
    if bill is None or bill.entity_type != "bill":
        raise HTTPException(status_code=404, detail="Bill not found")
    _check_target(db, payload.bill_entity_id, payload.object_type, payload.object_id)
    previous = None
    if payload.supersedes_id:
        previous = db.get(Response, payload.supersedes_id)
        if previous is None or previous.bill_entity_id != payload.bill_entity_id:
            raise HTTPException(status_code=404, detail="Response to supersede not found on this bill")
    response = Response(
        bill_entity_id=payload.bill_entity_id,
        object_type=payload.object_type,
        object_id=payload.object_id,
        responder_name=payload.responder_name,
        responder_role=payload.responder_role,
        text=payload.text,
        full_text_url=str(payload.full_text_url) if payload.full_text_url else None,
        verified_via=payload.verified_via,
        received_at=payload.received_at,
    )
    db.add(response)
    db.flush()
    if previous is not None:
        previous.superseded_by_id = response.id  # kept, marked superseded
    db.commit()
    db.refresh(response)
    return response


def bill_accountability(db: Session, bill_entity_id) -> tuple[list[DisputeOut], list[CorrectionOut], list[ResponseOut]]:
    """What the bill page shows: open disputes (labelled, never hidden),
    every correction for this bill (all severities, oldest first, so the
    history reads in order), and all responses including superseded ones."""
    disputes = [
        DisputeOut(
            flag_id=f.id, object_type=f.object_type, object_id=f.object_id,
            category=f.category, severity=f.severity, disputed_since=f.disputed_since,
        )
        for f in db.execute(
            select(Flag).where(Flag.bill_entity_id == bill_entity_id, Flag.disputed_since.is_not(None))
            .order_by(Flag.disputed_since)
        ).scalars()
    ]
    corrections = [
        CorrectionOut.model_validate(c)
        for c in db.execute(
            select(CorrectionRecord).where(CorrectionRecord.bill_entity_id == bill_entity_id)
            .order_by(CorrectionRecord.decided_at)
        ).scalars()
    ]
    responses = [
        ResponseOut.model_validate(r)
        for r in db.execute(
            select(Response).where(Response.bill_entity_id == bill_entity_id).order_by(Response.received_at)
        ).scalars()
    ]
    return disputes, corrections, responses
