from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

CHANGE_TYPES = ("update", "correction", "clarification", "retraction", "source_correction")
TRIGGERS = ("challenge", "internal_review", "source_change", "methodology_change")


class CorrectionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A change Sunshine Ledger made to something it published, and why.

    Append-only, like bill_layers: nothing here is edited after insert. Per
    the agreed decisions (2026-10-01), every correction, update and overturn
    stays visible with the earlier version, the corrected version and the
    evidence -- so the record keeps the text of both, not only references.
    Minor fixes are recorded too; the public log just doesn't headline them.

    `decided_by` is internal (never returned publicly); the public view says
    "Sunshine Ledger editor" or "automated process".
    """

    __tablename__ = "correction_records"
    __table_args__ = (
        CheckConstraint(f"change_type IN {CHANGE_TYPES}", name="ck_correction_change_type"),
        CheckConstraint("severity IN ('minor', 'material', 'critical')", name="ck_correction_severity"),
        CheckConstraint(f"trigger IN {TRIGGERS}", name="ck_correction_trigger"),
    )

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_type: Mapped[str] = mapped_column(String(20), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    prior_version: Mapped[int | None] = mapped_column(Integer)
    current_version: Mapped[int | None] = mapped_column(Integer)
    prior_text: Mapped[str | None] = mapped_column(Text)
    current_text: Mapped[str | None] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("flags.id", ondelete="SET NULL"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"url": ..., "role": "supporting" | "challenging" | "contradicting", "note": ...}]
    evidence_links: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    # Who produced what was corrected: sunshine_ledger_ai, legislative_staff,
    # bill_text, ... and whether a person had reviewed that version (decision 4).
    origin: Mapped[str | None] = mapped_column(String(30))
    was_reviewed: Mapped[bool | None] = mapped_column(Boolean)
    methodology_version: Mapped[str | None] = mapped_column(String(80))
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    flag: Mapped["Flag | None"] = relationship()


class Response(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Right of reply: a verified response from a person or organization
    named on a page, shown verbatim under the record it answers.

    Verified through the contact on their official filing (decision 3,
    interim until user accounts exist); `verified_via` is shown publicly.
    A response is not evidence and changes no evidence state. Never edited:
    a newer response from the same party supersedes it, and both are kept.
    """

    __tablename__ = "responses"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_type: Mapped[str] = mapped_column(String(20), nullable=False, default="bill")
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    responder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    responder_role: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    full_text_url: Mapped[str | None] = mapped_column(String(2000))
    verified_via: Mapped[str] = mapped_column(String(300), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responses.id", ondelete="SET NULL")
    )
