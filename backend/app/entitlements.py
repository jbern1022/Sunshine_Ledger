"""Pilot access to professional features (docs/PRO_FEATURE_MATRIX.md).

    python -m app.entitlements grant SUBJECT --package research --days 90 --by joe [--reason "..."]
    python -m app.entitlements revoke SUBJECT --by joe
    python -m app.entitlements show SUBJECT
    python -m app.entitlements list

Rules this module enforces, from the accepted principles:

* Everything the public gets is in FREE and is returned for every subject, with or without a grant.
  Nothing in a package can remove it, and no package can contain a FREE capability by mistake.
* Paying (or piloting) never buys editorial treatment: NEVER_FOR_SALE capabilities cannot be put in
  a package, and a test pins that.
* A grant has an expiry. When it ends the subject keeps FREE only; saved data is not deleted here,
  and `own_data_export` stays free so a person can always take their data.
* No prices, quotas or pilot length live here. Packages are names for sets of capabilities and are
  meant to be edited as the pilot teaches us.

Nothing calls this yet: accounts (Cognito) do not exist. When they do, `capabilities_for` is the
only function a request handler needs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EntitlementGrant

FREE: frozenset[str] = frozenset({
    "browse", "findings", "corrections", "rss", "impact_lens", "methodology", "own_data_export",
    # Decided 2026-11-10: watchlists are free for every account (the matrix's open question 8).
    # Free means no entitlement is needed; it still needs an account to be saved on the server.
    "watchlists",
})

NEVER_FOR_SALE: frozenset[str] = frozenset({
    "editorial_priority", "review_priority", "conclusion_changes", "correction_treatment",
})

# Name -> capabilities, from the matrix. "Bulk or API access" is undecided and in no package.
PACKAGES: dict[str, frozenset[str]] = {
    "research": frozenset({
        "alerts", "digests", "saved_searches", "private_notes", "evidence_export", "briefing_export",
    }),
    "team": frozenset({
        "alerts", "digests", "saved_searches", "private_notes", "evidence_export", "briefing_export",
        "team_workspace",
    }),
}


def validate_packages(packages: dict[str, frozenset[str]] = PACKAGES) -> list[str]:
    """Problems with a package table; empty when it is acceptable."""
    problems = []
    for name, caps in packages.items():
        if caps & FREE:
            problems.append(f"{name}: contains free capabilities {sorted(caps & FREE)}")
        if caps & NEVER_FOR_SALE:
            problems.append(f"{name}: contains capabilities that are never for sale {sorted(caps & NEVER_FOR_SALE)}")
    return problems


def _now() -> datetime:
    return datetime.now(timezone.utc)


def active_grants(db: Session, subject: str, at: datetime | None = None) -> list[EntitlementGrant]:
    at = at or _now()
    return list(db.execute(
        select(EntitlementGrant).where(
            EntitlementGrant.subject == subject,
            EntitlementGrant.starts_at <= at,
            EntitlementGrant.expires_at > at,
            EntitlementGrant.revoked_at.is_(None),
        ).order_by(EntitlementGrant.expires_at)
    ).scalars())


def capabilities_for(db: Session, subject: str | None, at: datetime | None = None) -> frozenset[str]:
    """Everything this subject may do now: FREE always, plus the packages of active grants.
    `None` (a visitor with no account) gets FREE."""
    caps = set(FREE)
    if subject:
        for g in active_grants(db, subject, at):
            caps |= PACKAGES.get(g.package, frozenset())
    return frozenset(caps)


def has_capability(db: Session, subject: str | None, capability: str, at: datetime | None = None) -> bool:
    return capability in capabilities_for(db, subject, at)


def grant(
    db: Session, subject: str, package: str, *, days: int, granted_by: str, reason: str | None = None,
    starts_at: datetime | None = None,
) -> EntitlementGrant:
    if package not in PACKAGES:
        raise ValueError(f"unknown package {package!r}; choose from {sorted(PACKAGES)}")
    if days <= 0:
        raise ValueError("a grant needs an expiry: days must be positive")
    if not subject.strip() or not granted_by.strip():
        raise ValueError("subject and granted_by are required")
    start = starts_at or _now()
    row = EntitlementGrant(
        subject=subject, package=package, starts_at=start, expires_at=start + timedelta(days=days),
        granted_by=granted_by, reason=reason,
    )
    db.add(row)
    db.commit()
    return row


def revoke(db: Session, subject: str, *, revoked_by: str, at: datetime | None = None) -> int:
    """End every active grant now. Returns how many were ended. Rows stay as the record."""
    at = at or _now()
    rows = active_grants(db, subject, at)
    for g in rows:
        g.revoked_at, g.revoked_by = at, revoked_by
    db.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    from app.db import SessionLocal

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant")
    g.add_argument("subject")
    g.add_argument("--package", required=True, choices=sorted(PACKAGES))
    g.add_argument("--days", type=int, required=True)
    g.add_argument("--by", required=True)
    g.add_argument("--reason")
    r = sub.add_parser("revoke")
    r.add_argument("subject")
    r.add_argument("--by", required=True)
    s = sub.add_parser("show")
    s.add_argument("subject")
    sub.add_parser("list")
    args = p.parse_args(argv)

    db = SessionLocal()
    try:
        if args.cmd == "grant":
            row = grant(db, args.subject, args.package, days=args.days, granted_by=args.by, reason=args.reason)
            print(f"{row.subject}: {row.package} until {row.expires_at:%Y-%m-%d}")
        elif args.cmd == "revoke":
            print(f"{revoke(db, args.subject, revoked_by=args.by)} grant(s) ended")
        elif args.cmd == "show":
            print("capabilities:", ", ".join(sorted(capabilities_for(db, args.subject))))
            for gr in active_grants(db, args.subject):
                print(f"  {gr.package} until {gr.expires_at:%Y-%m-%d} (granted by {gr.granted_by})")
        else:
            rows = db.execute(select(EntitlementGrant).order_by(EntitlementGrant.expires_at.desc())).scalars()
            for gr in rows:
                state = "revoked" if gr.revoked_at else ("active" if gr.starts_at <= _now() < gr.expires_at else "expired")
                print(f"{gr.subject}\t{gr.package}\t{state}\t{gr.expires_at:%Y-%m-%d}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
