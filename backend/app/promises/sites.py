"""Winners' own sites (Todoist 6hvxrjHc369MQR8p).

A promise must come from the candidate's own page, so every site here is one
the candidate or their legislature office publishes. Third-party directories
may point us at one (`discovered_via="directory"`) but are never crawled.

Usage:
    python -m app.promises.sites --senate-pages          # incumbent senators' flsenate.gov pages
    python -m app.promises.sites --csv sites.csv         # chamber,district,url[,kind,discovered_via]
"""

from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ElectionWinner, OfficialSite
from app.promises.winners import parse_chamber, parse_district

logger = logging.getLogger(__name__)

# No social platform scraping (owner decision 2026-11-03).
SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "instagram.com", "x.com", "twitter.com", "tiktok.com", "youtube.com",
    "youtu.be", "linkedin.com", "threads.net", "bsky.app", "truthsocial.com", "reddit.com",
    "nextdoor.com", "snapchat.com", "t.me", "telegram.org", "mastodon.social",
)


class SiteError(ValueError):
    pass


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def is_social(url: str) -> bool:
    host = host_of(url)
    return any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SiteError(f"not an http(s) URL: {url!r}")
    path = parts.path or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, parts.query, ""))


def add_site(
    db: Session,
    winner: ElectionWinner,
    url: str,
    *,
    kind: str,
    discovered_via: str,
    now: datetime | None = None,
) -> OfficialSite | None:
    """Add a site unless it is a social platform or already recorded.
    Returns the new row, or None when skipped."""
    url = normalize_url(url)
    if is_social(url):
        logger.info("skipping social platform URL for %s: %s", winner.name, url)
        return None
    existing = db.execute(
        select(OfficialSite).where(OfficialSite.winner_id == winner.id, OfficialSite.url == url)
    ).scalar_one_or_none()
    if existing:
        return None
    site = OfficialSite(
        winner_id=winner.id,
        url=url,
        site_kind=kind,
        discovered_via=discovered_via,
        discovered_at=now or datetime.now(timezone.utc),
        status="unchecked",
    )
    db.add(site)
    db.flush()
    return site


def senate_page_url(district: int) -> str:
    return f"https://www.flsenate.gov/Senators/s{district}"


def discover_senate_pages(db: Session, *, cycle: int, now: datetime | None = None) -> int:
    """flsenate.gov serves one page per district, at the sitting senator's
    name. That is the winner's own page only when the winner is the
    incumbent, so only incumbent winners get one; new senators get a page
    when sworn in (re-run then). House pages are keyed by member id, not
    district, so they come in through the CSV."""
    added = 0
    winners = db.execute(
        select(ElectionWinner).where(
            ElectionWinner.cycle == cycle, ElectionWinner.chamber == "senate", ElectionWinner.incumbent.is_(True)
        )
    ).scalars()
    for w in winners:
        if add_site(
            db, w, senate_page_url(w.district), kind="official_legislature",
            discovered_via="official_member_page", now=now,
        ):
            added += 1
    return added


def import_sites_csv(db: Session, text: str, *, cycle: int, now: datetime | None = None) -> dict:
    counts = {"added": 0, "skipped": 0, "unknown_seat": 0}
    for n, row in enumerate(csv.DictReader(text.lstrip("﻿").splitlines()), start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            chamber, district = parse_chamber(row["chamber"]), parse_district(row["district"])
            url = row["url"]
        except (KeyError, ValueError) as exc:
            raise SiteError(f"line {n}: {exc}") from exc
        w = db.execute(
            select(ElectionWinner).where(
                ElectionWinner.cycle == cycle, ElectionWinner.chamber == chamber, ElectionWinner.district == district
            )
        ).scalar_one_or_none()
        if w is None:
            counts["unknown_seat"] += 1
            continue
        site = add_site(
            db, w, url,
            kind=row.get("kind") or "campaign",
            discovered_via=row.get("discovered_via") or "manual",
            now=now,
        )
        counts["added" if site else "skipped"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--senate-pages", action="store_true")
    parser.add_argument("--csv", dest="csv_path")
    parser.add_argument("--cycle", type=int, default=2026)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        if args.senate_pages:
            logger.info("senate pages added: %d", discover_senate_pages(db, cycle=args.cycle))
        if args.csv_path:
            with open(args.csv_path, encoding="utf-8") as fh:
                logger.info("sites: %s", import_sites_csv(db, fh.read(), cycle=args.cycle))
        db.commit()


if __name__ == "__main__":
    main()
