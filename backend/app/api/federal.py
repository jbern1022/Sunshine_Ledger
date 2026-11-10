"""Federal bills: the Florida places their text names."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.federal.places import METHOD_VERSION
from app.models import Bill, Entity, FederalBillText, FederalPlaceFinding

router = APIRouter(prefix="/bills", tags=["federal"])

LABEL = "Automatically found in the bill text, not yet reviewed by a person."
NOT_COVERED = (
    "Only places the text names are listed. Earmark tables in appropriations reports, places given without a state, "
    "and anything in an image are not covered, so an empty list does not mean Florida is unaffected."
)


@router.get("/{entity_id}/florida-places")
def florida_places(entity_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Florida places named in the latest stored text of a federal bill,
    each with the sentence it appears in, copied exactly."""
    row = db.execute(
        select(Entity, Bill).join(Bill, Bill.entity_id == Entity.id).where(Entity.id == entity_id, Entity.entity_type == "bill")
    ).first()
    if row is None or row[1].source_system != "congress":
        raise HTTPException(status_code=404, detail="Not a federal bill")
    text = db.execute(
        select(FederalBillText).where(FederalBillText.bill_entity_id == entity_id)
        .order_by(FederalBillText.version_date.desc().nulls_last(), FederalBillText.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if text is None:
        return {"label": LABEL, "not_covered": NOT_COVERED, "text_version": None, "findings": []}
    findings = db.execute(
        select(FederalPlaceFinding).where(FederalPlaceFinding.text_id == text.id).order_by(FederalPlaceFinding.char_start)
    ).scalars().all()
    return {
        "label": LABEL,
        "not_covered": NOT_COVERED,
        "method_version": METHOD_VERSION,
        "text_version": {"type": text.version_type, "date": text.version_date, "source_url": text.source_url},
        "findings": [
            {"kind": f.kind, "name": f.matched_term, "counties": f.counties, "section": f.section, "quote": f.quote_text}
            for f in findings
        ],
    }
