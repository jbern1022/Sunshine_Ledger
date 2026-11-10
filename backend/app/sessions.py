"""Server-side reader sessions (docs/ADR_READER_AUTH_COGNITO.md).

The browser holds an opaque random token; the database holds its SHA-256. Sign-in itself
(Cognito, passwords, codes) is NOT here: this module takes the outcome of a sign-in
(`SignInResult`) and decides whether a session may exist. That keeps the rules that matter
(the MFA gate, revocation, lifetimes) testable without AWS.

Proposed lifetimes (owner to confirm): 14 days idle, 90 days absolute, re-authentication
window 10 minutes for sensitive actions.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthSession, User

IDLE = timedelta(days=14)
ABSOLUTE = timedelta(days=90)
REAUTH_WINDOW = timedelta(minutes=10)
SECOND_FACTORS = frozenset({"totp", "passkey"})  # a user-verifying passkey stands alone; see ADR


class SessionRefused(Exception):
    """A session may not be created. `code` is safe to show the client."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SignInResult:
    """What a verified sign-in proved. `factors` holds "pwd" and/or "totp" and/or "passkey"."""

    factors: frozenset[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, result: SignInResult, *, now: datetime | None = None) -> tuple[str, AuthSession]:
    """Mint a session for a verified sign-in, or refuse. Returns (cookie token, row)."""
    now = now or _now()
    if user.status != "active":
        raise SessionRefused("account_unavailable")
    if user.recovery_state in ("requested", "under_review", "denied"):
        # The old account stays protected while a recovery is open or after it was denied.
        raise SessionRefused("recovery_pending")
    restricted = user.recovery_state == "approved"  # may enroll a replacement factor and nothing else
    if user.mfa_required and not restricted and not (result.factors & SECOND_FACTORS):
        # The gate lives here, not only in the provider: a password-only result is refused even
        # if the pool would have allowed it (e.g. the factor was deleted in the pool). The one
        # exception is an approved recovery, whose session is restricted to enrolling a factor.
        raise SessionRefused("mfa_required")
    token = secrets.token_urlsafe(32)
    row = AuthSession(
        user_id=user.id, token_hash=hash_token(token), last_seen_at=now, idle_expires_at=now + IDLE,
        absolute_expires_at=now + ABSOLUTE, auth_time=now, factors=sorted(result.factors), restricted=restricted,
    )
    user.last_sign_in_at = now
    db.add(row)
    db.commit()
    return token, row


def validate(db: Session, token: str | None, *, now: datetime | None = None, touch: bool = True) -> AuthSession | None:
    """The live session for a cookie token, or None. Checks revocation, both lifetimes and the
    account's status on every call."""
    if not token:
        return None
    now = now or _now()
    row = db.execute(select(AuthSession).where(AuthSession.token_hash == hash_token(token))).scalar_one_or_none()
    if row is None or row.revoked_at is not None or now >= row.idle_expires_at or now >= row.absolute_expires_at:
        return None
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    if touch:
        row.last_seen_at = now
        row.idle_expires_at = min(now + IDLE, row.absolute_expires_at)
        db.commit()
    return row


def recently_authenticated(row: AuthSession, *, now: datetime | None = None) -> bool:
    """True when the sign-in is fresh enough for a sensitive action (else answer reauth_required)."""
    return (now or _now()) - row.auth_time <= REAUTH_WINDOW


def revoke(db: Session, row: AuthSession, reason: str, *, now: datetime | None = None) -> None:
    if row.revoked_at is None:
        row.revoked_at, row.revoked_reason = now or _now(), reason
        db.commit()


def revoke_all(db: Session, user: User, reason: str, *, now: datetime | None = None) -> int:
    """Password change, MFA change, approved recovery, suspension, deletion: end every session."""
    now = now or _now()
    rows = db.execute(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
    ).scalars().all()
    for r in rows:
        r.revoked_at, r.revoked_reason = now, reason
    db.commit()
    return len(rows)


def enroll_factor(db: Session, user: User, *, now: datetime | None = None) -> None:
    """A second factor was enrolled and proven: require it from now on, end all sessions, and finish
    any approved recovery. The caller notifies the verified email."""
    user.mfa_required = True
    if user.recovery_state == "approved":
        user.recovery_state = "none"
    db.commit()
    revoke_all(db, user, "mfa_changed", now=now)


def password_reset_completed(db: Session, user: User, *, now: datetime | None = None) -> None:
    """A reset ends every session and does NOT touch `mfa_required`."""
    revoke_all(db, user, "password_reset", now=now)
