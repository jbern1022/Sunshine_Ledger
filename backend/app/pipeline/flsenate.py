"""Fetch Florida Legislature documents from flsenate.gov instead of LegiScan.

Every document LegiScan serves for a Florida bill -- bill text versions,
committee staff analyses, amendments -- is a public file on flsenate.gov,
and the session dataset gives each one's URL (`state_link`). Fetching it
there costs no LegiScan calls, which matter from 2026-10-01 (10,000 a
month). Verified 2026-09-29: HB 1389 filed PDF, SB 102 enrolled HTML, HB 565
enrolled PDF and an HB 565 staff analysis all extract byte-for-byte the same
as LegiScan's copies.

Politeness: robots.txt allows /Session/ with `Crawl-delay: 10`, so requests
are spaced at least 10 seconds apart (~360 documents an hour), with an
honest User-Agent.

A missing document is a soft 404: HTTP 200 with the site's HTML page
saying the file was "not found for this bill" (House bills have no HTML
version, and old supplement links rotate). Those are rejected here, and
callers fall back to LegiScan.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = {"www.flsenate.gov", "flsenate.gov", "www.myfloridahouse.gov", "myfloridahouse.gov"}
CRAWL_DELAY = 10.0
USER_AGENT = "SunshineLedger/1.0 (nonprofit civic transparency site; https://sunshineledger.josephbernal.com)"
_SOFT_404 = b"not found for this bill"

# Documents fetched / failed this process, printed with the LegiScan counts.
FETCHES: Counter[str] = Counter()

_last_request = 0.0
_budget: int | None = None
_client: httpx.Client | None = None
_sleep = time.sleep
_clock = time.monotonic


class NotADocument(Exception):
    """The URL didn't return the document (soft 404, wrong type, bad host)."""


class BudgetExhausted(Exception):
    """This run's document budget is spent; leave the rest for the next run."""


def set_budget(documents: int | None) -> None:
    """Cap the documents this process may fetch (None: no cap). The nightly
    job sets one so a busy night can't run for hours at 10 s a document."""
    global _budget
    _budget = documents


def usage_summary() -> str:
    return f"flsenate.gov documents this run: {FETCHES['fetched']} fetched, {FETCHES['failed']} failed"


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True)
    return _client


def _wait_turn() -> None:
    global _last_request
    wait = _last_request + CRAWL_DELAY - _clock()
    if wait > 0:
        _sleep(wait)
    _last_request = _clock()


def fetch_document(url: str) -> tuple[bytes, str]:
    """(body, content type) of one document, which is "pdf" or "html".

    Raises NotADocument when the URL isn't an allowed host or doesn't return
    a real document, BudgetExhausted when the run's budget is spent, and
    httpx errors on network failure.
    """
    host = urlparse(url).hostname or ""
    if host.lower() not in ALLOWED_HOSTS:
        raise NotADocument(f"not a Florida Legislature URL: {url}")
    if _budget is not None and FETCHES["fetched"] + FETCHES["failed"] >= _budget:
        raise BudgetExhausted(f"flsenate.gov budget of {_budget} documents reached")

    _wait_turn()
    try:
        response = _http().get(url)
        response.raise_for_status()
        body = response.content
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if body.startswith(b"%PDF"):
            kind = "pdf"
        elif content_type == "text/html" and _SOFT_404 not in body:
            kind = "html"
        else:
            raise NotADocument(f"{url} returned {content_type or 'no content type'}, not the document")
    except Exception:
        FETCHES["failed"] += 1
        raise
    FETCHES["fetched"] += 1
    return body, kind
