"""A reader's rights over their own account data: export and deletion
(Todoist 6hrmhxW4cj9jXvgp; docs/ADR_READER_AUTH_COGNITO.md).

Provider-independent: deleting the identity at the provider (Cognito) is a callable the caller
passes in, so the order of events and the failure path are testable without AWS.

What is held, and so what is exported or deleted: the account row (id, provider subject, verified
email, status), its sessions, and its entitlement grants. Notes will be added here when they exist. Impact Lens answers are never held (they stay in the browser) and so are not here.

Retention periods are parameters, not decisions: the values in `Retention` are PROPOSALS from the ADR
and are not approved. The owner sets them; nothing runs on a schedule yet.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import sessions
from app.models import AuthSession, EntitlementGrant, User, Watch


@dataclass(frozen=True)
class Retention:
    """Proposed, not approved (ADR). Pass your own."""

    unverified_signup: timedelta = timedelta(days=7)
    expired_session_rows: timedelta = timedelta(days=30)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def export_user(db: Session, user: User) -> dict:
    """Everything held about the user, as plain data. Session token hashes are not included (they
    are credentials, and useless to the person); everything else is."""
    grants = db.execute(select(EntitlementGrant).where(EntitlementGrant.subject == str(user.id))).scalars().all()
    rows = db.execute(select(AuthSession).where(AuthSession.user_id == user.id).order_by(AuthSession.created_at)).scalars().all()
    return {
        "account": {
            "id": str(user.id), "email": user.email, "status": user.status, "created_at": _iso(user.created_at),
            "last_sign_in_at": _iso(user.last_sign_in_at), "second_factor_required": user.mfa_required,
        },
        "sessions": [
            {"created_at": _iso(r.created_at), "last_seen_at": _iso(r.last_seen_at), "factors": list(r.factors),
             "revoked_at": _iso(r.revoked_at), "revoked_reason": r.revoked_reason}
            for r in rows
        ],
        "entitlement_grants": [
            {"package": g.package, "starts_at": _iso(g.starts_at), "expires_at": _iso(g.expires_at),
             "granted_by": g.granted_by, "reason": g.reason, "revoked_at": _iso(g.revoked_at)}
            for g in grants
        ],
        "watchlist": [
            {"kind": w.kind, "target": w.target, "jurisdiction": w.jurisdiction or None, "created_at": _iso(w.created_at)}
            for w in db.execute(select(Watch).where(Watch.user_id == user.id).order_by(Watch.created_at)).scalars()
        ],
        "not_held": ["Impact Lens answers (they stay in your browser)", "your password (held by the identity provider)"],
    }


def anonymous_subject(user_id: str) -> str:
    return "deleted:" + hashlib.sha256(user_id.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class DeletionResult:
    local_done: bool
    provider_done: bool  # False: the provider call failed; the user row stays as a tombstone to retry


def delete_account(
    db: Session, user: User, provider_delete: Callable[[str], None], *, keep_anonymized_grants: bool = True,
    now: datetime | None = None,
) -> DeletionResult:
    """Delete the account. Order: stop access, remove local data, then delete at the provider.

    1. Mark deleted and revoke every session (access ends first, even if later steps fail).
    2. Remove sessions and the email. Entitlement grants are the pilot's audit record: by default their
       subject is replaced with a one-way hash (`keep_anonymized_grants`); pass False to delete them.
       Whether they may be kept is an open owner decision (ADR).
    3. Ask the provider to delete the identity. On failure the tombstone row (provider subject only, no
       email) stays so the call can be retried; on success the row is removed.
    """
    now = now or datetime.now(timezone.utc)
    uid = str(user.id)
    user.status = "deleted"
    db.commit()
    sessions.revoke_all(db, user, "account_deleted", now=now)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    if keep_anonymized_grants:
        for g in db.execute(select(EntitlementGrant).where(EntitlementGrant.subject == uid)).scalars():
            g.subject = anonymous_subject(uid)
    else:
        db.execute(delete(EntitlementGrant).where(EntitlementGrant.subject == uid))
    user.email = None
    db.commit()
    try:
        provider_delete(user.cognito_sub)
    except Exception:  # noqa: BLE001 -- any provider failure leaves the tombstone for a retry
        return DeletionResult(local_done=True, provider_done=False)
    db.delete(user)
    db.commit()
    return DeletionResult(local_done=True, provider_done=True)


def retry_provider_deletions(db: Session, provider_delete: Callable[[str], None]) -> int:
    """Finish deletions whose provider call failed earlier. Returns how many completed."""
    done = 0
    for user in db.execute(select(User).where(User.status == "deleted")).scalars().all():
        try:
            provider_delete(user.cognito_sub)
        except Exception:  # noqa: BLE001
            continue
        db.delete(user)
        db.commit()
        done += 1
    return done


def purge_expired(db: Session, retention: Retention, *, now: datetime | None = None) -> dict[str, int]:
    """Remove operational rows past their retention: session rows long expired or revoked, and accounts that never
    signed in (never verified) within the window. Nothing else is touched."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - retention.expired_session_rows
    old = db.execute(delete(AuthSession).where(
        (AuthSession.absolute_expires_at < cutoff) | (AuthSession.revoked_at < cutoff)
    )).rowcount
    stale = db.execute(
        select(User).where(User.last_sign_in_at.is_(None), User.status == "active", User.created_at < now - retention.unverified_signup)
    ).scalars().all()
    for u in stale:
        db.delete(u)
    db.commit()
    return {"sessions": old or 0, "unverified_accounts": len(stale)}
