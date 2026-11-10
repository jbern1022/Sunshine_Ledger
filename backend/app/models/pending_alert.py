from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PendingAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A change that matched one of a user's watches and is waiting to be sent in a digest.
    At most one row per (user, event), however many watches matched. `delivered_at` is set only
    after a send is confirmed; nothing sends yet."""

    __tablename__ = "pending_alerts"
    __table_args__ = (UniqueConstraint("user_id", "event_id", name="uq_pending_alerts_user_event"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    watch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("watches.id", ondelete="SET NULL"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
