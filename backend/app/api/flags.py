from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Claim, Entity, Flag
from app.schemas.flag import FlagCreate, FlagOut

router = APIRouter(prefix="/flags", tags=["flags"])


@router.post("", response_model=FlagOut, status_code=201)
def create_flag(payload: FlagCreate, db: Session = Depends(get_db)) -> Flag:
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
