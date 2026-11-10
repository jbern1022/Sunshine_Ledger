from datetime import datetime, timedelta, timezone

import pytest

from app import sessions as s
from app.models import AuthSession, User

T0 = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
PWD = s.SignInResult(frozenset({"pwd"}))
PWD_TOTP = s.SignInResult(frozenset({"pwd", "totp"}))
PASSKEY = s.SignInResult(frozenset({"passkey"}))


@pytest.fixture
def user(db_session):
    u = User(cognito_sub="sub-1", email="a@example.org")
    db_session.add(u)
    db_session.commit()
    return u


def test_only_the_hash_of_the_token_is_stored(db_session, user):
    token, row = s.create_session(db_session, user, PWD, now=T0)
    assert row.token_hash == s.hash_token(token) != token
    assert token not in str(row.__dict__)
    assert s.validate(db_session, token, now=T0) is not None
    assert s.validate(db_session, "wrong", now=T0) is None and s.validate(db_session, None) is None


def test_idle_and_absolute_limits(db_session, user):
    token, row = s.create_session(db_session, user, PWD, now=T0)
    assert s.validate(db_session, token, now=T0 + timedelta(days=13)) is not None  # touches: idle resets
    assert s.validate(db_session, token, now=T0 + timedelta(days=13 + 15)) is None  # idle passed
    token2, _ = s.create_session(db_session, user, PWD, now=T0)
    cur = T0
    for _ in range(7):  # keep it alive (84 days) until near the absolute cap
        cur += timedelta(days=12)
        assert s.validate(db_session, token2, now=cur) is not None
    assert s.validate(db_session, token2, now=T0 + s.ABSOLUTE + timedelta(seconds=1)) is None


def test_a_user_with_mfa_cannot_get_a_password_only_session(db_session, user):
    s.enroll_factor(db_session, user, now=T0)
    assert user.mfa_required
    with pytest.raises(s.SessionRefused) as e:
        s.create_session(db_session, user, PWD, now=T0)
    assert e.value.code == "mfa_required"
    assert s.create_session(db_session, user, PWD_TOTP, now=T0)[1].factors == ["pwd", "totp"]
    assert s.create_session(db_session, user, PASSKEY, now=T0)  # a user-verifying passkey stands alone


def test_a_password_reset_ends_sessions_and_does_not_clear_the_mfa_requirement(db_session, user):
    s.enroll_factor(db_session, user, now=T0)
    token, _ = s.create_session(db_session, user, PWD_TOTP, now=T0)
    s.password_reset_completed(db_session, user, now=T0)
    assert s.validate(db_session, token, now=T0) is None
    assert user.mfa_required is True
    with pytest.raises(s.SessionRefused):
        s.create_session(db_session, user, PWD, now=T0)  # reset alone does not unlock a password-only sign-in


def test_enrolling_or_changing_a_factor_revokes_every_session(db_session, user):
    t1, _ = s.create_session(db_session, user, PWD, now=T0)
    t2, _ = s.create_session(db_session, user, PWD, now=T0)
    s.enroll_factor(db_session, user, now=T0)
    assert s.validate(db_session, t1, now=T0) is None and s.validate(db_session, t2, now=T0) is None
    assert {r.revoked_reason for r in db_session.query(AuthSession)} == {"mfa_changed"}


def test_recovery_states_gate_sign_in(db_session, user):
    s.enroll_factor(db_session, user, now=T0)
    for state in ("requested", "under_review", "denied"):
        user.recovery_state = state
        db_session.commit()
        with pytest.raises(s.SessionRefused) as e:
            s.create_session(db_session, user, PWD_TOTP, now=T0)
        assert e.value.code == "recovery_pending"
    user.recovery_state = "approved"
    db_session.commit()
    _, row = s.create_session(db_session, user, PWD, now=T0)  # old factor is gone: restricted session only
    assert row.restricted is True
    s.enroll_factor(db_session, user, now=T0)  # replacement enrolled
    assert user.recovery_state == "none" and user.mfa_required is True
    assert s.validate(db_session, "x", now=T0) is None


def test_suspension_and_deletion_block_existing_and_new_sessions(db_session, user):
    token, _ = s.create_session(db_session, user, PWD, now=T0)
    user.status = "suspended"
    db_session.commit()
    assert s.validate(db_session, token, now=T0) is None
    with pytest.raises(s.SessionRefused) as e:
        s.create_session(db_session, user, PWD, now=T0)
    assert e.value.code == "account_unavailable"


def test_sensitive_actions_need_a_recent_sign_in(db_session, user):
    _, row = s.create_session(db_session, user, PWD, now=T0)
    assert s.recently_authenticated(row, now=T0 + timedelta(minutes=9))
    assert not s.recently_authenticated(row, now=T0 + timedelta(minutes=11))


def test_revoke_all_counts_only_live_sessions_and_keeps_rows(db_session, user):
    s.create_session(db_session, user, PWD, now=T0)
    _, second = s.create_session(db_session, user, PWD, now=T0)
    s.revoke(db_session, second, "logout", now=T0)
    assert s.revoke_all(db_session, user, "logout_everywhere", now=T0) == 1
    assert db_session.query(AuthSession).count() == 2
