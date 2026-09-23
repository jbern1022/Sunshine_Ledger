from datetime import datetime, timedelta, timezone

from app.models import Flag
from app.pipeline.purge_flag_emails import RETENTION_DAYS, purge_reporter_emails

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _flag(db_session, entity, *, status="reviewed", resolved_days_ago=None, email="reporter@example.com"):
    flag = Flag(
        bill_entity_id=entity.id,
        reason_text="This looks wrong",
        reporter_email=email,
        status=status,
        resolved_at=None if resolved_days_ago is None else NOW - timedelta(days=resolved_days_ago),
    )
    db_session.add(flag)
    # Commit, not flush: the dry run rolls back, and must only undo its own
    # update, not the setup insert.
    db_session.commit()
    return flag


def test_purges_email_resolved_past_retention(db_session, bill_factory):
    flag = _flag(db_session, bill_factory(), resolved_days_ago=RETENTION_DAYS + 1)

    assert purge_reporter_emails(db_session, now=NOW) == 1
    db_session.refresh(flag)
    assert flag.reporter_email is None
    # The report itself is kept -- only the email goes.
    assert flag.reason_text == "This looks wrong"
    assert flag.status == "reviewed"


def test_keeps_email_within_retention(db_session, bill_factory):
    flag = _flag(db_session, bill_factory(), status="dismissed", resolved_days_ago=RETENTION_DAYS - 1)

    assert purge_reporter_emails(db_session, now=NOW) == 0
    db_session.refresh(flag)
    assert flag.reporter_email == "reporter@example.com"


def test_never_purges_pending_flags(db_session, bill_factory):
    # A pending flag still needs its email for follow-up, however old it is.
    flag = _flag(db_session, bill_factory(), status="pending")

    assert purge_reporter_emails(db_session, now=NOW) == 0
    db_session.refresh(flag)
    assert flag.reporter_email == "reporter@example.com"


def test_dry_run_changes_nothing(db_session, bill_factory):
    flag = _flag(db_session, bill_factory(), resolved_days_ago=RETENTION_DAYS + 30)

    assert purge_reporter_emails(db_session, now=NOW, dry_run=True) == 1
    db_session.refresh(flag)
    assert flag.reporter_email == "reporter@example.com"


def test_skips_flags_with_no_email(db_session, bill_factory):
    _flag(db_session, bill_factory(), resolved_days_ago=RETENTION_DAYS + 1, email=None)

    assert purge_reporter_emails(db_session, now=NOW) == 0
