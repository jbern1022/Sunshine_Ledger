"""What kind of record a "bill" is.

City feeds carry more than legislation. Miami's iQM2 types every item
(2026-09-30: of 293 stored, ~120 were discussion items, code-enforcement
and ticketing agendas, protocol items such as proclamations, civil-service
notifications and hearings, attorney-client sessions). Jacksonville's
Legistar matter types were ordinances and resolutions apart from one set of
minutes. The source's own type is kept on the entity (attributes
"item_type") and mapped to a kind the site can word honestly:

- legislation: ordinances, resolutions (and every state bill)
- discussion: discussion items
- agenda: meeting agendas, minutes, calendars
- other: proclamations, hearings, notifications, directives, sessions

    python -m app.pipeline.item_kind --backfill   # from stored sources, no fetches
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, Source

KINDS = ("legislation", "discussion", "agenda", "other")


def item_kind(item_type: str | None) -> str:
    """Map a source's item type to a kind. No type (state bills, older
    records) counts as legislation."""
    t = (item_type or "").strip().lower()
    if not t or t.endswith("resolution") or t.endswith("ordinance"):
        return "legislation"
    if "discussion" in t:
        return "discussion"
    if t.endswith("agenda") or t == "minutes":
        return "agenda"
    return "other"


def backfill_item_types(db: Session) -> int:
    """Copy each city item's type from its newest stored source (iQM2 `type`,
    Legistar `matter_type`) onto the entity. Returns entities updated."""
    by_key: dict[tuple[str, str], str] = {}
    rows = db.execute(
        select(Source.source_type, Source.metadata_json, Source.retrieved_at)
        .where(Source.source_type.in_(["iqm2_legislation", "legistar_agenda"]))
        .order_by(Source.retrieved_at)
    ).all()
    for source_type, meta, _ in rows:
        meta = meta or {}
        if source_type == "iqm2_legislation" and meta.get("type"):
            by_key[("iqm2_legi_file_id", str(meta.get("legi_file_id")))] = meta["type"]
        elif source_type == "legistar_agenda" and meta.get("matter_type"):
            by_key[("legistar_matter_id", str(meta.get("matter_id")))] = meta["matter_type"]

    updated = 0
    for entity in db.execute(select(Entity).where(Entity.entity_type == "bill", Entity.jurisdiction_level == "city")).scalars():
        ids = entity.external_ids or {}
        item_type = next(
            (by_key[(k, str(ids[k]))] for k in ("iqm2_legi_file_id", "legistar_matter_id") if k in ids and (k, str(ids[k])) in by_key),
            None,
        )
        if item_type and (entity.attributes or {}).get("item_type") != item_type:
            entity.attributes = {**(entity.attributes or {}), "item_type": item_type}
            updated += 1
    db.commit()
    return updated


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill", action="store_true", required=True)
    parser.parse_args()
    session = SessionLocal()
    try:
        print(f"Recorded the item type on {backfill_item_types(session)} city items.")
    finally:
        session.close()
