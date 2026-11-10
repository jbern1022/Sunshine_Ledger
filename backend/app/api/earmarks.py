"""Florida House project-funding requests and awards (read-only)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FederalEarmark

router = APIRouter(prefix="/earmarks", tags=["federal"])

STAGE_LABELS = {
    "requested": "A member's request. Not funding: it may never be included in a bill.",
    "included": "Included in a House committee bill. Not yet law.",
    "enacted": "Funded in an enacted law.",
}
NOTE = (
    "From the House Appropriations Committee's published Community Project Funding tables and the Senate "
    "Appropriations Committee's Congressionally Directed Spending requests. Senate enacted awards are not included yet. "
    "A project can appear at more than one stage."
)


@router.get("")
def list_earmarks(
    district: str | None = Query(None, pattern=r"^CD-\d{3}$"),
    person_id: uuid.UUID | None = None,
    fiscal_year: int | None = None,
    stage: str | None = Query(None, pattern="^(requested|included|enacted)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    q = select(FederalEarmark)
    if district:
        q = q.where(FederalEarmark.district == district)
    if person_id:
        q = q.where(FederalEarmark.person_entity_id == person_id)
    if fiscal_year:
        q = q.where(FederalEarmark.fiscal_year == fiscal_year)
    if stage:
        q = q.where(FederalEarmark.stage == stage)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(
        q.order_by(FederalEarmark.fiscal_year.desc(), FederalEarmark.district, FederalEarmark.recipient, FederalEarmark.id)
        .limit(limit).offset(offset)
    ).scalars().all()
    return {
        "note": NOTE,
        "total": total,
        "items": [
            {
                "id": str(e.id), "chamber": e.chamber, "fiscal_year": e.fiscal_year, "stage": e.stage, "stage_label": STAGE_LABELS[e.stage],
                "district": e.district, "person_id": str(e.person_entity_id) if e.person_entity_id else None,
                "member": f"{e.member_first + ' ' if e.member_first else ''}{e.member_last}", "party": e.party,
                "subcommittee": e.subcommittee, "recipient": e.recipient, "description": e.description,
                "recipient_address": e.recipient_address, "amount": e.amount, "member_url": e.member_url,
                "source_url": e.source_url,
            }
            for e in rows
        ],
    }
