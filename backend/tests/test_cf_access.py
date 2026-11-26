"""Admin identity from Cloudflare Access (docs/ADMIN_ACCESS_AUDIT.md, gap 2).

Cloudflare Access fronts every admin path and signs a JWT
(Cf-Access-Jwt-Assertion) naming who logged in. The API verifies it and
records that email as the reviewer instead of the shared Basic username.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import cf_access
from app.config import settings

TEAM = "example-team.cloudflareaccess.com"
AUD = "a" * 64
BASIC = ("testadmin", "testpass")

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(*, key=_KEY, aud=AUD, iss=f"https://{TEAM}", email="joe@example.org", exp_in=600):
    now = int(time.time())
    claims = {"aud": [aud], "iss": iss, "email": email, "iat": now, "exp": now + exp_in, "sub": "abc"}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture()
def access(monkeypatch):
    monkeypatch.setattr(settings, "cf_access_team_domain", TEAM)
    monkeypatch.setattr(settings, "cf_access_aud", AUD)
    monkeypatch.setattr(settings, "cf_access_required", False)
    monkeypatch.setattr(cf_access, "_signing_key", lambda _token: _KEY.public_key())


def queue(client, tok=None):
    headers = {"Cf-Access-Jwt-Assertion": tok} if tok else {}
    return client.get("/promises/admin/queue", auth=BASIC, headers=headers)


def test_valid_token_names_the_reviewer(access):
    assert cf_access.verified_email(token()) == "joe@example.org"


@pytest.mark.parametrize(
    "bad",
    [
        lambda: token(key=_OTHER),                       # forged signature
        lambda: token(aud="b" * 64),                     # another Access app
        lambda: token(iss="https://evil.cloudflareaccess.com"),
        lambda: token(exp_in=-60),                       # expired
        lambda: "not-a-jwt",
    ],
)
def test_bad_tokens_are_refused(access, client, bad):
    assert queue(client, bad()).status_code == 403


def test_valid_token_passes_the_admin_route(access, client):
    assert queue(client, token()).status_code == 200


def test_no_token_still_works_while_not_required(access, client):
    assert queue(client).status_code == 200


def test_no_token_is_refused_once_required(access, client, monkeypatch):
    monkeypatch.setattr(settings, "cf_access_required", True)
    assert queue(client).status_code == 403
    assert queue(client, token()).status_code == 200


def test_basic_auth_is_still_checked_behind_access(access, client):
    r = client.get("/promises/admin/queue", auth=("testadmin", "wrong"), headers={"Cf-Access-Jwt-Assertion": token()})
    assert r.status_code == 401


def test_unconfigured_access_ignores_the_header(client):
    # Dev and tests: no team domain, so behaviour is exactly as before.
    assert queue(client, "anything").status_code == 200


def test_reviewer_is_the_access_email(access):
    from fastapi.security import HTTPBasicCredentials
    from starlette.requests import Request

    req = Request({"type": "http", "headers": [(b"cf-access-jwt-assertion", token().encode())]})
    assert cf_access.admin_reviewer(req, HTTPBasicCredentials(username="testadmin", password="x")) == "joe@example.org"
    plain = Request({"type": "http", "headers": []})
    assert cf_access.admin_reviewer(plain, HTTPBasicCredentials(username="testadmin", password="x")) == "testadmin"
