"""Shared logging setup for pipeline CLI entry points.

`logging.basicConfig(level=logging.INFO)` raises the *root* logger's
effective level to INFO, and any logger without its own explicit level
(httpx's included) inherits that. httpx logs every request -- URL included
-- at INFO. For a client like LegiScan's that authenticates via a
`?key=...` query param, that means the API key lands verbatim in whatever
this process logs to (e.g. the nightly ingestion.log).

Every pipeline `__main__` entry point that calls `logging.basicConfig`
should also call `quiet_http_logging()` right after, so nothing it runs
can leak a request URL this way.
"""

from __future__ import annotations

import logging


def quiet_http_logging() -> None:
    """Keep httpx/httpcore's own request logging at WARNING or above.

    Call this after `logging.basicConfig(...)` (or anything else that
    raises the root logger's level) so httpx's per-request INFO logging --
    which includes the full request URL and query string -- never gets
    emitted, regardless of what level the rest of the process logs at.
    """
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
