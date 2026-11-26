"""Amazon Cognito implementation of `IdentityProvider` (docs/ADR_READER_AUTH_COGNITO.md).

Used by app/api/auth.py when the Cognito settings are present (accounts stay off behind
REGISTRATION_OPEN). Unit-tested with botocore's Stubber, and checked against the real dev pool
us-east-2_IDPul5NQZ on 2026-11-25 with a throwaway user: the user-password flow with an email-based
SECRET_HASH, TOTP setup and the MFA challenge, and AdminDeleteUser called with the user's `sub` all
behaved as written here. Still UNVERIFIED (see the ADR): a TOTP-enrolled user who also registers a
passkey.

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

from app.identity import InvalidCredentials, MfaAlreadyEnabled, ProviderOutcome, WeakPassword

# Errors that mean "these credentials or this code did not work". Anything else is a real fault and
# propagates (the caller maps unexpected exceptions to a generic 5xx, never to a sign-in answer).
_CREDENTIAL_ERRORS = {
    "NotAuthorizedException", "UserNotFoundException", "UserNotConfirmedException", "CodeMismatchException",
    "ExpiredCodeException", "InvalidPasswordException", "PasswordResetRequiredException", "LimitExceededException",
    "TooManyFailedAttemptsException", "TooManyRequestsException", "InvalidParameterException",
    "EnableSoftwareTokenMFAException",  # VerifySoftwareToken: the code did not match
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

    def _fresh_access_token(self, email: str, password: str) -> str:
        """Re-authenticate for a factor change. Only an account WITHOUT TOTP gets tokens straight away;
        one that has it answers with the TOTP challenge, which enrollment does not continue."""
        params = {"USERNAME": email, "PASSWORD": password, **self._secret_hash(email)}
        r = self._call(
            self._c.initiate_auth, ClientId=self._client_id, AuthFlow="USER_PASSWORD_AUTH", AuthParameters=params,
        )
        if r.get("ChallengeName") == "SOFTWARE_TOKEN_MFA":
            raise MfaAlreadyEnabled()
        if r.get("ChallengeName") or "AuthenticationResult" not in r:
            raise InvalidCredentials()
        return r["AuthenticationResult"]["AccessToken"]

    def begin_totp_setup(self, email: str, password: str) -> tuple[str, str]:
        token = self._fresh_access_token(email, password)
        sub = self._vouch(token, frozenset({"pwd"})).sub
        secret = self._call(self._c.associate_software_token, AccessToken=token)["SecretCode"]
        return sub, secret  # the token goes out of scope here: nothing keeps it

    def finish_totp_setup(self, email: str, password: str, code: str) -> str:
        token = self._fresh_access_token(email, password)
        sub = self._vouch(token, frozenset({"pwd"})).sub
        r = self._call(
            self._c.verify_software_token, AccessToken=token, UserCode=code, FriendlyDeviceName="Sunshine Ledger",
        )
        if r.get("Status") != "SUCCESS":
            raise InvalidCredentials()
        self._call(
            self._c.set_user_mfa_preference, AccessToken=token,
            SoftwareTokenMfaSettings={"Enabled": True, "PreferredMfa": True},
        )
        return sub

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

    def sign_up(self, email: str, password: str) -> None:
        try:
            self._c.sign_up(
                ClientId=self._client_id, Username=email, Password=password,
                UserAttributes=[{"Name": "email", "Value": email}], **self._secret_hash(email),
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "UsernameExistsException":
                return  # indistinguishable from a new sign-up; the existing owner is not told
            if code == "InvalidPasswordException":
                raise WeakPassword() from exc
            if code in _CREDENTIAL_ERRORS:
                raise InvalidCredentials() from exc
            raise

    def confirm_sign_up(self, email: str, code: str) -> None:
        self._call(self._c.confirm_sign_up, ClientId=self._client_id, Username=email, ConfirmationCode=code, **self._secret_hash(email))

    def resend_confirmation(self, email: str) -> None:
        try:
            self._c.resend_confirmation_code(ClientId=self._client_id, Username=email, **self._secret_hash(email))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in _CREDENTIAL_ERRORS | {"UsernameExistsException"}:
                raise

    def request_password_reset(self, email: str) -> None:
        try:
            self._c.forgot_password(ClientId=self._client_id, Username=email, **self._secret_hash(email))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in _CREDENTIAL_ERRORS:
                raise

    def delete_user(self, sub: str) -> None:
        # Admin calls accept the user's `sub` as Username in this pool configuration (checked in the
        # dev pool, 2026-11-25).
        try:
            self._c.admin_delete_user(UserPoolId=self._pool, Username=sub)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
                return  # already gone: deletion is idempotent
            raise
