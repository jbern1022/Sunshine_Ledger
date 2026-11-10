from datetime import datetime, timedelta, timezone

import pytest

from app import entitlements as ent
from app.models import EntitlementGrant


def test_the_package_table_never_contains_free_or_never_for_sale_capabilities():
    assert ent.validate_packages() == []
    assert ent.validate_packages({"bad": frozenset({"corrections", "watchlists"})})
    assert ent.validate_packages({"bad": frozenset({"editorial_priority"})})
    assert not (ent.FREE & ent.NEVER_FOR_SALE)


def test_a_visitor_or_an_account_with_no_grant_gets_exactly_the_free_set(db_session):
    assert ent.capabilities_for(db_session, None) == ent.FREE
    assert ent.capabilities_for(db_session, "acct-1") == ent.FREE
    assert ent.has_capability(db_session, "acct-1", "corrections")
    assert not ent.has_capability(db_session, "acct-1", "alerts")


def test_a_grant_adds_its_package_until_it_expires_and_then_only_free_remains(db_session):
    start = datetime(2026, 12, 1, tzinfo=timezone.utc)
    ent.grant(db_session, "acct-1", "research", days=90, granted_by="joe", reason="pilot", starts_at=start)
    assert ent.has_capability(db_session, "acct-1", "evidence_export", at=start + timedelta(days=1))
    assert not ent.has_capability(db_session, "acct-1", "team_workspace", at=start + timedelta(days=1))
    after = start + timedelta(days=91)
    assert ent.capabilities_for(db_session, "acct-1", at=after) == ent.FREE
    assert ent.has_capability(db_session, "acct-1", "own_data_export", at=after)  # never taken away
    assert not ent.has_capability(db_session, "acct-1", "alerts", at=start - timedelta(days=1))  # not started yet


def test_grants_need_a_known_package_a_positive_expiry_and_a_grantor(db_session):
    with pytest.raises(ValueError):
        ent.grant(db_session, "a", "gold", days=30, granted_by="joe")
    with pytest.raises(ValueError):
        ent.grant(db_session, "a", "research", days=0, granted_by="joe")
    with pytest.raises(ValueError):
        ent.grant(db_session, "a", "research", days=30, granted_by=" ")
    assert db_session.query(EntitlementGrant).count() == 0


def test_revoking_ends_access_and_keeps_the_record(db_session):
    ent.grant(db_session, "acct-1", "team", days=30, granted_by="joe")
    assert ent.has_capability(db_session, "acct-1", "team_workspace")
    assert ent.revoke(db_session, "acct-1", revoked_by="joe") == 1
    assert not ent.has_capability(db_session, "acct-1", "team_workspace")
    row = db_session.query(EntitlementGrant).one()
    assert row.revoked_by == "joe" and row.revoked_at is not None
    assert ent.revoke(db_session, "acct-1", revoked_by="joe") == 0


def test_two_grants_combine_and_other_accounts_are_unaffected(db_session):
    ent.grant(db_session, "acct-1", "research", days=30, granted_by="joe")
    ent.grant(db_session, "acct-1", "team", days=30, granted_by="joe")
    assert ent.has_capability(db_session, "acct-1", "team_workspace")
    assert not ent.has_capability(db_session, "acct-2", "alerts")
