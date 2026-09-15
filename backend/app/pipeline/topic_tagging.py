"""Bill topic tagging: resolve raw source subjects to badge Tags and record
the assignment, per the Roadmap Phase 2 bill topic tagging feature.

Two ways a bill gets tagged:
  - LegiScan-sourced: `assign_tags_for_bill(..., raw_subjects=[...])`, one
    raw FL Subject Index string per call, looked up in the curated
    SubjectMapping table.
  - Local-bill (Ollama) fallback: `assign_tags_for_bill(..., ollama_tag_slugs=[...])`,
    since Miami/Jacksonville Legistar bills carry no subject field at all.

Every state change (a tag added, hidden, or reactivated) writes an Event on
the bill's entity, per the 2026-09-08 decision to log through the unified
Event timeline rather than a standalone tag-only log.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.tag import GOVERNANCE_SLUG, BillTag, SubjectMapping, Tag


def _governance_tag(db: Session) -> Tag:
    tag = db.execute(select(Tag).where(Tag.slug == GOVERNANCE_SLUG)).scalar_one_or_none()
    if tag is None:
        raise RuntimeError(
            "Governance catch-all tag is missing -- run "
            "`python -m app.pipeline.topic_tagging_seed` first"
        )
    return tag


def resolve_tag_for_subject(db: Session, raw_subject: str) -> Tag:
    """Curated-mapping lookup for one raw subject string. An unmapped
    subject routes to the Governance catch-all rather than being silently
    dropped -- this IS the "defined behavior for a brand-new raw subject
    with no mapping yet" the acceptance criteria call for.
    """
    mapping = db.execute(
        select(SubjectMapping).where(SubjectMapping.raw_subject == raw_subject)
    ).scalar_one_or_none()
    if mapping is not None:
        return mapping.tag
    return _governance_tag(db)


def assign_tags_for_bill(
    db: Session,
    bill_entity_id: uuid.UUID,
    *,
    raw_subjects: list[str] | None = None,
    ollama_tag_slugs: list[str] | None = None,
) -> list[BillTag]:
    """Idempotent: re-running with subjects the bill is already tagged with
    creates no duplicate rows and logs no duplicate events. Returns only the
    newly-created BillTags.
    """
    existing_tag_ids = {
        bt.tag_id
        for bt in db.execute(
            select(BillTag).where(BillTag.bill_entity_id == bill_entity_id)
        ).scalars()
    }
    created: list[BillTag] = []

    def _add(tag: Tag, *, tag_source: str, raw_subject: str | None) -> None:
        if tag.id in existing_tag_ids:
            return
        bill_tag = BillTag(
            bill_entity_id=bill_entity_id,
            tag_id=tag.id,
            tag_source=tag_source,
            raw_subject=raw_subject,
            active=True,
        )
        db.add(bill_tag)
        db.add(
            Event(
                entity_id=bill_entity_id,
                event_type="tag_added",
                event_date=date.today(),
                title=f"Tagged {tag.label}",
                attributes={"tag_id": str(tag.id), "tag_slug": tag.slug, "tag_source": tag_source},
            )
        )
        existing_tag_ids.add(tag.id)
        created.append(bill_tag)

    for raw_subject in raw_subjects or []:
        tag = resolve_tag_for_subject(db, raw_subject)
        _add(tag, tag_source="legiscan", raw_subject=raw_subject)

    if ollama_tag_slugs:
        tags_by_slug = {
            t.slug: t
            for t in db.execute(select(Tag).where(Tag.slug.in_(set(ollama_tag_slugs)))).scalars()
        }
        for slug in ollama_tag_slugs:
            tag = tags_by_slug.get(slug)
            if tag is not None:
                _add(tag, tag_source="ollama", raw_subject=None)

    db.commit()
    return created


def set_bill_tag_active(db: Session, bill_tag_id: uuid.UUID, *, active: bool) -> BillTag:
    """Toggle a single badge's visibility on a bill without deleting the
    assignment -- reversible, per the "badges have an active/hidden state"
    decision. No-ops (and logs nothing) if already in the requested state.
    """
    bill_tag = db.get(BillTag, bill_tag_id)
    if bill_tag is None:
        raise ValueError(f"BillTag {bill_tag_id} not found")
    if bill_tag.active == active:
        return bill_tag

    bill_tag.active = active
    db.add(
        Event(
            entity_id=bill_tag.bill_entity_id,
            event_type="tag_reactivated" if active else "tag_hidden",
            event_date=date.today(),
            title=f"{'Reactivated' if active else 'Hidden'} tag {bill_tag.tag.label}",
            attributes={"tag_id": str(bill_tag.tag_id), "tag_slug": bill_tag.tag.slug},
        )
    )
    db.commit()
    return bill_tag
