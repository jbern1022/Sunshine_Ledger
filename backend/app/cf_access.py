"""Who is behind an admin request, according to Cloudflare Access.

Access fronts every admin path (docs/ADMIN_ACCESS_AUDIT.md) and adds a JWT,
`Cf-Access-Jwt-Assertion`, signed with the team's keys and naming the person
who passed its one-time-PIN login. Verifying it here gives each review a real
reviewer (audit gap 2: every action used to be recorded as `admin`), and with
CF_ACCESS_REQUIRED=true it also refuses any admin request that did not come
through Access at all.

The plain `Cf-Access-Authenticated-User-Email` header is NOT trusted: anyone
who reaches the origin could set it. Only the signed token counts.

Unconfigured (no team domain: dev, tests, the standby before it's set) means
the header is ignored and behaviour is exactly as before.
"""

from __future__ import annotations

import functools

import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBasicCredentials

from app.config import settings

HEADER = "cf-access-jwt-assertion"


@functools.lru_cache(maxsize=4)
def _jwks(team_domain: str) -> jwt.PyJWKClient:
    # Keys rotate; PyJWKClient refetches on an unknown kid and caches for an hour.
    return jwt.PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs", cache_keys=True, lifespan=3600)


def _signing_key(token: str):
    return _jwks(settings.cf_access_team_domain).get_signing_key_from_jwt(token).key


def _configured() -> bool:
    return bool(settings.cf_access_team_domain and settings.cf_access_aud)


def verified_email(token: str) -> str:
    """The email in a valid Access token; raises jwt.PyJWTError otherwise."""
    audiences = [a.strip() for a in settings.cf_access_aud.split(",") if a.strip()]
    claims = jwt.decode(
        token,
        _signing_key(token),
        algorithms=["RS256"],
        audience=audiences,
        issuer=f"https://{settings.cf_access_team_domain}",
        options={"require": ["exp", "iat", "iss", "aud"]},
    )
    email = claims.get("email")
    if not email:
        raise jwt.InvalidTokenError("no email claim")
    return str(email)[:100]


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def admin_reviewer(request: Request, credentials: HTTPBasicCredentials) -> str:
    """The name to record for an admin action (Basic auth already passed).

    A present-but-invalid token is always refused: that is either an attack or
    a misconfiguration, and neither should be recorded as a real person."""
    if not _configured():
        return credentials.username
    token = request.headers.get(HEADER)
    if token:
        try:
            return verified_email(token)
        except Exception as exc:  # noqa: BLE001 -- any decode/key-fetch failure fails closed
            raise _refuse("Cloudflare Access token is not valid") from exc
    if settings.cf_access_required:
        raise _refuse("Sign in through Cloudflare Access")
    return credentials.username
