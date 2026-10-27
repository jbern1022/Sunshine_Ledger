"""Which criteria row a reader is served for each Who it affects entry, and
where it stands in review. One rule, shared by the read endpoint and the
review CLI so a reviewer acts on exactly what readers see.

See docs/IMPACT_LENS_REVIEW_LIFECYCLE.md.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.impact_lens.vocabulary import VOCABULARY_VERSION
from app.models import BillLayer, BillLayerCriteria

ReviewState = Literal["unreviewed", "approved", "rejected"]


def served_rows(db: Session, layer: BillLayer) -> dict[int, BillLayerCriteria]:
    """The newest row per entry at the CURRENT vocabulary version (any method
    version); rows mapped against an older vocabulary are ignored."""
    rows = db.execute(
        select(BillLayerCriteria)
        .where(BillLayerCriteria.bill_layer_id == layer.id, BillLayerCriteria.vocabulary_version == VOCABULARY_VERSION)
        .options(selectinload(BillLayerCriteria.reviews))
        .order_by(BillLayerCriteria.created_at, BillLayerCriteria.id)
    ).scalars().all()
    return {r.entry_index: r for r in rows}  # later rows overwrite earlier ones


def review_state(row: BillLayerCriteria) -> ReviewState:
    """A rejection is terminal and beats an approval; otherwise an approval
    counts; otherwise the row is unreviewed."""
    decisions = {r.decision for r in row.reviews}
    if "rejected" in decisions:
        return "rejected"
    if "approved" in decisions:
        return "approved"
    return "unreviewed"
