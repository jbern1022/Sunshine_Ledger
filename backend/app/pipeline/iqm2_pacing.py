"""Pacing and a request budget for scraping Granicus iQM2 portals.

Every iQM2 tenant's robots.txt says `Crawl-delay: 60`. The approved policy
(Todoist 6hrFq2mH5Pj68qgG, 2026-10-29): one request every 60 seconds by
default, a cap on requests per run, a wall-clock cap, and progress that
survives between runs. Going faster than the portal's own Crawl-delay needs
written permission from the portal, so the delay it publishes is a floor:
configuration can slow the scraper down, never speed it past that.
"""

from __future__ import annotations

import time
from typing import Callable


class BudgetExhausted(Exception):
    """The run used up its request or time budget. Not an error: the
    checkpoint is saved and the next run carries on."""


class Pacer:
    def __init__(
        self,
        *,
        pace_seconds: float,
        max_requests: int,
        max_seconds: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.pace = pace_seconds
        self.max_requests = max_requests
        self.requests = 0
        self._sleep, self._clock = sleep, clock
        self._started = clock()
        self._deadline = None if max_seconds is None else self._started + max_seconds
        self._last: float | None = None

    def raise_floor(self, crawl_delay: float) -> None:
        """Never go faster than the portal's published Crawl-delay."""
        self.pace = max(self.pace, crawl_delay)

    def before_request(self) -> None:
        """Wait out the spacing, then count the request. Raises
        BudgetExhausted if the request cap is reached or the wait itself
        would run past the time budget."""
        if self.requests >= self.max_requests:
            raise BudgetExhausted(f"request cap of {self.max_requests} reached")
        wait = 0.0 if self._last is None else max(0.0, self._last + self.pace - self._clock())
        if self._deadline is not None and self._clock() + wait >= self._deadline:
            raise BudgetExhausted("time budget reached")
        if wait:
            self._sleep(wait)
        self._last = self._clock()
        self.requests += 1
