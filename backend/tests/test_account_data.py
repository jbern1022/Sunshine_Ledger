from datetime import datetime, timedelta, timezone

from app import account_data as ad
from app import entitlements as ent
from app import sessions as s
from app.models import AuthSession, EntitlementGrant, User

T0 = datetime(2026, 12, 1, tzinfo=timezone.utc)


def make_user(db, sub="sub-1", **kw):
    u = User(cognito_sub=sub, email="a@example.org", **kw)
    db.add(u)
    db.commit()
    return u


def test_export_lists_what_is_held_and_never_a_token_hash(db_session):
    u = make_user(db_session)
    token, _ = s.create_session(db_session, u, s.SignInResult(frozenset({"pwd"})), now=T0)
    ent.grant(db_session, str(u.id), "research", days=30, granted_by="joe", reason="pilot")
    out = ad.export_user(db_session, u)
    assert out["account"]["email"] == "a@example.org" and len(out["sessions"]) == 1
    assert out["entitlement_grants"][0]["package"] == "research"
    flat = str(out)
    assert token not in flat and s.hash_token(token) not in flat
    assert any("Impact Lens" in n for n in out["not_held"])


def test_deletion_removes_data_revokes_access_anonymizes_grants_and_drops_the_user(db_session):
    u = make_user(db_session)
    uid = str(u.id)
    token, _ = s.create_session(db_session, u, s.SignInResult(frozenset({"pwd"})), now=T0)
    ent.grant(db_session, uid, "team", days=30, granted_by="joe")
    called = []
    r = ad.delete_account(db_session, u, called.append, now=T0)
    assert r.provider_done and called == ["sub-1"]
    assert db_session.query(User).count() == 0 and db_session.query(AuthSession).count() == 0
    assert s.validate(db_session, token, now=T0) is None
    g = db_session.query(EntitlementGrant).one()
    assert g.subject == ad.anonymous_subject(uid) and uid not in g.subject  # audit line kept, person not identifiable
    assert not ent.has_capability(db_session, uid, "team_workspace")


def test_grants_can_be_deleted_instead_of_anonymized(db_session):
    u = make_user(db_session)
    ent.grant(db_session, str(u.id), "research", days=30, granted_by="joe")
    ad.delete_account(db_session, u, lambda sub: None, keep_anonymized_grants=False, now=T0)
    assert db_session.query(EntitlementGrant).count() == 0


def test_a_provider_failure_leaves_a_tombstone_with_no_email_and_a_retry_finishes_it(db_session):
    u = make_user(db_session)

    def boom(sub):
        raise RuntimeError("provider down")

    r = ad.delete_account(db_session, u, boom, now=T0)
    assert r.local_done and not r.provider_done
    row = db_session.query(User).one()
    assert row.status == "deleted" and row.email is None
    assert ad.retry_provider_deletions(db_session, boom) == 0
    assert ad.retry_provider_deletions(db_session, lambda sub: None) == 1
    assert db_session.query(User).count() == 0


def test_purge_removes_only_old_session_rows_and_never_verified_accounts(db_session):
    keep = make_user(db_session, "keep")
    old = make_user(db_session, "old")
    for u in (keep, old):
        u.created_at = T0 - timedelta(days=100)
    keep.last_sign_in_at = T0 - timedelta(days=50)  # signed in once: a real account
    db_session.commit()
    tok, row = s.create_session(db_session, keep, s.SignInResult(frozenset({"pwd"})), now=T0 - timedelta(days=200))
    row.revoked_at = T0 - timedelta(days=60)
    live_tok, live = s.create_session(db_session, keep, s.SignInResult(frozenset({"pwd"})), now=T0)
    db_session.commit()
    out = ad.purge_expired(db_session, ad.Retention(), now=T0 + timedelta(days=1))
    assert out == {"sessions": 1, "unverified_accounts": 1}
    assert db_session.query(User).one().cognito_sub == "keep"
    assert db_session.query(AuthSession).one().id == live.id
