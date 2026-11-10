from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reader account (docs/ADR_READER_AUTH_COGNITO.md). Authorization is always by `id`;
    `cognito_sub` is the stable provider subject, never the email. No profile, no Impact Lens
    data, nothing but what the account needs."""

    __tablename__ = "users"

    cognito_sub: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320))  # copied after verification, for notices
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")  # active|suspended|deleted
    # True once the user enrolls a second factor. Cleared only by an explicit, re-authenticated
    # action or an approved support recovery; a password reset never clears it.
    mfa_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recovery_state: Mapped[str] = mapped_column(String(14), nullable=False, default="none")
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One browser session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auth_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    factors: Mapped[list[str]] = mapped_column(ARRAY(String(12)), nullable=False)  # pwd, totp, passkey
    restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # may only enroll a factor
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(40))
