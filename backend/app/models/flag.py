from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# The correction process (Notion "Correction, Dispute & Right-of-Reply
# Process", decisions agreed 2026-10-01). A flag is what the spec calls a
# challenge: a public report that a statement is wrong, carried from triage
# to a recorded decision.
CATEGORIES = ("factually_wrong", "misleading", "wrong_source", "outdated", "wrong_entity", "other")
STATUSES = ("pending", "triaged", "decided", "dismissed")  # pending = submitted, not yet triaged
SEVERITIES = ("minor", "material", "critical")
DECISIONS = ("update", "correction", "clarification", "retraction", "source_correction", "no_change")
# What a flag can point at. "bill" = the bill as a whole.
OBJECT_TYPES = ("bill", "claim", "bill_layer", "amendment", "vote", "page_copy")


class Flag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user-submitted challenge to something on a bill page (BRD 5.5).

    Lifecycle: pending -> triaged -> decided (or dismissed: spam, duplicate,
    off-topic). Triage sets the severity and, for a credible challenge to a
    material or critical statement, `disputed_since`: the page then labels
    the statement "Disputed - under review". A disputed statement is never
    hidden (decision 2). A decision other than no_change produces a
    CorrectionRecord.

    `claim_id` is kept for the original form; new reports point at their
    target with object_type/object_id/object_version.
    """

    __tablename__ = "flags"
    __table_args__ = (
        CheckConstraint(f"status IN {STATUSES}", name="ck_flags_status"),
        CheckConstraint(f"category IN {CATEGORIES}", name="ck_flags_category"),
        CheckConstraint(f"severity IS NULL OR severity IN {SEVERITIES}", name="ck_flags_severity"),
        CheckConstraint(f"decision IS NULL OR decision IN {DECISIONS}", name="ck_flags_decision"),
        CheckConstraint(f"object_type IN {OBJECT_TYPES}", name="ck_flags_object_type"),
    )

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE")
    )
    object_type: Mapped[str] = mapped_column(String(20), nullable=False, default="bill")
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    object_version: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(String(2000))
    is_named_party: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reporter_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    severity: Mapped[str | None] = mapped_column(String(10))
    # Set at triage when the page should show "Disputed - under review";
    # cleared when the challenge is decided.
    disputed_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flags.id", ondelete="SET NULL")
    )
    decision: Mapped[str | None] = mapped_column(String(20))
    # Public, plain language: why the challenge was upheld or not.
    decision_explanation: Mapped[str | None] = mapped_column(Text)
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the flag left "pending" for good (decided or dismissed). The
    # privacy page promises reporter emails are deleted 90 days after this --
    # see pipeline/purge_flag_emails.py.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    bill_entity: Mapped["Entity"] = relationship()
    claim: Mapped["Claim | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Flag {self.status} on {self.bill_entity_id}>"
