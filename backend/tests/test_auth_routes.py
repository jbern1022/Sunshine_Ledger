import logging

import pytest

from app.api.auth import CSRF_COOKIE, SESSION_COOKIE, get_identity_provider
from app.config import settings
from app.main import app
from app.models import AuthSession, User
from tests.fakes_identity import FakeProvider


@pytest.fixture
def provider():
    p = FakeProvider()
    p.add("a@example.org", "pw-1")
    return p


@pytest.fixture
def on(monkeypatch, provider):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "session_cookie_secure", False)  # TestClient talks plain http
    app.dependency_overrides[get_identity_provider] = lambda: provider
    yield
    app.dependency_overrides.pop(get_identity_provider, None)


def sign_in(client, email="a@example.org", password="pw-1"):
    return client.post("/auth/sign-in", json={"email": email, "password": password})


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}


def test_everything_is_a_404_while_accounts_are_switched_off(client):
    for method, path in (("get", "/auth/me"), ("post", "/auth/sign-in"), ("get", "/watchlist"), ("post", "/auth/me/delete")):
        assert getattr(client, method)(path).status_code == 404


def test_sign_in_sets_an_httponly_session_cookie_and_a_readable_csrf_cookie(client, on):
    r = sign_in(client)
    assert r.status_code == 200 and r.json() == {"signed_in": True}
    set_cookie = " ".join(r.headers.get_list("set-cookie")).lower()
    assert SESSION_COOKIE in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
    sess = [c for c in r.headers.get_list("set-cookie") if c.startswith(SESSION_COOKIE)][0].lower()
    csrf_c = [c for c in r.headers.get_list("set-cookie") if c.startswith(CSRF_COOKIE)][0].lower()
    assert "httponly" in sess and "httponly" not in csrf_c
    me = client.get("/auth/me").json()
    assert me["email"] == "a@example.org" and me["second_factor_required"] is False


def test_bad_credentials_are_one_uniform_401_and_set_no_cookie(client, on):
    for email, pw in (("nobody@example.org", "x"), ("a@example.org", "wrong")):
        r = sign_in(client, email, pw)
        assert r.status_code == 401 and r.json()["detail"] == "invalid_credentials" and not r.headers.get_list("set-cookie")


def test_no_password_or_code_reaches_the_logs_or_the_response(client, on, caplog, provider):
    caplog.set_level(logging.DEBUG)
    r = sign_in(client, password="pw-1")
    assert "pw-1" not in r.text and "pw-1" not in caplog.text
    provider.add("m@example.org", "pw-2", totp="987654")
    step = sign_in(client, "m@example.org", "pw-2").json()
    r2 = client.post("/auth/totp", json={"challenge_token": step["challenge_token"], "code": "987654"})
    assert r2.status_code == 200 and "987654" not in caplog.text and "pw-2" not in caplog.text


def test_totp_flow_over_http(client, on, provider):
    provider.add("m@example.org", "pw-2", totp="123456")
    step = sign_in(client, "m@example.org", "pw-2").json()
    assert step["signed_in"] is False and step["challenge"] == "totp"
    assert client.get("/auth/me").status_code == 401  # a challenge is not a session
    bad = client.post("/auth/totp", json={"challenge_token": step["challenge_token"], "code": "000000"})
    assert bad.status_code == 401
    step = sign_in(client, "m@example.org", "pw-2").json()
    ok = client.post("/auth/totp", json={"challenge_token": step["challenge_token"], "code": "123456"})
    assert ok.status_code == 200 and client.get("/auth/me").json()["factors"] == ["pwd", "totp"]


