from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EntitlementGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A professional package granted to one account for a limited time (pilot access,
    docs/PRO_FEATURE_MATRIX.md). Grants are explicit, expire, and are never deleted: the
    rows are the audit record. Extending access is a new grant; ending it early sets
    `revoked_at`. No price, quota or card is stored here."""

    __tablename__ = "entitlement_grants"
    __table_args__ = (Index("ix_entitlement_grants_subject_expires", "subject", "expires_at"),)

    # An opaque account identifier. Accounts do not exist yet, so nothing is joined.
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    package: Mapped[str] = mapped_column(String(30), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(80))
