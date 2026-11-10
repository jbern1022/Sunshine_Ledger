"""Amazon Cognito implementation of `IdentityProvider` (docs/ADR_READER_AUTH_COGNITO.md).

**Not wired and not exercised against a real user pool.** It is written against the documented
`cognito-idp` operations and tested with botocore's Stubber, which proves the requests we make and how
we read the answers, not that a real pool behaves this way. Everything marked UNVERIFIED in the ADR
(passkeys with TOTP, region support, whether admin calls accept a `sub` as the username) still has to be
checked in a dev pool before this is used.

Design choices that follow the ADR:

* The browser never sees Cognito tokens. We call the user-password flow server-side, then ask Cognito to
  vouch for the access token with `GetUser` (so no JWT library or key handling here), read `sub`, `email`
  and `email_verified` from it, and DROP the tokens. Only the outcome leaves this module.
* Any credential or code failure is `InvalidCredentials`, never a more specific error, so nothing
  distinguishes an unknown address from a wrong password. The pool should also have "prevent user
  existence errors" enabled.
* Passwords and codes are passed straight through and never logged or kept.
* Authentication factors reported are only what Cognito proved in this call: "pwd", plus "totp" after a
  software-token challenge. Passkeys are not offered until they have been tested.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from botocore.exceptions import ClientError

from app.identity import InvalidCredentials, ProviderOutcome

# Errors that mean "these credentials or this code did not work". Anything else is a real fault and
# propagates (the caller maps unexpected exceptions to a generic 5xx, never to a sign-in answer).
_CREDENTIAL_ERRORS = {
    "NotAuthorizedException", "UserNotFoundException", "UserNotConfirmedException", "CodeMismatchException",
    "ExpiredCodeException", "InvalidPasswordException", "PasswordResetRequiredException", "LimitExceededException",
    "TooManyFailedAttemptsException", "TooManyRequestsException", "InvalidParameterException",
}


class CognitoProvider:
    def __init__(self, client, user_pool_id: str, client_id: str, client_secret: str | None = None):
        self._c = client  # a boto3 "cognito-idp" client
        self._pool = user_pool_id
        self._client_id = client_id
        self._secret = client_secret

    def _secret_hash(self, username: str) -> dict:
        if not self._secret:
            return {}
        digest = hmac.new(self._secret.encode(), (username + self._client_id).encode(), hashlib.sha256).digest()
        return {"SECRET_HASH": base64.b64encode(digest).decode()}

    def _call(self, fn, **kw):
        try:
            return fn(**kw)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _CREDENTIAL_ERRORS:
                raise InvalidCredentials() from exc
            raise

    def _vouch(self, access_token: str, factors: frozenset[str]) -> ProviderOutcome:
        """Have Cognito validate the access token and tell us who it belongs to; keep no token."""
        user = self._call(self._c.get_user, AccessToken=access_token)
        attrs = {a["Name"]: a["Value"] for a in user.get("UserAttributes", [])}
        sub = attrs.get("sub")
        if not sub:
            raise InvalidCredentials()
        return ProviderOutcome(
            sub=sub, email=attrs.get("email"), email_verified=attrs.get("email_verified") == "true", factors=factors,
        )

    def authenticate(self, email: str, password: str) -> ProviderOutcome:
        params = {"USERNAME": email, "PASSWORD": password, **self._secret_hash(email)}
        r = self._call(
            self._c.initiate_auth, ClientId=self._client_id, AuthFlow="USER_PASSWORD_AUTH", AuthParameters=params,
        )
        challenge = r.get("ChallengeName")
        if challenge == "SOFTWARE_TOKEN_MFA":
            # Cognito's own session string continues the challenge. It is carried with the username so
            # the second step can compute the secret hash; it is not a credential we store.
            return ProviderOutcome(
                sub="", email=email, email_verified=False, challenge="totp", challenge_token=f"{email}\n{r['Session']}",
            )
        if challenge or "AuthenticationResult" not in r:
            raise InvalidCredentials()  # a challenge we do not support: fail closed
        return self._vouch(r["AuthenticationResult"]["AccessToken"], frozenset({"pwd"}))

    def verify_totp(self, challenge_token: str, code: str) -> ProviderOutcome:
        try:
            email, session = challenge_token.split("\n", 1)
        except ValueError as exc:
            raise InvalidCredentials() from exc
        responses = {"USERNAME": email, "SOFTWARE_TOKEN_MFA_CODE": code, **self._secret_hash(email)}
        r = self._call(
            self._c.respond_to_auth_challenge, ClientId=self._client_id, ChallengeName="SOFTWARE_TOKEN_MFA",
            Session=session, ChallengeResponses=responses,
        )
        if r.get("ChallengeName") or "AuthenticationResult" not in r:
            raise InvalidCredentials()
        return self._vouch(r["AuthenticationResult"]["AccessToken"], frozenset({"pwd", "totp"}))

    def confirm_password_reset(self, email: str, code: str, new_password: str) -> str:
        self._call(
            self._c.confirm_forgot_password, ClientId=self._client_id, Username=email, ConfirmationCode=code,
            Password=new_password, **self._secret_hash(email),
        )
        got = self._call(self._c.admin_get_user, UserPoolId=self._pool, Username=email)
        sub = next((a["Value"] for a in got.get("UserAttributes", []) if a["Name"] == "sub"), None)
        if not sub:
            raise InvalidCredentials()
        return sub

    def delete_user(self, sub: str) -> None:
        # UNVERIFIED: admin calls accept the user's `sub` as Username in this pool configuration.
        try:
            self._c.admin_delete_user(UserPoolId=self._pool, Username=sub)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
                return  # already gone: deletion is idempotent
            raise
