"""Read-only mode for the pilot-light standby.

An app-wide dependency rather than an outer middleware: the refusal is raised
inside the app, so CORS headers are still added and the site can show the
message instead of a network error.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RETRY_AFTER_SECONDS = 900

MESSAGE = (
    "Sunshine Ledger is temporarily read-only: this is a backup copy while the main server is offline. "
    "Reading works; reports, reviews and account changes are paused. Please try again later."
)


class ReadOnlyError(Exception):
    pass


def reject_writes_when_read_only(request: Request) -> None:
    if settings.read_only and request.method in WRITE_METHODS:
        raise ReadOnlyError()


async def read_only_response(_request: Request, _exc: ReadOnlyError) -> JSONResponse:
    # A handler for a specific exception class runs in Starlette's inner
    # ExceptionMiddleware, i.e. inside CORS, so the 503 stays readable cross-origin.
    return JSONResponse(
        status_code=503,
        content={"detail": MESSAGE, "read_only": True},
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )
