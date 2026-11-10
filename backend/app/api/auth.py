"""Reader account routes: sign-in, sign-out, the account itself, and the watchlist.

Everything here answers 404 while `settings.auth_enabled` is false (the default), so deploying this code
exposes nothing. Design: docs/ADR_READER_AUTH_COGNITO.md. The identity provider is a dependency
(`get_identity_provider`): Cognito in production, a fake in tests.

Rules enforced at this edge:

* The browser holds only an opaque, HttpOnly, Secure, SameSite=Lax session cookie. Every state-changing
  request that uses it must also send `X-CSRF-Token` equal to the readable `sl_csrf` cookie (double
  submit), and its Origin, when sent, must be one of the allowed origins.
* Passwords and one-time codes are read from the JSON body, handed to the provider and never logged,
  stored or returned. Sign-in failures are uniform (`invalid_credentials`).
* Sensitive actions (delete the account) require a sign-in within the last 10 minutes
  (`401 reauth_required`).
* No route reads or writes Impact Lens answers; they never leave the browser.

No `from __future__ import annotations` here: the rate-limit decorator wraps the handlers and breaks
postponed annotations (see api/promises.py).
"""

import secrets
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import account_data, identity, sessions, watchlists
from app.config import settings
from app.db import get_db
from app.models import AuthSession, User
from app.rate_limit import limiter

SESSION_COOKIE = "sl_session"
CSRF_COOKIE = "sl_csrf"


def require_enabled() -> None:
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(tags=["accounts"], dependencies=[Depends(require_enabled)])


def get_identity_provider() -> identity.IdentityProvider:
    """The Cognito provider from settings. Overridden in tests."""
    if not (settings.cognito_region and settings.cognito_user_pool_id and settings.cognito_client_id):
        raise HTTPException(status_code=503, detail="Sign-in is not available")
    import boto3

    from app.cognito_provider import CognitoProvider

    client = boto3.client("cognito-idp", region_name=settings.cognito_region)
    return CognitoProvider(client, settings.cognito_user_pool_id, settings.cognito_client_id, settings.cognito_client_secret or None)


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256, repr=False)


class TotpAnswer(BaseModel):
    challenge_token: str = Field(max_length=2000)
    code: str = Field(max_length=12, repr=False)


class ResetConfirm(BaseModel):
    email: str = Field(max_length=320)
    code: str = Field(max_length=12, repr=False)
    new_password: str = Field(max_length=256, repr=False)


class WatchIn(BaseModel):
    kind: str = Field(max_length=10)
    target: str = Field(max_length=80)
    jurisdiction: str = Field(default="", max_length=80)


def _set_cookies(response: Response, token: str) -> None:
    kw = dict(domain=settings.session_cookie_domain or None, secure=settings.session_cookie_secure, samesite="lax", path="/")
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=int(sessions.ABSOLUTE.total_seconds()), **kw)
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), httponly=False, max_age=int(sessions.ABSOLUTE.total_seconds()), **kw)


def _clear_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, domain=settings.session_cookie_domain or None, path="/")


def _fail(exc: identity.AuthFailed) -> HTTPException:
    # Credential problems are 401 with one code; account states are 403 with their own (the password was proven).
    status = 401 if exc.code == "invalid_credentials" else 403
    return HTTPException(status_code=status, detail=exc.code)


def current_session(db: Session = Depends(get_db), sl_session: str | None = Cookie(default=None)) -> AuthSession:
    row = sessions.validate(db, sl_session)
    if row is None:
        raise HTTPException(status_code=401, detail="not_signed_in")
    return row


def csrf_protected(
    request: Request, sl_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None),
) -> None:
    if not sl_csrf or not x_csrf_token or not secrets.compare_digest(sl_csrf, x_csrf_token):
        raise HTTPException(status_code=403, detail="csrf")
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_allowed_origins_list:
        raise HTTPException(status_code=403, detail="csrf")


def _user(db: Session, row: AuthSession) -> User:
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="not_signed_in")
    return user


