"""Shared retry-with-backoff for pipeline HTTP calls.

The Aug 21-24 nightly ingestion outage (see docs/RUNBOOK.md) sat on a
network/API hiccup with no retry -- one bad request and the whole run
died, discovered only because someone happened to check the log.
`with_retry` gives every pipeline client the same three-attempt,
30/60/120s backoff so a single transient failure can no longer take
down a whole ingestion run by itself.

Deliberately narrow about what counts as "retry-worthy": connection-level
failures and 5xx responses are the server's/network's problem and often
resolve themselves. A 4xx is the request's problem -- retrying an
unauthorized or malformed request three times just delays the same
failure, so those raise immediately.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRY_DELAYS_SECONDS: tuple[float, ...] = (30.0, 60.0, 120.0)

_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def with_retry(fn: Callable[[], T], *, description: str, delays: tuple[float, ...] = RETRY_DELAYS_SECONDS) -> T:
    """Call `fn()`, retrying on transient network/5xx failures.

    `description` is just for the log line (e.g. "LegiScan getBill 1234") --
    this has no knowledge of what `fn` actually does.

    Raises the last exception once delays are exhausted, so a caller that
    does nothing extra behaves exactly as it did before: the ingestion
    script's existing `set -e` / non-zero exit / Uptime Kuma heartbeat
    failure path still fires, unchanged. This only reduces how often that
    path gets reached for a failure that would have cleared itself up in
    a minute or two.
    """
    attempts = len(delays) + 1
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 -- re-raised below if not retryable/exhausted
            if not _is_retryable(exc) or attempt == attempts:
                raise
            delay = delays[attempt - 1]
            logger.warning(
                "%s failed (attempt %d/%d): %s -- retrying in %.0fs",
                description,
                attempt,
                attempts,
                exc,
                delay,
            )
            last_exc = exc
            time.sleep(delay)

    # Unreachable: the loop always either returns or raises above.
    assert last_exc is not None
    raise last_exc
