"""GDELT headline pull (Roadmap Step 10, BRD 5.7): a thin, unscored news
layer — recent headlines matched to a bill by keyword, no sentiment or
stance classification (explicitly deferred to Phase 2).

Deliberately the last/least load-bearing MVP piece per the Roadmap. Uses
GDELT's free DOC 2.0 API (no key required).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, Event, Source

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT's free DOC API rate-limits aggressively and its exact window isn't
# published — observed 429s persisting well past a naive few-second backoff
# during testing. Space requests out generously and retry with real backoff
# rather than letting one throttled bill fail a whole batch run. For regular
# use, run this as an infrequent (e.g. daily) batch job, not interactively.
MIN_SECONDS_BETWEEN_REQUESTS = 8.0
RATE_LIMIT_RETRY_DELAY_SECONDS = 30.0
RATE_LIMIT_MAX_RETRIES = 2


class GDELTError(RuntimeError):
    pass


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

        retries = 0
        while resp.status_code == 429 and retries < RATE_LIMIT_MAX_RETRIES:
            time.sleep(RATE_LIMIT_RETRY_DELAY_SECONDS)
            resp = self._client.get(GDELT_DOC_API, params=params)
            self._last_request_at = time.monotonic()
            retries += 1

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GDELTError(f"GDELT request failed for query={query!r}: {exc}") from exc

        # GDELT returns text/html content-type even for JSON responses.
        try:
            data = resp.json()
        except ValueError as exc:
            raise GDELTError(f"Unexpected GDELT response for query={query!r}: {resp.text[:200]}") from exc
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


def pull_headlines_for_all_bills(db: Session, *, max_records: int = 5) -> int:
    """Batch entry point: pull headlines for every bill entity currently stored."""
    client = GDELTClient()
    entities = db.execute(select(Entity).where(Entity.entity_type == "bill")).scalars().all()

    total = 0
    for entity in entities:
        try:
            total += len(pull_headlines_for_bill(db, entity, client=client))
        except GDELTError as exc:
            logger.warning("Skipping bill %s: %s", entity.id, exc)
    return total


if __name__ == "__main__":
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        count = pull_headlines_for_all_bills(session)
        print(f"Pulled {count} new headlines across all bills.")
    finally:
        session.close()
