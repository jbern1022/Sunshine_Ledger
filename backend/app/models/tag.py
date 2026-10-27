from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

GOVERNANCE_SLUG = "governance"


class Tag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A badge category in the curated topic taxonomy (Roadmap Phase 2: bill
    topic tagging). Seeded with a fixed ~13-category set plus the
    "governance" catch-all -- not user-creatable through the API, so `slug`
    stays a small, known set curated in app/pipeline/topic_tagging_seed.py.
    """

    __tablename__ = "tags"

    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Tag {self.slug}>"


class SubjectMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Curated lookup: a raw source subject string (verbatim from LegiScan's
    pass-through of the Florida Legislature's Subject Index) -> Tag.

    This is the mapping table's defined owner/location per the bill topic
    tagging acceptance criteria. A `raw_subject` with no row here falls back
    to the "governance" tag at assignment time (see
    app/pipeline/topic_tagging.py:resolve_tag_for_subject) rather than being
    silently dropped.
    """

    __tablename__ = "subject_mappings"

    raw_subject: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )

    tag: Mapped["Tag"] = relationship()

    def __repr__(self) -> str:
        return f"<SubjectMapping {self.raw_subject!r}>"


class BillTag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Join table: which Tags are assigned to a bill. Multi-tag by design
    (Roadmap decision 2026-09-08: multi-tag bills show every applicable
    badge, no priority pick) -- this is a join table, not a single column.
    """

    __tablename__ = "bill_tags"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # legiscan | ollama | manual -- kept separate from raw_subject so
    # local-bill (Ollama) tag quality can be audited apart from
    # state-verified (LegiScan) tags, per the Roadmap decision.
    tag_source: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_subject: Mapped[str | None] = mapped_column(String(200))  # set when tag_source="legiscan"
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    bill_entity: Mapped["Entity"] = relationship(back_populates="bill_tags")
    tag: Mapped["Tag"] = relationship()

    __table_args__ = (
        UniqueConstraint("bill_entity_id", "tag_id", name="uq_bill_tags_bill_entity_id_tag_id"),
    )

    def __repr__(self) -> str:
        return f"<BillTag bill={self.bill_entity_id} tag={self.tag_id}>"


class TagQuarantine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tag slug the local model proposed that is not in the canonical
    allowlist. Held for review instead of dropped: a recurring slug may mean
    the vocabulary should grow, but only a person grows it (no silent
    taxonomy expansion). status: pending | added | mapped | rejected --
    `added` means the slug was approved for the vocabulary (the change itself
    is an edit to topic_tagging_seed.TAGS, which the classifier's allowlist
    is built from), `mapped` that it was judged equivalent to `mapped_tag`,
    `rejected` that it stays out. Neither tags the bill automatically; the
    next classification pass does.
    """

    __tablename__ = "tag_quarantine"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposed_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Provenance: how the slug arose, so a reviewer can judge it.
    tag_source: Mapped[str] = mapped_column(String(20), nullable=False, default="ollama")
    bill_title: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    mapped_tag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="SET NULL"))
    reviewer: Mapped[str | None] = mapped_column(String(100))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("bill_entity_id", "proposed_slug", name="uq_tag_quarantine_bill_slug"),
    )


class BillTagRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What the last local-model classification of a bill saw and how it
    ended. `input_hash` is a hash of the title and description, so an amended
    bill is re-classified rather than keeping stale tags. `outcome`:
    ok | empty (the model answered but nothing valid; Governance applied) |
    failed (the call or parse failed; no tag written, retried next run) |
    legacy (tagged before runs were recorded; input recorded, not re-run).
    """

    __tablename__ = "bill_tag_runs"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(300))
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
