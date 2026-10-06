"""GET /bills/{id}/impact-lens: the data the browser-side matcher needs.

Read-only and input-free. The reader's answers stay in their browser; this
returns the bill's current Who-it-affects entries, their criteria, review
state, a completeness flag, and the slice of the vocabulary the bill's
criteria use (see app.impact_lens and the Notion design).
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.impact_lens.vocabulary import (
    FLORIDA_COUNTIES, MUNICIPALITY_COUNTIES, REGISTRY, VOCABULARY_VERSION, jurisdiction_label,
)
from app.models import BillLayer, BillLayerCriteria, Entity
from app.schemas.impact_lens import (
    ImpactLensOut, LensEntryOut, LensItemOut, LensLayerOut, LensOptionOut, LensQuestionOut,
)

router = APIRouter(prefix="/bills", tags=["impact-lens"])

# The Who layer records "· first N of M entries" in its scope note when it
# kept only the first N of M.
_CAPPED = re.compile(r"first \d+ of \d+ entries")


# Every question a reader can answer must have an answer for "none of the above":
# the lists only hold what the bill mentions. The matcher treats any value that is
# not named in the criteria as matching nothing.
NONE_OF_THESE = "none_of_these"


def _with_none(options: list[LensOptionOut]) -> list[LensOptionOut]:
    return [*options, LensOptionOut(value=NONE_OF_THESE, label="None of These")]


def _title(value: str) -> str:
    return " ".join(w.capitalize() for w in value.replace("_", " ").split())


def _current_who_layer(db: Session, entity_id: uuid.UUID) -> BillLayer | None:
    return db.execute(
        select(BillLayer).where(
            BillLayer.bill_entity_id == entity_id,
            BillLayer.layer == "who_it_affects",
            BillLayer.superseded_at.is_(None),
        )
    ).scalar_one_or_none()


def _criteria_by_entry(db: Session, layer: BillLayer) -> dict[int, BillLayerCriteria]:
    """The newest row per entry at the CURRENT vocabulary version (any method
    version); rows mapped against an older vocabulary are ignored."""
    rows = db.execute(
        select(BillLayerCriteria)
        .where(BillLayerCriteria.bill_layer_id == layer.id, BillLayerCriteria.vocabulary_version == VOCABULARY_VERSION)
        .options(selectinload(BillLayerCriteria.reviews))
        .order_by(BillLayerCriteria.created_at, BillLayerCriteria.id)
    ).scalars().all()
    return {r.entry_index: r for r in rows}  # later rows overwrite earlier ones


def _used_values(criteria_rows: list[dict]) -> tuple[set[str], set[str], set[str]]:
    """(roles, jurisdiction values, property types) the criteria mention."""
    roles: set[str] = set()
    jurisdictions: set[str] = set()
    property_types: set[str] = set()
    for c in criteria_rows:
        for side in (c.get("audience"), c.get("affected")):
            if side and side.get("kind") == "attr":
                roles.update(side.get("any_of") or [])
        for t in (c.get("requires") or []) + (c.get("excludes") or []):
            if t.get("attr") == "jurisdiction":
                jurisdictions.update(t.get("values") or [])
            elif t.get("attr") == "property_type":
                property_types.update(t.get("values") or [])
    return roles, jurisdictions, property_types


def _questions(criteria_rows: list[dict]) -> list[LensQuestionOut]:
    roles, jurisdictions, property_types = _used_values(criteria_rows)
    out: list[LensQuestionOut] = []
    if roles:
        role_attr = REGISTRY["role"]
        out.append(LensQuestionOut(
            key="role", label=role_attr.label, question=role_attr.question,
            options=_with_none([LensOptionOut(value=v, label=_title(v)) for v in role_attr.values if v in roles]),
        ))
    if jurisdictions:
        out.append(LensQuestionOut(
            key="county", label="County", question="Which Florida county do you live in?",
            options=[LensOptionOut(value=c, label=jurisdiction_label(f"county:{c}")) for c in FLORIDA_COUNTIES],
        ))
        named = sorted(v.partition(":")[2] for v in jurisdictions if v.startswith("municipality:"))
        named = [n for n in named if n in MUNICIPALITY_COUNTIES]
        if named:
            # Only the places the bill names; a reader outside them picks
            # "None of These"
            out.append(LensQuestionOut(
                key="municipality", label="City, Town or Village",
                question="Do you live in one of these cities, towns or villages?",
                options=_with_none([LensOptionOut(value=n, label=n) for n in named]),
                counties={n: list(MUNICIPALITY_COUNTIES[n]) for n in named},
            ))
    if property_types:
        pt = REGISTRY["property_type"]
        out.append(LensQuestionOut(
            key="property_type", label=pt.label, question=pt.question,
            options=_with_none([LensOptionOut(value=v, label=_title(v)) for v in pt.values if v in property_types]),
        ))
    return out


@router.get("/{entity_id}/impact-lens", response_model=ImpactLensOut)
def get_impact_lens(entity_id: uuid.UUID, db: Session = Depends(get_db)) -> ImpactLensOut:
    entity = db.execute(select(Entity).where(Entity.id == entity_id, Entity.entity_type == "bill")).scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Bill not found")

    layer = _current_who_layer(db, entity_id)
    if layer is None:
        return ImpactLensOut(
            bill_entity_id=entity_id, available=False, vocabulary_version=VOCABULARY_VERSION,
            unavailable_reason="This bill has no Who it affects analysis yet.",
        )

    mapped = _criteria_by_entry(db, layer)
    entries: list[LensEntryOut] = []
    for i, item in enumerate(layer.items):
        row = mapped.get(i)
        entries.append(LensEntryOut(
            group=str(item.get("group") or ""),
            text=str(item.get("text") or ""),
            quote=str(item.get("quote") or ""),
            conditions=[LensItemOut(text=str(c.get("text") or ""), quote=str(c.get("quote") or "")) for c in item.get("conditions") or []],
            exceptions=[LensItemOut(text=str(c.get("text") or ""), quote=str(c.get("quote") or "")) for c in item.get("exceptions") or []],
            criteria=row.criteria if row else None,
            reviewed=bool(row and any(r.decision == "approved" for r in row.reviews)),
        ))

    reasons: list[str] = []
    if layer.evidence_state != "supported":
        reasons.append("The Who it affects analysis is not marked supported.")
    if _CAPPED.search(layer.scope_note or ""):
        reasons.append("The analysis lists only the first entries of a longer list.")
    if not layer.items:
        reasons.append("The analysis has no entries.")
    unmapped = sum(1 for e in entries if e.criteria is None)
    if unmapped:
        reasons.append(f"{unmapped} of {len(entries)} entries have no questions mapped yet.")

    return ImpactLensOut(
        bill_entity_id=entity_id,
        available=True,
        vocabulary_version=VOCABULARY_VERSION,
        complete=not reasons,
        incomplete_reasons=reasons,
        layer=LensLayerOut(
            id=layer.id, version=layer.version, evidence_state=layer.evidence_state,
            scope_note=layer.scope_note, method_version=layer.method_version, created_at=layer.created_at,
        ),
        entries=entries,
        questions=_questions([e.criteria for e in entries if e.criteria]),
    )
