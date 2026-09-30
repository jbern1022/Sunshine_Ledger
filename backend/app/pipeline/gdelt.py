"""GDELT headline pull (Roadmap Step 10, BRD 5.7): a thin, unscored news
layer — recent headlines matched to a bill by keyword, no sentiment or
stance classification (explicitly deferred to Phase 2).

Deliberately the last/least load-bearing MVP piece per the Roadmap. Uses
GDELT's free DOC 2.0 API (no key required).

Weekly run, sized to take minutes (2026-09-27 it took 6+ hours over every
bill, with 243 rate-limit errors and many rejected queries): only bills
with activity in the last `days`, queries built from a title's distinctive
words (GDELT rejects short keywords and punctuation), real backoff on 429,
and a wall-clock cap.

    python -m app.pipeline.gdelt [--days 60] [--max-minutes 45]
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_setup import quiet_http_logging
from app.models import Bill, Entity, Event, Source

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT's free DOC API rate-limits aggressively and its exact window isn't
# published — observed 429s persisting well past a naive few-second backoff
# during testing. Space requests out generously and retry with real backoff
# rather than letting one throttled bill fail a whole batch run. For regular
# use, run this as an infrequent (e.g. daily) batch job, not interactively.
MIN_SECONDS_BETWEEN_REQUESTS = 8.0
RATE_LIMIT_RETRY_DELAY_SECONDS = 30.0  # doubled on each retry unless GDELT sends Retry-After
RATE_LIMIT_MAX_RETRIES = 4
MAX_QUERY_WORDS = 5

# Words that say nothing about what a bill is about. Titles made only of
# these ("Department of Financial Services") match everything, so they're
# skipped rather than searched.
GENERIC_WORDS = {
    "about", "act", "acts", "additional", "amend", "amending", "amendment", "amendments", "and",
    "appropriation", "appropriations", "approving", "authorizing", "authority", "bill", "board",
    "certain", "city", "code", "commission", "committee", "concerning", "council", "county",
    "creating", "department", "district", "division", "florida", "for", "from", "general",
    "government", "into", "jacksonville", "miami", "office", "ordinance", "other", "program",
    "programs", "providing", "public", "regarding", "relating", "resolution", "revising", "section",
    "services", "state", "statutes", "that", "the", "this", "with", "within",
    # Procedure and the abbreviations Jacksonville ordinance titles use.
    "adopted", "agencies", "agreement", "amend", "approp", "apv", "auth", "btwn", "conditions",
    "contract", "corp", "desig", "dist", "estab", "execute", "fund", "funds", "initiatives",
    "introduced", "mgmt", "misc", "pkwy", "prog", "progs", "proposed", "pursuant", "read",
    "reappoint", "rerefer", "review", "svc", "svcs", "transmitting", "various",
    "adopting", "amendmnt", "appt", "approv", "member", "prov", "reappt", "reso",
}


class GDELTError(RuntimeError):
    pass


class GDELTQueryRejected(GDELTError):
    """GDELT answered with an error page about the query itself (e.g. "a
    keyword that was too short"): not worth retrying."""


def build_query(title: str | None, place: str | None = None) -> str | None:
    """A GDELT query from a bill title's distinctive words, or None when the
    title has fewer than two. GDELT rejects short keywords and punctuation,
    so words under 4 letters and every non-alphanumeric character go.
    `place` ("florida", "jacksonville") is added to keep matches local."""
    words: list[str] = []
    for word in re.sub(r"[^A-Za-z0-9 ]+", " ", title or "").lower().split():
        if len(word) >= 4 and word not in GENERIC_WORDS and not word.isdigit() and word not in words:
            words.append(word)
    if len(words) < 2:
        return None
    return " ".join(words[:MAX_QUERY_WORDS] + ([place.lower()] if place else []))


def _place(entity: Entity) -> str:
    return "florida" if entity.jurisdiction_level == "state" else (entity.jurisdiction_name or "florida")


class GDELTClient:
    def __init__(self) -> None:
        self._client = httpx.Client(timeout=20.0)
        self._last_request_at: float = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    def search_articles(self, query: str, *, max_records: int = 5, timespan: str = "1month") -> list[dict]:
        """Recent articles matching `query`, newest first. Empty list on no matches."""
        params = {
            "query": query,
            "mode": "ArtList",
            "maxrecords": str(max_records),
            "sort": "DateDesc",
            "timespan": timespan,
            "format": "json",
        }

        self._throttle()
        resp = self._client.get(GDELT_DOC_API, params=params)
        self._last_request_at = time.monotonic()

        delay = RATE_LIMIT_RETRY_DELAY_SECONDS
        retries = 0
        while resp.status_code == 429 and retries < RATE_LIMIT_MAX_RETRIES:
            retry_after = resp.headers.get("Retry-After", "")
            time.sleep(float(retry_after) if retry_after.isdigit() else delay)
            delay *= 2
            resp = self._client.get(GDELT_DOC_API, params=params)
            self._last_request_at = time.monotonic()
            retries += 1

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GDELTError(f"GDELT request failed for query={query!r}: {exc}") from exc

        # GDELT returns text/html content-type even for JSON responses, and a
        # plain-text sentence (200 OK) when it rejects the query itself.
        try:
            data = resp.json()
        except ValueError as exc:
            raise GDELTQueryRejected(f"GDELT rejected query={query!r}: {resp.text[:200]}") from exc
        return data.get("articles", [])


def _parse_seendate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def pull_headlines_for_bill(
    db: Session, entity: Entity, *, query: str | None = None, max_records: int = 5, client: GDELTClient | None = None
) -> list[Event]:
    """Pull headlines matching `query` (default: the bill's title) and store
    each as an Event(event_type='news_mention') with its own Source,
    skipping URLs already stored for this bill.
    """
    if entity.bill is None:
        raise ValueError("Entity is not a bill")

    client = client or GDELTClient()
    query = query or entity.name
    articles = client.search_articles(query, max_records=max_records)

    existing_urls = {e.source.url for e in entity.events if e.event_type == "news_mention" and e.source}

    written: list[Event] = []
    now = datetime.now(timezone.utc)

    for article in articles:
        url = article.get("url")
        if not url or url in existing_urls:
            continue

        source = Source(
            url=url,
            publisher=article.get("domain"),
            source_type="gdelt_article",
            retrieved_at=now,
            metadata_json={"language": article.get("language"), "sourcecountry": article.get("sourcecountry")},
        )
        db.add(source)
        db.flush()

        seen_at = _parse_seendate(article.get("seendate"))
        event = Event(
            entity_id=entity.id,
            event_type="news_mention",
            event_date=(seen_at or now).date(),
            title=article.get("title", "")[:500],
            source_id=source.id,
        )
        db.add(event)
        written.append(event)
        existing_urls.add(url)

    db.commit()
    logger.info("Pulled %d new headlines for bill %s (query=%r)", len(written), entity.bill.bill_number, query)
    return written


def pull_headlines_for_all_bills(
    db: Session,
    *,
    max_records: int = 5,
    days: int = 60,
    max_minutes: float = 45,
    client: GDELTClient | None = None,
    today: date | None = None,
) -> int:
    """Batch entry point: headlines for bills with activity in the last
    `days` (most recent first) that have a usable query, stopping after
    `max_minutes`. Returns headlines written."""
    client = client or GDELTClient()
    since = (today or date.today()) - timedelta(days=days)
    entities = db.execute(
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.last_action_date >= since)
        .order_by(Bill.last_action_date.desc())
    ).scalars().all()

    deadline = time.monotonic() + max_minutes * 60
    total = searched = no_query = rejected = failed = 0
    stopped_early = False
    for entity in entities:
        query = build_query(entity.name, _place(entity))
        if query is None:
            no_query += 1
            continue
        if time.monotonic() >= deadline:
            stopped_early = True
            break
        searched += 1
        try:
            total += len(pull_headlines_for_bill(db, entity, query=query, max_records=max_records, client=client))
        except GDELTQueryRejected as exc:
            rejected += 1
            logger.info("Query rejected for bill %s: %s", entity.id, exc)
        except (GDELTError, httpx.HTTPError) as exc:
            failed += 1
            logger.warning("Skipping bill %s: %s", entity.id, exc)

    summary = (
        f"{total} headlines from {searched} of {len(entities)} bills active in {days} days; "
        f"{no_query} without a usable query, {rejected} rejected, {failed} failed"
        + ("; stopped at the time cap" if stopped_early else "")
    )
    logger.info("GDELT: %s", summary)
    from app.pipeline.source_checks import record_check

    record_check(db, "gdelt", summary)
    return total


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=60, help="Only bills with an action in this many days.")
    parser.add_argument("--max-minutes", type=float, default=45)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        count = pull_headlines_for_all_bills(session, days=args.days, max_minutes=args.max_minutes)
        print(f"Pulled {count} new headlines.")
    finally:
        session.close()
