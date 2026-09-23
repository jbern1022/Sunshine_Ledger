"""Append-only writes for bill layers.

The only two writes this module ever makes: insert a new version, and stamp
`superseded_at` on the version it replaces -- in one transaction, so the
one-current-row index is never violated mid-way. Nothing else on an
existing row is updated; that is how earlier versions stay intact.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillLayer, BillLayerSource, Source
from app.models.bill_layer import ALLOWED_PAIRS
from app.pipeline.bill_layers import METHOD_VERSIONS, LayerResult


def layer_input_hash(layer: str, origin: str, input_text: str, model: str) -> str:
    parts = [METHOD_VERSIONS[(layer, origin)], model, input_text]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def current_layer(db: Session, bill_entity_id: uuid.UUID, layer: str, origin: str) -> BillLayer | None:
    return db.execute(
        select(BillLayer).where(
            BillLayer.bill_entity_id == bill_entity_id,
            BillLayer.layer == layer,
            BillLayer.origin == origin,
            BillLayer.superseded_at.is_(None),
        )
    ).scalar_one_or_none()


def store_layer_version(
    db: Session,
    *,
    bill_entity_id: uuid.UUID,
    layer: str,
    origin: str,
    result: LayerResult,
    input_hash: str,
    generated_by: str,
    sources: list[Source],
) -> BillLayer | None:
    if (layer, origin) not in ALLOWED_PAIRS:
        raise ValueError(f"({layer}, {origin}) is not an allowed layer/origin pair")

    existing = current_layer(db, bill_entity_id, layer, origin)
    if existing is not None and existing.input_hash == input_hash:
        return None

    last_version = db.execute(
        select(func.max(BillLayer.version)).where(
            BillLayer.bill_entity_id == bill_entity_id, BillLayer.layer == layer, BillLayer.origin == origin
        )
    ).scalar() or 0

    if existing is not None:
        existing.superseded_at = datetime.now(timezone.utc)
        db.flush()  # free the one-current-row slot before inserting

    row = BillLayer(
        bill_entity_id=bill_entity_id,
        layer=layer,
        origin=origin,
        version=last_version + 1,
        evidence_state=result.evidence_state,
        scope_note=result.scope_note,
        items=result.items,
        generated_by=generated_by,
        method_version=METHOD_VERSIONS[(layer, origin)],
        input_hash=input_hash,
    )
    db.add(row)
    for source in sources:
        db.add(source)
    db.flush()
    for source in sources:
        db.add(BillLayerSource(bill_layer_id=row.id, source_id=source.id))
    db.commit()
    db.refresh(row)
    return row
