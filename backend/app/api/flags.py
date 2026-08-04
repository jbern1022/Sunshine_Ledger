from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db import get_db
from app.models import Claim, Entity, Flag
from app.rate_limit import limiter
from app.schemas.flag import FlagAdminOut, FlagCreate, FlagOut, FlagStatusUpdate

router = APIRouter(prefix="/flags", tags=["flags"])


@router.post("", response_model=FlagOut, status_code=201)
@limiter.limit("5/minute")
def create_flag(request: Request, payload: FlagCreate, db: Session = Depends(get_db)) -> Flag:
    """Report a suspected inaccuracy (BRD 5.5). Routes to manual review only —
    there is no public listing endpoint, matching the no-open-editing MVP scope.
    """
    bill_entity = db.get(Entity, payload.bill_entity_id)
    if bill_entity is None or bill_entity.entity_type != "bill":
        raise HTTPException(status_code=404, detail="Bill not found")

    if payload.claim_id is not None:
        claim = db.execute(
            select(Claim).where(Claim.id == payload.claim_id, Claim.bill_entity_id == payload.bill_entity_id)
        ).scalar_one_or_none()
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found on this bill")

    flag = Flag(
        bill_entity_id=payload.bill_entity_id,
        claim_id=payload.claim_id,
        reason_text=payload.reason_text,
        reporter_email=payload.reporter_email,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag


@router.get("/admin", response_model=list[FlagAdminOut])
def list_flags_admin(
    status: str = Query("pending", pattern="^(pending|reviewed|dismissed|all)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
) -> list[FlagAdminOut]:
    """Admin-only: the actual review queue BRD 5.5 promises. HTTP Basic
    Auth-gated -- see app/auth.py. Defaults to pending only.
    """
    stmt = (
        select(Flag)
        .options(selectinload(Flag.bill_entity).selectinload(Entity.bill), selectinload(Flag.claim))
        .order_by(Flag.created_at.desc())
        .limit(limit)
    )
    if status != "all":
        stmt = stmt.where(Flag.status == status)

    flags = db.execute(stmt).scalars().all()
    return [
        FlagAdminOut(
            id=f.id,
            bill_entity_id=f.bill_entity_id,
            bill_number=f.bill_entity.bill.bill_number if f.bill_entity.bill else "?",
            bill_name=f.bill_entity.name,
            claim_id=f.claim_id,
            claim_text=f.claim.claim_text if f.claim else None,
            reason_text=f.reason_text,
            reporter_email=f.reporter_email,
            status=f.status,
            created_at=f.created_at,
        )
        for f in flags
    ]


@router.patch("/admin/{flag_id}", response_model=FlagOut)
def update_flag_status(
    flag_id: str,
    payload: FlagStatusUpdate,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
) -> Flag:
    """Admin-only: mark a flag reviewed or dismissed once acted on."""
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    flag.status = payload.status
    db.commit()
    db.refresh(flag)
    return flag
