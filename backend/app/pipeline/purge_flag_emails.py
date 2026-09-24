"""Delete reporter emails from flags resolved more than 90 days ago.

The public privacy page promises that an email left on a "Flag this" report
is kept only until the report is resolved, then deleted within 90 days.
This job is what makes that true: it clears `reporter_email` on flags whose
`resolved_at` is older than the retention window. The report itself (reason
text, status, which bill) is kept -- it's the correction history, and holds
nothing personal once the email is gone.

Pending flags are never touched, however old: the email is still needed to
follow up. Runs nightly as a step in scripts/run-ingestion.sh.

Usage:
    python -m app.pipeline.purge_flag_emails [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.db import SessionLocal
from app.logging_setup import quiet_http_logging
from app.models import Flag

logger = logging.getLogger(__name__)

# Keep in sync with the retention promise on frontend/app/privacy/page.tsx.
RETENTION_DAYS = 90


def purge_reporter_emails(db, *, now: datetime | None = None, dry_run: bool = False) -> int:
    """Clear reporter emails on flags resolved before the retention cutoff.

    Returns the number of flags purged (or that would be, with `dry_run`).
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)
    stmt = (
        update(Flag)
        .where(
            Flag.status != "pending",
            Flag.resolved_at.is_not(None),
            Flag.resolved_at < cutoff,
            Flag.reporter_email.is_not(None),
        )
        .values(reporter_email=None)
    )
    result = db.execute(stmt)
    purged = result.rowcount
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return purged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count what would be purged; change nothing.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        n = purge_reporter_emails(db, dry_run=args.dry_run)
        verb = "Would purge" if args.dry_run else "Purged"
        print(f"{verb} reporter email on {n} flag(s) resolved over {RETENTION_DAYS} days ago.")
    finally:
        db.close()
