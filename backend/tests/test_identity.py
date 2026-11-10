import pytest

from app import identity as ident
from app import sessions
from app.models import AuthSession, User
from tests.fakes_identity import FakeProvider


@pytest.fixture
def p():
    f = FakeProvider()
    f.add("a@example.org", "pw-1")
    return f


def test_a_good_sign_in_creates_the_user_once_and_a_session(db_session, p):
    step = ident.sign_in(db_session, p, "a@example.org", "pw-1")
    assert step.token and sessions.validate(db_session, step.token)
    ident.sign_in(db_session, p, "a@example.org", "pw-1")
    assert db_session.query(User).count() == 1 and db_session.query(AuthSession).count() == 2
    assert db_session.query(User).one().cognito_sub == "sub-a@example.org"


def test_unknown_address_and_wrong_password_are_indistinguishable(db_session, p):
    codes = set()
    for email, pw in (("nobody@example.org", "x"), ("a@example.org", "wrong")):
        with pytest.raises(ident.AuthFailed) as e:
            ident.sign_in(db_session, p, email, pw)
        codes.add(e.value.code)
    assert codes == {"invalid_credentials"}
    assert db_session.query(User).count() == 0


def test_an_unverified_email_gets_no_session_and_no_user(db_session, p):
    p.add("u@example.org", "pw", verified=False)
    with pytest.raises(ident.AuthFailed) as e:
        ident.sign_in(db_session, p, "u@example.org", "pw")
    assert e.value.code == "email_not_verified" and db_session.query(User).count() == 0


def test_totp_flow_wrong_replayed_and_right_codes(db_session, p):
    p.add("m@example.org", "pw", totp="123456")
    step = ident.sign_in(db_session, p, "m@example.org", "pw")
    assert step.token is None and step.challenge == "totp"
    with pytest.raises(ident.AuthFailed):
        ident.answer_totp(db_session, p, step.challenge_token, "000000")
    with pytest.raises(ident.AuthFailed):  # the failed attempt consumed the challenge: no guessing on one token
        ident.answer_totp(db_session, p, step.challenge_token, "123456")
    step = ident.sign_in(db_session, p, "m@example.org", "pw")
    done = ident.answer_totp(db_session, p, step.challenge_token, "123456")
    assert done.token and sessions.validate(db_session, done.token).factors == ["pwd", "totp"]
    with pytest.raises(ident.AuthFailed):  # replay
        ident.answer_totp(db_session, p, step.challenge_token, "123456")


def test_the_mfa_gate_holds_even_if_the_provider_would_allow_password_only(db_session, p):
    ident.sign_in(db_session, p, "a@example.org", "pw-1")
    user = db_session.query(User).one()
    sessions.enroll_factor(db_session, user)  # we recorded a factor; the pool's TOTP was then deleted (simulated)
    with pytest.raises(ident.AuthFailed) as e:
        ident.sign_in(db_session, p, "a@example.org", "pw-1")
    assert e.value.code == "mfa_required"


def test_suspended_and_recovering_accounts_are_refused(db_session, p):
    ident.sign_in(db_session, p, "a@example.org", "pw-1")
    user = db_session.query(User).one()
    user.status = "suspended"
    db_session.commit()
    with pytest.raises(ident.AuthFailed) as e:
        ident.sign_in(db_session, p, "a@example.org", "pw-1")
    assert e.value.code == "account_unavailable"
    user.status, user.recovery_state = "active", "under_review"
    db_session.commit()
    with pytest.raises(ident.AuthFailed) as e:
        ident.sign_in(db_session, p, "a@example.org", "pw-1")
    assert e.value.code == "recovery_pending"


def test_reset_ends_sessions_and_keeps_the_mfa_requirement(db_session, p):
    step = ident.sign_in(db_session, p, "a@example.org", "pw-1")
    user = db_session.query(User).one()
    sessions.enroll_factor(db_session, user)
    p.reset_codes["a@example.org"] = "999"
    ident.reset_password(db_session, p, "a@example.org", "999", "new-pw")
    assert sessions.validate(db_session, step.token) is None
    assert db_session.query(User).one().mfa_required is True
    with pytest.raises(ident.AuthFailed):
        ident.reset_password(db_session, p, "a@example.org", "999", "again")  # code is single use


def test_a_changed_provider_email_is_copied_but_the_account_is_the_same(db_session, p):
    ident.sign_in(db_session, p, "a@example.org", "pw-1")
    p.users["b@example.org"] = {**p.users.pop("a@example.org")}
    ident.sign_in(db_session, p, "b@example.org", "pw-1")
    u = db_session.query(User).one()
    assert u.email == "b@example.org" and u.cognito_sub == "sub-a@example.org"


def test_sign_out_and_everywhere(db_session, p):
    t1 = ident.sign_in(db_session, p, "a@example.org", "pw-1").token
    t2 = ident.sign_in(db_session, p, "a@example.org", "pw-1").token
    ident.sign_out(db_session, t1)
    assert sessions.validate(db_session, t1) is None and sessions.validate(db_session, t2)
    t3 = ident.sign_in(db_session, p, "a@example.org", "pw-1").token
    assert ident.sign_out_everywhere(db_session, t3) == 2
    assert sessions.validate(db_session, t2) is None and ident.sign_out_everywhere(db_session, "bad") == 0
