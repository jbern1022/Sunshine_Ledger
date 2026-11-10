"""Polite crawler for winners' own sites (Todoist 6hvxrjGmcGjQ66Pp).

Rules, from the 2026-11-03 owner decisions and the approved iQM2 policy:
  * robots.txt is honoured, including Crawl-delay; a Disallow is recorded
    as `blocked_by_robots`, not worked around.
  * one request per host per `pace` seconds (default 60), different hosts
    interleave; a per-run cap on requests; checkpoints live in the database,
    so a re-run skips what is already snapshotted and carries on.
  * no social platforms, no cross-host redirects, HTML only, 3 MB per page.
  * a site that is gone is recorded offline and routed to the Internet
    Archive copy where one exists (kept apart from our own fetch time).

Usage:
    python -m app.promises.crawler [--max-requests N] [--pace SECONDS] [--site-id UUID]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import OfficialSite, SiteSnapshot
from app.promises.sites import host_of, is_social

logger = logging.getLogger(__name__)

USER_AGENT = (
    "SunshineLedgerBot/1.0 (civic transparency; collects candidates' own published "
    "commitments; https://sunshineledger.josephbernal.com/methodology)"
)
MAX_BYTES = 3 * 1024 * 1024
MAX_PAGES_PER_SITE = 8
ROBOTS_UNREADABLE = "robots.txt could not be read"
ARCHIVE_HOST = "web.archive.org"
ARCHIVE_PACE = 5.0
RETRY_UNAVAILABLE_AFTER = timedelta(days=1)

_KIND_WORDS = {
    "issues": ("issue", "platform", "priorit", "policy", "policies", "agenda", "plan", "vision", "positions", "promise"),
    "about": ("about", "meet", "bio", "biography", "story", "who-i-am", "who-we-are"),
    "news": ("news", "press", "media", "release", "blog", "update", "statement", "op-ed", "newsroom"),
}


def classify_page(url: str, link_text: str = "") -> str:
    hay = f"{urlsplit(url).path} {link_text}".lower()
    for kind, words in _KIND_WORDS.items():
        if any(w in hay for w in words):
            return kind
    return "other"


def pick_links(base_url: str, html: bytes, *, limit: int = MAX_PAGES_PER_SITE - 1) -> list[tuple[str, str]]:
    """Same-host links that look like issues / about / news pages, best first."""
    base_host = host_of(base_url)
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    found: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or host_of(url) != base_host or is_social(url):
            continue
        if re.search(r"\.(jpe?g|png|gif|svg|webp|pdf|docx?|xlsx?|zip|mp[34]|css|js)$", parts.path, re.I):
            continue
        if url in seen or url.rstrip("/") == base_url.rstrip("/"):
            continue
        kind = classify_page(url, a.get_text(" ", strip=True))
        if kind == "other":
            continue
        seen.add(url)
        found.append((kind, url))
    order = {"issues": 0, "about": 1, "news": 2}
    found.sort(key=lambda kv: order[kv[0]])
    return [(k, u) for k, u in found[:limit]]


@dataclass
class Task:
    site: OfficialSite
    url: str
    kind: str
    is_home: bool = False
    archive_ts: str | None = None


class Crawler:
    def __init__(
        self,
        db: Session,
        *,
        client: httpx.Client | None = None,
        pace: float | None = None,
        max_requests: int | None = None,
        storage_dir: str | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.db = db
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True, max_redirects=5
        )
        self.pace = settings.crawl_pace_seconds if pace is None else pace
        self.max_requests = settings.crawl_max_requests if max_requests is None else max_requests
        self.storage = Path(storage_dir or settings.snapshot_dir)
        self._sleep, self._clock, self._now = sleep, clock, now
        self.requests = 0
        self._next_ok: dict[str, float] = defaultdict(float)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._delay: dict[str, float] = {}

    # -- plumbing ---------------------------------------------------------
    @property
    def capped(self) -> bool:
        return self.requests >= self.max_requests

    def _wait(self, host: str) -> None:
        wait = self._next_ok[host] - self._clock()
        if wait > 0:
            self._sleep(wait)

    def _get(self, url: str, host: str, pace: float) -> httpx.Response | Exception:
        self._wait(host)
        self.requests += 1
        try:
            with self.client.stream("GET", url) as resp:
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                resp._content = b"".join(chunks)  # noqa: SLF001 - keep the capped body on the response
                resp.truncated = size > MAX_BYTES  # type: ignore[attr-defined]
        except httpx.HTTPError as exc:
            return exc
        finally:
            self._next_ok[host] = self._clock() + max(pace, self._delay.get(host, 0.0))
        return resp

    def _robots_for(self, site_url: str) -> RobotFileParser | None:
        """None means robots.txt could not be read (do not crawl this run)."""
        host = host_of(site_url)
        if host in self._robots:
            return self._robots[host]
        parts = urlsplit(site_url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        rp = RobotFileParser()
        resp = self._get(robots_url, host, self.pace)
        if isinstance(resp, Exception) or resp.status_code >= 500:
            self._robots[host] = None
        elif resp.status_code in (401, 403):
            rp.disallow_all = True
            self._robots[host] = rp
        elif resp.status_code >= 400:
            rp.allow_all = True
            self._robots[host] = rp
        else:
            rp.parse(resp.text.splitlines())
            delay = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*")
            if delay:
                self._delay[host] = float(delay)
            self._robots[host] = rp
        return self._robots[host]

    # -- storage ----------------------------------------------------------
    def _store(self, body: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(body).hexdigest()
        rel = f"{digest[:2]}/{digest}.html"
        path = self.storage / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(path)
        return digest, rel

    def _record(self, task: Task, status: str, **fields) -> SiteSnapshot:
        row = SiteSnapshot(
            site_id=task.site.id, url=task.url, page_kind=task.kind, status=status, fetched_at=self._now(), **fields
        )
        # A re-fetch that returns identical bytes is not a new snapshot.
        if row.content_hash:
            dup = self.db.execute(
                select(SiteSnapshot).where(
                    SiteSnapshot.site_id == row.site_id,
                    SiteSnapshot.url == row.url,
                    SiteSnapshot.content_hash == row.content_hash,
                )
            ).scalar_one_or_none()
            if dup:
                return dup
        self.db.add(row)
        self.db.flush()
        return row

    # -- the work ---------------------------------------------------------
    def _done_recently(self, task: Task) -> bool:
        rows = self.db.execute(
            select(SiteSnapshot).where(SiteSnapshot.site_id == task.site.id, SiteSnapshot.url == task.url)
        ).scalars().all()
        for r in rows:
            if r.status != "unavailable" or self._now() - r.fetched_at < RETRY_UNAVAILABLE_AFTER:
                return True
        return False

    def fetch_page(self, task: Task) -> tuple[SiteSnapshot | None, bytes | None]:
        if is_social(task.url):
            return self._record(task, "refused", note="social platform; not crawled"), None
        rp = self._robots_for(task.url)
        if rp is None:
            return self._record(task, "unavailable", note=ROBOTS_UNREADABLE), None
        if not rp.can_fetch(USER_AGENT, task.url):
            return self._record(task, "blocked_by_robots", note="disallowed by robots.txt"), None
        if self.capped:
            return None, None
        resp = self._get(task.url, host_of(task.url), self.pace)
        if isinstance(resp, Exception):
            return self._record(task, "unavailable", note=f"{type(resp).__name__}: {resp}"[:300]), None
        final = str(resp.url)
        base = dict(http_status=resp.status_code, final_url=final, content_type=resp.headers.get("content-type"))
        if host_of(final) != host_of(task.url):
            return self._record(task, "refused", note=f"redirected to another host: {host_of(final)}", **base), None
        if resp.status_code >= 400:
            return self._record(task, "unavailable", note=f"HTTP {resp.status_code}", **base), None
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype:
            return self._record(task, "refused", note="not an HTML page", **base), None
        if getattr(resp, "truncated", False):
            return self._record(task, "refused", note=f"larger than {MAX_BYTES} bytes", **base), None
        body = resp.content
        digest, rel = self._store(body)
        snap = self._record(
            task, "ok", content_hash=digest, byte_length=len(body), storage_path=rel, **base,
        )
        return snap, body

    def archive_fallback(self, site: OfficialSite) -> SiteSnapshot | None:
        """Snapshot the Internet Archive's copy of a site that is gone."""
        if self.capped:
            return None
        self._wait("archive.org")
        self.requests += 1
        try:
            r = self.client.get("https://archive.org/wayback/available", params={"url": site.url})
            closest = (r.json().get("archived_snapshots") or {}).get("closest") or {}
        except (httpx.HTTPError, ValueError):
            return None
        finally:
            self._next_ok["archive.org"] = self._clock() + ARCHIVE_PACE
        if not closest.get("available") or not closest.get("timestamp"):
            return None
        ts = closest["timestamp"]
        site.archive_url, site.archive_timestamp = closest.get("url"), ts
        raw_url = f"https://{ARCHIVE_HOST}/web/{ts}id_/{site.url}"
        task = Task(site, site.url, "home", is_home=True, archive_ts=ts)
        if self.capped:
            return None
        resp = self._get(raw_url, ARCHIVE_HOST, ARCHIVE_PACE)
        if isinstance(resp, Exception) or resp.status_code >= 400 or "html" not in (resp.headers.get("content-type") or "").lower():
            return None
        digest, rel = self._store(resp.content)
        return self._record(
            task, "ok", http_status=resp.status_code, final_url=raw_url, content_type=resp.headers.get("content-type"),
            content_hash=digest, byte_length=len(resp.content), storage_path=rel, from_archive_timestamp=ts,
            note="Internet Archive copy; the site itself was unavailable",
        )

    def crawl_site(self, site: OfficialSite) -> dict:
        out = {"snapshots": 0, "unavailable": 0, "blocked": 0}
        home = Task(site, site.url, "home", is_home=True)
        if self._done_recently(home):
            prior = self.db.execute(
                select(SiteSnapshot).where(
                    SiteSnapshot.site_id == site.id, SiteSnapshot.url == site.url, SiteSnapshot.status == "ok"
                ).order_by(SiteSnapshot.fetched_at.desc())
            ).scalars().first()
            body = (self.storage / prior.storage_path).read_bytes() if prior and prior.storage_path else None
            snap = prior
        else:
            snap, body = self.fetch_page(home)
        site.last_checked_at = self._now()
        if snap is None:  # run cap reached before the first page
            return out
        if snap.status == "ok":
            site.status = "live"
            out["snapshots"] += 1
        elif snap.status == "blocked_by_robots":
            site.status = "blocked"
            out["blocked"] += 1
        elif snap.note == ROBOTS_UNREADABLE:
            out["unavailable"] += 1  # the site may be fine; say nothing about it, try again next run
            return out
        else:
            site.status = "offline"
            out["unavailable"] += 1
            arch = self.archive_fallback(site) if snap.status == "unavailable" else None
            if arch:
                out["snapshots"] += 1
            return out
        if body is None:
            return out
        for kind, url in pick_links(site.url, body):
            task = Task(site, url, kind)
            if self._done_recently(task):
                continue
            if self.capped:
                break
            s, _ = self.fetch_page(task)
            if s is None:
                break
            out["snapshots" if s.status == "ok" else "blocked" if s.status == "blocked_by_robots" else "unavailable"] += 1
        return out

    def run(self, sites: list[OfficialSite]) -> dict:
        """Crawl the given sites, never touching one host more often than
        `pace`. Sites are visited in order of the host that is ready first, so
        many small hosts interleave rather than queue behind a slow one."""
        totals = {"sites": 0, "snapshots": 0, "unavailable": 0, "blocked": 0, "requests": 0, "capped": False}
        pending = list(sites)
        while pending and not self.capped:
            pending.sort(key=lambda s: self._next_ok[host_of(s.url)])
            site = pending.pop(0)
            res = self.crawl_site(site)
            totals["sites"] += 1
            for k in ("snapshots", "unavailable", "blocked"):
                totals[k] += res[k]
            self.db.commit()
        totals["requests"] = self.requests
        totals["capped"] = bool(pending) or self.capped
        return totals


def sites_to_crawl(db: Session, site_id: str | None = None) -> list[OfficialSite]:
    stmt = select(OfficialSite).order_by(OfficialSite.created_at)
    if site_id:
        stmt = stmt.where(OfficialSite.id == site_id)
    return list(db.execute(stmt).scalars())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--pace", type=float)
    parser.add_argument("--site-id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        crawler = Crawler(db, pace=args.pace, max_requests=args.max_requests)
        logger.info("crawl: %s", crawler.run(sites_to_crawl(db, args.site_id)))


if __name__ == "__main__":
    main()