@router.post("/auth/sign-in")
@limiter.limit("10/minute")
def sign_in(
    request: Request, response: Response, body: Credentials, db: Session = Depends(get_db),
    provider: identity.IdentityProvider = Depends(get_identity_provider),
) -> dict:
    try:
        step = identity.sign_in(db, provider, body.email.strip(), body.password)
    except identity.AuthFailed as exc:
        raise _fail(exc) from exc
    if step.token:
        _set_cookies(response, step.token)
        return {"signed_in": True}
    return {"signed_in": False, "challenge": step.challenge, "challenge_token": step.challenge_token}


@router.post("/auth/totp")
@limiter.limit("10/minute")
def totp(
    request: Request, response: Response, body: TotpAnswer, db: Session = Depends(get_db),
    provider: identity.IdentityProvider = Depends(get_identity_provider),
) -> dict:
    try:
        step = identity.answer_totp(db, provider, body.challenge_token, body.code.strip())
    except identity.AuthFailed as exc:
        raise _fail(exc) from exc
    _set_cookies(response, step.token or "")
    return {"signed_in": True}


@router.post("/auth/password-reset/confirm")
@limiter.limit("5/minute")
def password_reset_confirm(
    request: Request, response: Response, body: ResetConfirm, db: Session = Depends(get_db),
    provider: identity.IdentityProvider = Depends(get_identity_provider),
) -> dict:
    try:
        identity.reset_password(db, provider, body.email.strip(), body.code.strip(), body.new_password)
    except identity.AuthFailed as exc:
        raise _fail(exc) from exc
    _clear_cookies(response)  # every session of that account just ended, including this browser's
    return {"reset": True}


@router.post("/auth/sign-out", dependencies=[Depends(csrf_protected)])
def sign_out(response: Response, db: Session = Depends(get_db), sl_session: str | None = Cookie(default=None)) -> dict:
    identity.sign_out(db, sl_session)
    _clear_cookies(response)
    return {"signed_out": True}


@router.post("/auth/sign-out-all", dependencies=[Depends(csrf_protected)])
def sign_out_all(response: Response, db: Session = Depends(get_db), sl_session: str | None = Cookie(default=None)) -> dict:
    n = identity.sign_out_everywhere(db, sl_session)
    _clear_cookies(response)
    return {"signed_out": True, "sessions_ended": n}


@router.get("/auth/me")
def me(row: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> dict:
    user = _user(db, row)
    return {
        "id": str(user.id), "email": user.email, "second_factor_required": user.mfa_required,
        "restricted": row.restricted, "factors": list(row.factors),
    }


@router.get("/auth/me/export")
def export(row: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> dict:
    return account_data.export_user(db, _user(db, row))


@router.post("/auth/me/delete", dependencies=[Depends(csrf_protected)])
def delete_me(
    response: Response, row: AuthSession = Depends(current_session), db: Session = Depends(get_db),
    provider: identity.IdentityProvider = Depends(get_identity_provider),
) -> dict:
    if not sessions.recently_authenticated(row):
        raise HTTPException(status_code=401, detail="reauth_required")
    if row.restricted:
        raise HTTPException(status_code=403, detail="restricted_session")
    result = account_data.delete_account(db, _user(db, row), provider.delete_user)
    _clear_cookies(response)
    return {"deleted": True, "provider_pending": not result.provider_done}


def _watch_out(w) -> dict:
    return {"id": str(w.id), "kind": w.kind, "target": w.target, "jurisdiction": w.jurisdiction or None}


def _unrestricted(row: AuthSession) -> AuthSession:
    if row.restricted:
        raise HTTPException(status_code=403, detail="restricted_session")
    return row


@router.get("/watchlist")
def list_watchlist(row: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> dict:
    _unrestricted(row)
    return {"items": [_watch_out(w) for w in watchlists.listing(db, _user(db, row))]}


@router.post("/watchlist", dependencies=[Depends(csrf_protected)])
def add_watch(body: WatchIn, row: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> dict:
    _unrestricted(row)
    try:
        return _watch_out(watchlists.add(db, _user(db, row), body.kind, body.target, body.jurisdiction))
    except watchlists.WatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/watchlist/{watch_id}/remove", dependencies=[Depends(csrf_protected)])
def remove_watch(watch_id: uuid.UUID, row: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> dict:
    _unrestricted(row)
    return {"removed": watchlists.remove(db, _user(db, row), watch_id)}
