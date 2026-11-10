"""The seam between our sessions and an identity provider (docs/ADR_READER_AUTH_COGNITO.md).

`IdentityProvider` is what we need from Cognito, as a small protocol. The real adapter (boto3 or the
Cognito API, in a dev user pool) does not exist yet; `tests/fakes_identity.py` is a fake that lets every rule
below be tested without AWS. Nothing here has a route.

The rules this layer owns:

* Responses never reveal whether an address has an account: a wrong password and an unknown address
  raise the same `AuthFailed("invalid_credentials")`.
* The provider says who proved what (`factors`); WE decide whether a session may exist
  (`sessions.create_session`), including the MFA gate that the provider's optional-MFA pool cannot enforce.
* The provider's subject maps to our `users` row, created on the first successful, verified sign-in.
  Authorization is by our id, never the email.
* Passwords and one-time codes pass through to the provider and are never stored, logged or returned.
* A password reset ends all our sessions and does not clear the MFA requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import sessions
from app.models import AuthSession, User


class AuthFailed(Exception):
    """Sign-in did not succeed. `code` is safe to show; it is deliberately coarse."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProviderOutcome:
    """What the provider reports after checking credentials. Either `factors` is set (sign-in complete)
    or `challenge` is set (a second step is needed; `challenge_token` continues it)."""

    sub: str
    email: str | None
    email_verified: bool
    factors: frozenset[str] = frozenset()
    challenge: str | None = None  # "totp"
    challenge_token: str | None = None


class IdentityProvider(Protocol):
    def authenticate(self, email: str, password: str) -> ProviderOutcome: ...  # raises InvalidCredentials
    def verify_totp(self, challenge_token: str, code: str) -> ProviderOutcome: ...  # raises InvalidCredentials
    def confirm_password_reset(self, email: str, code: str, new_password: str) -> str: ...  # returns sub
    def delete_user(self, sub: str) -> None: ...


class InvalidCredentials(Exception):
    """Raised by a provider for any credential or code failure (it must not distinguish the causes)."""


def _user_for(db: Session, outcome: ProviderOutcome) -> User:
    if not outcome.email_verified:
        raise AuthFailed("email_not_verified")
    user = db.execute(select(User).where(User.cognito_sub == outcome.sub)).scalar_one_or_none()
    if user is None:
        user = User(cognito_sub=outcome.sub, email=outcome.email)
        db.add(user)
        db.commit()
    elif outcome.email and user.email != outcome.email:
        user.email = outcome.email  # the verified address can change at the provider; the id does not
        db.commit()
    return user


@dataclass(frozen=True)
class SignInStep:
    """Either a session token (done) or a challenge to answer."""

    token: str | None = None
    challenge: str | None = None
    challenge_token: str | None = None


def _finish(db: Session, outcome: ProviderOutcome) -> SignInStep:
    user = _user_for(db, outcome)
    try:
        token, _ = sessions.create_session(db, user, sessions.SignInResult(outcome.factors))
    except sessions.SessionRefused as exc:
        # Say why only when it helps the person act and tells an attacker nothing new: they have
        # already proved the password to get here.
        raise AuthFailed(exc.code) from exc
    return SignInStep(token=token)


def sign_in(db: Session, provider: IdentityProvider, email: str, password: str) -> SignInStep:
    try:
        outcome = provider.authenticate(email, password)
    except InvalidCredentials as exc:
        raise AuthFailed("invalid_credentials") from exc
    if outcome.challenge:
        return SignInStep(challenge=outcome.challenge, challenge_token=outcome.challenge_token)
    return _finish(db, outcome)


def answer_totp(db: Session, provider: IdentityProvider, challenge_token: str, code: str) -> SignInStep:
    try:
        outcome = provider.verify_totp(challenge_token, code)
    except InvalidCredentials as exc:
        raise AuthFailed("invalid_credentials") from exc
    if outcome.challenge:
        raise AuthFailed("invalid_credentials")  # a second challenge is not a flow we support: fail closed
    return _finish(db, outcome)


def reset_password(db: Session, provider: IdentityProvider, email: str, code: str, new_password: str) -> None:
    """Complete a reset at the provider, then end every session of that account. Does not touch
    `mfa_required`: the next sign-in still needs the second factor."""
    try:
        sub = provider.confirm_password_reset(email, code, new_password)
    except InvalidCredentials as exc:
        raise AuthFailed("invalid_credentials") from exc
    user = db.execute(select(User).where(User.cognito_sub == sub)).scalar_one_or_none()
    if user is not None:
        sessions.password_reset_completed(db, user)


def sign_out(db: Session, token: str | None) -> None:
    row = sessions.validate(db, token, touch=False)
    if row is not None:
        sessions.revoke(db, row, "logout")


def sign_out_everywhere(db: Session, token: str | None) -> int:
    row = sessions.validate(db, token, touch=False)
    if row is None:
        return 0
    user = db.get(User, row.user_id)
    return sessions.revoke_all(db, user, "logout_everywhere") if user else 0
