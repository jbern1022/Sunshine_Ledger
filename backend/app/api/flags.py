"""Challenges ("flags") and the admin side of the correction process.

Notion spec "Correction, Dispute & Right-of-Reply Process", decisions agreed
2026-10-01: review targets (Critical: triage 2 days, decide 7; Material: 7
and 30), disputed statements stay visible with a label and are never
hidden, and every correction stays visible with its evidence.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db import get_db
from app.models import BillLayer, Claim, CorrectionRecord, Entity, Event, Flag
from app.rate_limit import limiter
from app.schemas.flag import (
    FlagAdminOut,
    FlagCreate,
    FlagDecision,
    FlagOut,
    FlagTriage,
)

router = APIRouter(prefix="/flags", tags=["flags"])


def _check_target(db: Session, bill_id, object_type: str, object_id) -> None:
    """The challenged object must exist and belong to this bill."""
    if object_type in ("bill", "page_copy"):
        return
    if object_id is None:
        raise HTTPException(status_code=422, detail=f"object_id is required for {object_type}")
    if object_type == "claim":
        found = db.execute(select(Claim.id).where(Claim.id == object_id, Claim.bill_entity_id == bill_id)).first()
    elif object_type == "bill_layer":
        found = db.execute(select(BillLayer.id).where(BillLayer.id == object_id, BillLayer.bill_entity_id == bill_id)).first()
    else:  # amendment | vote
        event_type = "AMENDED" if object_type == "amendment" else "vote"
        found = db.execute(
            select(Event.id).where(Event.id == object_id, Event.entity_id == bill_id, Event.event_type == event_type)
        ).first()
    if not found:
        raise HTTPException(status_code=404, detail=f"{object_type} not found on this bill")


@router.post("", response_model=FlagOut, status_code=201)
@limiter.limit("5/minute")
def create_flag(request: Request, payload: FlagCreate, db: Session = Depends(get_db)) -> Flag:
    """Challenge something on a bill page. Goes to manual review; there is
    no public listing of challenges, only of disputes and corrections."""
    bill_entity = db.get(Entity, payload.bill_entity_id)
    if bill_entity is None or bill_entity.entity_type != "bill":
        raise HTTPException(status_code=404, detail="Bill not found")

    object_type = payload.object_type or ("claim" if payload.claim_id else "bill")
    object_id = payload.object_id or (payload.claim_id if object_type == "claim" else None)
    if payload.claim_id is not None:
        _check_target(db, payload.bill_entity_id, "claim", payload.claim_id)
    _check_target(db, payload.bill_entity_id, object_type, object_id)

    flag = Flag(
        bill_entity_id=payload.bill_entity_id,
        claim_id=payload.claim_id,
        object_type=object_type,
        object_id=object_id,
        object_version=payload.object_version,
        category=payload.category,
        reason_text=payload.reason_text,
        evidence_text=payload.evidence_text,
        evidence_url=str(payload.evidence_url) if payload.evidence_url else None,
        is_named_party=payload.is_named_party,
        reporter_email=payload.reporter_email,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag


def _admin_out(f: Flag) -> FlagAdminOut:
    return FlagAdminOut(
        id=f.id,
        bill_entity_id=f.bill_entity_id,
        bill_number=f.bill_entity.bill.bill_number if f.bill_entity.bill else "?",
        bill_name=f.bill_entity.name,
        claim_id=f.claim_id,
        claim_text=f.claim.claim_text if f.claim else None,
        object_type=f.object_type,
        object_id=f.object_id,
        object_version=f.object_version,
        category=f.category,
        reason_text=f.reason_text,
        evidence_text=f.evidence_text,
        evidence_url=f.evidence_url,
        is_named_party=f.is_named_party,
        reporter_email=f.reporter_email,
        status=f.status,
        severity=f.severity,
        disputed_since=f.disputed_since,
        duplicate_of_id=f.duplicate_of_id,
        decision=f.decision,
        decision_explanation=f.decision_explanation,
        created_at=f.created_at,
        triaged_at=f.triaged_at,
        decided_at=f.decided_at,
    )


@router.get("/admin", response_model=list[FlagAdminOut])
def list_flags_admin(
    status: str = Query("open", pattern="^(open|pending|triaged|decided|dismissed|all)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
) -> list[FlagAdminOut]:
    """Admin-only review queue (HTTP Basic, app/auth.py). "open" = pending
    and triaged, the ones still needing a decision; Critical first, then
    oldest first, so the 2-day / 7-day targets surface on top."""
    stmt = (
        select(Flag)
        .options(selectinload(Flag.bill_entity).selectinload(Entity.bill), selectinload(Flag.claim))
        .limit(limit)
    )
    if status == "open":
        stmt = stmt.where(Flag.status.in_(("pending", "triaged")))
    elif status != "all":
        stmt = stmt.where(Flag.status == status)
    flags = db.execute(stmt.order_by(Flag.created_at)).scalars().all()
    flags = sorted(flags, key=lambda f: (f.severity != "critical", f.created_at))
    return [_admin_out(f) for f in flags]


def _open_flag(db: Session, flag_id: str) -> Flag:
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag


@router.post("/admin/{flag_id}/triage", response_model=FlagAdminOut)
def triage_flag(
    flag_id: str, payload: FlagTriage, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
) -> FlagAdminOut:
    flag = _open_flag(db, flag_id)
    if flag.status not in ("pending", "triaged"):
        raise HTTPException(status_code=409, detail=f"Flag is already {flag.status}")
    now = datetime.now(timezone.utc)
    if payload.dismiss or payload.duplicate_of_id:
        if payload.duplicate_of_id and db.get(Flag, payload.duplicate_of_id) is None:
            raise HTTPException(status_code=404, detail="duplicate_of flag not found")
        flag.status = "dismissed"
        flag.duplicate_of_id = payload.duplicate_of_id
        flag.disputed_since = None
        flag.decision_explanation = payload.note
        flag.resolved_at = flag.resolved_at or now  # starts the email retention clock
    else:
        if payload.severity is None:
            raise HTTPException(status_code=422, detail="severity is required unless dismissing")
        if payload.disputed and payload.severity == "minor":
            raise HTTPException(status_code=422, detail="Only material or critical challenges mark a statement disputed")
        flag.status = "triaged"
        flag.severity = payload.severity
        flag.disputed_since = (flag.disputed_since or now) if payload.disputed else None
    flag.triaged_at = flag.triaged_at or now
    db.commit()
    db.refresh(flag)
    return _admin_out(flag)


def record_correction(db: Session, *, bill_entity_id, object_type, object_id, fields, trigger, flag_id, admin) -> CorrectionRecord:
    record = CorrectionRecord(
        bill_entity_id=bill_entity_id,
        object_type=object_type,
        object_id=object_id,
        prior_version=fields.prior_version,
        current_version=fields.current_version,
        prior_text=fields.prior_text,
        current_text=fields.current_text,
        change_type=fields.change_type,
        severity=fields.severity,
        trigger=trigger,
        flag_id=flag_id,
        explanation=fields.explanation,
        evidence_links=[link.model_dump(mode="json") for link in fields.evidence_links],
        origin=fields.origin,
        was_reviewed=fields.was_reviewed,
        methodology_version=fields.methodology_version,
        decided_by=admin,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(record)
    return record


@router.post("/admin/{flag_id}/decide", response_model=FlagAdminOut)
def decide_flag(
    flag_id: str, payload: FlagDecision, db: Session = Depends(get_db), admin: str = Depends(require_admin)
) -> FlagAdminOut:
    flag = _open_flag(db, flag_id)
    if flag.status not in ("pending", "triaged"):
        raise HTTPException(status_code=409, detail=f"Flag is already {flag.status}")
    if payload.decision != "no_change":
        if payload.correction is None:
            raise HTTPException(status_code=422, detail="A correction record is required unless the decision is no_change")
        if payload.correction.change_type != payload.decision:
            raise HTTPException(status_code=422, detail="correction.change_type must match the decision")
        record_correction(
            db, bill_entity_id=flag.bill_entity_id, object_type=flag.object_type, object_id=flag.object_id,
            fields=payload.correction, trigger="challenge", flag_id=flag.id, admin=admin,
        )
    now = datetime.now(timezone.utc)
    flag.status = "decided"
    flag.decision = payload.decision
    flag.decision_explanation = payload.explanation
    flag.disputed_since = None
    flag.decided_at = now
    flag.resolved_at = flag.resolved_at or now
    db.commit()
    db.refresh(flag)
    return _admin_out(flag)
