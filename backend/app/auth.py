import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.cf_access import admin_reviewer
from app.config import settings

_security = HTTPBasic()


def require_admin(request: Request, credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """HTTP Basic Auth gate for the small set of admin-only endpoints
    (currently: flag review). Constant-time comparison to avoid a timing
    side-channel on the username/password check. Returns who to record as
    the reviewer.

    Fails closed: if ADMIN_PASSWORD isn't configured, every request is
    rejected rather than falling back to a guessable default.
    """
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin auth not configured",
            headers={"WWW-Authenticate": "Basic"},
        )

    valid_username = secrets.compare_digest(credentials.username, settings.admin_username)
    valid_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    # Behind Cloudflare Access: the reviewer is the verified Access email, not
    # the shared Basic username (app/cf_access.py).
    return admin_reviewer(request, credentials)
