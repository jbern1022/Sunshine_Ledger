"""A small, polite client for the Congress.gov API (api.congress.gov/v3).

Free key, 5,000 requests an hour; we stay far under with a fixed pause
between calls. Every call goes through the shared retry-with-backoff.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Iterator

import httpx

from app.config import settings
from app.pipeline._retry import with_retry
from app.pipeline.flsenate import USER_AGENT

logger = logging.getLogger(__name__)

BASE_URL = "https://api.congress.gov/v3"
PAGE_SIZE = 250


class CongressApiError(RuntimeError):
    pass


class CongressClient:
    def __init__(self, api_key: str | None = None, *, pause: float = 0.8, sleep: Callable[[float], None] = time.sleep,
                 client: httpx.Client | None = None) -> None:
        self.api_key = api_key or settings.congress_api_key
        if not self.api_key:
            raise CongressApiError("CONGRESS_API_KEY is not set. Free signup: https://api.congress.gov/sign-up/")
        self._pause, self._sleep = pause, sleep
        self._client = client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})
        self.requests = 0

    def get(self, path: str, **params) -> dict:
        def attempt() -> httpx.Response:
            self._sleep(self._pause)
            self.requests += 1
            resp = self._client.get(f"{BASE_URL}{path}", params={**params, "api_key": self.api_key, "format": "json"})
            if resp.status_code >= 500:
                resp.raise_for_status()  # retried with backoff
            return resp

        resp = with_retry(attempt, description=f"Congress.gov GET {path}")
        if resp.status_code == 404:
            return {}
        if resp.status_code == 429:
            raise CongressApiError(f"Congress.gov rate limit reached on {path}; the run can be repeated later and will carry on")
        if resp.status_code != 200:
            # Never put the key in an error message.
            raise CongressApiError(f"Congress.gov {path} returned {resp.status_code}")
        return resp.json()

    def paged(self, path: str, key: str, **params) -> Iterator[dict]:
        """Every item under `key`, following offset pagination."""
        offset = 0
        while True:
            data = self.get(path, limit=PAGE_SIZE, offset=offset, **params)
            items = data.get(key)
            if items is None:  # a renamed list key should not silently read as "no bills"
                lists = [v for k, v in data.items() if isinstance(v, list)]
                items = lists[0] if len(lists) == 1 else []
                if lists and key not in data:
                    logger.warning("Congress.gov %s: expected %r, used the only list in the response", path, key)
            yield from items
            if not items or not (data.get("pagination") or {}).get("next"):
                return
            offset += PAGE_SIZE
