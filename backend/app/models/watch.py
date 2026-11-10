from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Watch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One thing a reader follows: a bill, an official (person), or a topic, optionally within a
    jurisdiction. `target` is the bill or person entity id, or the topic slug. Deleted with the account."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "kind", "target", "jurisdiction", name="uq_watches_user_target"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # bill | official | topic
    target: Mapped[str] = mapped_column(String(80), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False, default="")  # topics only; '' = everywhere
