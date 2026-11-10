"""An in-memory identity provider for tests: the behaviours the real adapter must reproduce."""

from app.identity import InvalidCredentials, ProviderOutcome


class FakeProvider:
    def __init__(self):
        self.users = {}  # email -> dict(sub, password, verified, totp_secret)
        self.pending = {}  # challenge_token -> email
        self.deleted = []
        self.reset_codes = {}

    def add(self, email, password, *, sub=None, verified=True, totp=None):
        self.users[email] = {"sub": sub or f"sub-{email}", "password": password, "verified": verified, "totp": totp}

    def authenticate(self, email, password):
        u = self.users.get(email)
        if u is None or u["password"] != password:
            raise InvalidCredentials()
        if u["totp"]:
            token = f"chal-{len(self.pending)}"
            self.pending[token] = email
            return ProviderOutcome(u["sub"], email, u["verified"], challenge="totp", challenge_token=token)
        return ProviderOutcome(u["sub"], email, u["verified"], factors=frozenset({"pwd"}))

    def verify_totp(self, challenge_token, code):
        email = self.pending.pop(challenge_token, None)  # single use: a replayed token fails
        if email is None or self.users[email]["totp"] != code:
            raise InvalidCredentials()
        u = self.users[email]
        return ProviderOutcome(u["sub"], email, u["verified"], factors=frozenset({"pwd", "totp"}))

    def confirm_password_reset(self, email, code, new_password):
        if self.reset_codes.get(email) != code:
            raise InvalidCredentials()
        del self.reset_codes[email]
        self.users[email]["password"] = new_password
        return self.users[email]["sub"]

    def delete_user(self, sub):
        self.deleted.append(sub)