def test_state_changing_routes_need_the_csrf_token_and_a_trusted_origin(client, on):
    sign_in(client)
    assert client.post("/auth/sign-out").status_code == 403
    assert client.post("/auth/sign-out", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    h = csrf(client)
    assert client.post("/auth/sign-out", headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/auth/me").status_code == 200  # none of the failures ended the session
    assert client.post("/auth/sign-out", headers={**h, "Origin": settings.cors_allowed_origins_list[0]}).status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_sign_out_everywhere_ends_other_sessions(client, on):
    sign_in(client)
    other = client.cookies.get(SESSION_COOKIE)
    client.post("/auth/sign-out-all", headers=csrf(client))
    client.cookies.set(SESSION_COOKIE, other)
    assert client.get("/auth/me").status_code == 401


def test_password_reset_ends_sessions_and_keeps_the_mfa_requirement(client, on, provider, db_session):
    sign_in(client)
    user = db_session.query(User).one()
    from app import sessions
    sessions.enroll_factor(db_session, user)
    provider.reset_codes["a@example.org"] = "999"
    r = client.post("/auth/password-reset/confirm", json={"email": "a@example.org", "code": "999", "new_password": "new-pw"})
    assert r.status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert sign_in(client, password="new-pw").status_code == 403  # password-only is refused: second factor required
    assert sign_in(client, password="new-pw").json()["detail"] == "mfa_required"


def test_watchlist_round_trip_with_csrf_and_isolation(client, on, bill_factory, provider):
    sign_in(client)
    bill = bill_factory()
    assert client.post("/watchlist", json={"kind": "bill", "target": str(bill.id)}).status_code == 403  # no CSRF
    added = client.post("/watchlist", json={"kind": "bill", "target": str(bill.id)}, headers=csrf(client))
    assert added.status_code == 200
    assert [i["kind"] for i in client.get("/watchlist").json()["items"]] == ["bill"]
    bad = client.post("/watchlist", json={"kind": "bill", "target": "not-a-uuid"}, headers=csrf(client))
    assert bad.status_code == 422
    # a second account cannot remove or see it
    provider.add("b@example.org", "pw-b")
    client.cookies.clear()
    sign_in(client, "b@example.org", "pw-b")
    assert client.get("/watchlist").json()["items"] == []
    wid = added.json()["id"]
    assert client.post(f"/watchlist/{wid}/remove", headers=csrf(client)).json() == {"removed": False}


def test_export_and_delete_with_a_recent_sign_in(client, on, provider, db_session):
    sign_in(client)
    assert client.get("/auth/me/export").json()["account"]["email"] == "a@example.org"
    row = db_session.query(AuthSession).one()
    from datetime import timedelta
    row.auth_time = row.auth_time - timedelta(minutes=30)
    db_session.commit()
    stale = client.post("/auth/me/delete", headers=csrf(client))
    assert stale.status_code == 401 and stale.json()["detail"] == "reauth_required"
    row.auth_time = row.auth_time + timedelta(minutes=30)
    db_session.commit()
    done = client.post("/auth/me/delete", headers=csrf(client))
    assert done.json() == {"deleted": True, "provider_pending": False}
    assert provider.deleted == ["sub-a@example.org"] and db_session.query(User).count() == 0
    assert client.get("/auth/me").status_code == 401


def test_an_unconfigured_provider_is_a_503_not_a_crash(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    for k in ("cognito_region", "cognito_user_pool_id", "cognito_client_id"):
        monkeypatch.setattr(settings, k, "")
    assert sign_in(client).status_code == 503


def test_sign_up_is_closed_until_registration_is_opened(client, on):
    assert client.post("/auth/sign-up", json={"email": "n@example.org", "password": "longenough"}).status_code == 404
    assert client.post("/auth/sign-up/confirm", json={"email": "n@example.org", "code": "111111"}).status_code == 404


def test_sign_up_confirm_sign_in_and_uniform_answers(client, on, monkeypatch, provider):
    monkeypatch.setattr(settings, "registration_open", True)
    new = client.post("/auth/sign-up", json={"email": "n@example.org", "password": "longenough"})
    existing = client.post("/auth/sign-up", json={"email": "a@example.org", "password": "longenough"})
    assert new.status_code == existing.status_code == 200 and new.json() == existing.json() == {"check_your_email": True}
    assert provider.users["a@example.org"]["password"] == "pw-1"  # a sign-up never changes an existing account
    weak = client.post("/auth/sign-up", json={"email": "w@example.org", "password": "short"})
    assert weak.status_code == 422 and weak.json()["detail"] == "weak_password"
    assert sign_in(client, "n@example.org", "longenough").json()["detail"] == "email_not_verified"  # unconfirmed: no session
    assert client.post("/auth/sign-up/confirm", json={"email": "n@example.org", "code": "000000"}).status_code == 401
    assert client.post("/auth/sign-up/confirm", json={"email": "n@example.org", "code": "111111"}).json() == {"confirmed": True}
    assert sign_in(client, "n@example.org", "longenough").status_code == 200


def test_reset_request_looks_the_same_for_unknown_and_known_addresses(client, on, provider):
    a = client.post("/auth/password-reset/request", json={"email": "a@example.org"})
    b = client.post("/auth/password-reset/request", json={"email": "nobody@example.org"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json() == {"check_your_email": True}
    assert provider.reset_codes == {"a@example.org": "999"}
