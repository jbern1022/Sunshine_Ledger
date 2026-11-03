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
from sqlalchemy.orm import Session

from app.db import get_db
from app.impact_lens.vocabulary import (
    BUSINESS, FLORIDA_COUNTIES, MUNICIPALITY_COUNTIES, PROPERTY, REGISTRY, RESIDENCE, ROLE_LOCATIONS,
    VOCABULARY_VERSION, jurisdiction_label,
)
from app.impact_lens.selection import review_state, served_rows
from app.models import BillLayer, Entity
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


def _used_values(criteria_rows: list[dict]) -> tuple[set[str], set[str]]:
    """(roles, property types) the criteria mention."""
    roles: set[str] = set()
    property_types: set[str] = set()
    for c in criteria_rows:
        for side in (c.get("audience"), c.get("affected")):
            if side and side.get("kind") == "attr":
                roles.update(side.get("any_of") or [])
        for t in (c.get("requires") or []) + (c.get("excludes") or []):
            if t.get("attr") == "property_type":
                property_types.update(t.get("values") or [])
    return roles, property_types


def _location_kinds(criteria: dict) -> set[str]:
    """The kinds of the reader's location this entry's place names are compared
    with: the kind of each role it binds, plus residence for readers it only
    affects and for an unmapped or "anyone" audience. Mirrors the matcher's
    locationKindFor in frontend/lib/impactLens.ts."""
    kinds: set[str] = set()
    audience = criteria.get("audience")
    if audience and audience.get("kind") == "attr":
        kinds.update(ROLE_LOCATIONS.get(r, RESIDENCE) for r in audience.get("any_of") or [])
    else:
        kinds.add(RESIDENCE)
    affected = criteria.get("affected")
    if affected and affected.get("kind") == "attr" and affected.get("any_of"):
        kinds.add(RESIDENCE)
    return kinds or {RESIDENCE}


# Per kind of location: the county question, the municipality question, and
# their answer keys. The matcher reads the same keys (PLACE_KEYS in impactLens.ts).
_PLACE_QUESTIONS = {
    RESIDENCE: dict(
        county_key="county", county_label="County", county_q="Which Florida county do you live in?",
        city_key="municipality", city_label="City, Town or Village",
        city_q="Do you live in one of these cities, towns or villages?",
    ),
    PROPERTY: dict(
        county_key="property_county", county_label="Property County", county_q="In which Florida county is the property?",
        city_key="property_municipality", city_label="Property City, Town or Village",
        city_q="Is the property in one of these cities, towns or villages?",
    ),
    BUSINESS: dict(
        county_key="business_county", county_label="Business County",
        county_q="In which Florida county is the business or workplace?",
        city_key="business_municipality", city_label="Business City, Town or Village",
        city_q="Is the business or workplace in one of these cities, towns or villages?",
    ),
}


def _questions(criteria_rows: list[dict]) -> list[LensQuestionOut]:
    roles, property_types = _used_values(criteria_rows)
    # kind -> municipality names the entries of that kind name; a kind is asked
    # about only if some entry of that kind tests a place.
    places: dict[str, set[str]] = {}
    for c in criteria_rows:
        jurisdiction_values = [
            v
            for t in (c.get("requires") or []) + (c.get("excludes") or [])
            if t.get("attr") == "jurisdiction"
            for v in (t.get("values") or [])
        ]
        if not jurisdiction_values:
            continue
        for kind in _location_kinds(c):
            names = places.setdefault(kind, set())
            names.update(v.partition(":")[2] for v in jurisdiction_values if v.startswith("municipality:"))

    out: list[LensQuestionOut] = []
    if roles:
        role_attr = REGISTRY["role"]
        out.append(LensQuestionOut(
            key="role", label=role_attr.label, question=role_attr.question,
            options=_with_none([LensOptionOut(value=v, label=_title(v)) for v in role_attr.values if v in roles]),
        ))
    for kind in (RESIDENCE, PROPERTY, BUSINESS):
        if kind not in places:
            continue
        q = _PLACE_QUESTIONS[kind]
        out.append(LensQuestionOut(
            key=q["county_key"], label=q["county_label"], question=q["county_q"],
            options=[LensOptionOut(value=c, label=jurisdiction_label(f"county:{c}")) for c in FLORIDA_COUNTIES],
        ))
        named = sorted(n for n in places[kind] if n in MUNICIPALITY_COUNTIES)
        if named:
            # Only the places the bill names; a reader outside them picks
            # "None of These"
            out.append(LensQuestionOut(
                key=q["city_key"], label=q["city_label"], question=q["city_q"],
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
            role_locations=ROLE_LOCATIONS,
        )

    mapped = served_rows(db, layer)
    entries: list[LensEntryOut] = []
    for i, item in enumerate(layer.items):
        row = mapped.get(i)
        state = review_state(row) if row else None
        entries.append(LensEntryOut(
            group=str(item.get("group") or ""),
            text=str(item.get("text") or ""),
            quote=str(item.get("quote") or ""),
            conditions=[LensItemOut(text=str(c.get("text") or ""), quote=str(c.get("quote") or "")) for c in item.get("conditions") or []],
            exceptions=[LensItemOut(text=str(c.get("text") or ""), quote=str(c.get("quote") or "")) for c in item.get("exceptions") or []],
            # A rejected mapping is withheld: the entry reads as unmapped, never as a quiet miss.
            criteria=row.criteria if row and state != "rejected" else None,
            reviewed=state == "approved",
            withdrawn=state == "rejected",
        ))

    reasons: list[str] = []
    if layer.evidence_state != "supported":
        reasons.append("The Who it affects analysis is not marked supported.")
    if _CAPPED.search(layer.scope_note or ""):
        reasons.append("The analysis lists only the first entries of a longer list.")
    if not layer.items:
        reasons.append("The analysis has no entries.")
    withdrawn = sum(1 for e in entries if e.withdrawn)
    unmapped = sum(1 for e in entries if e.criteria is None and not e.withdrawn)
    if unmapped:
        reasons.append(f"{unmapped} of {len(entries)} entries have no questions mapped yet.")
    if withdrawn:
        reasons.append(f"{withdrawn} of {len(entries)} entries had their questions withdrawn after review.")

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
        role_locations=ROLE_LOCATIONS,
    )
