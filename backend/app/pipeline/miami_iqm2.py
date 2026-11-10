"""Miami local legislation ingestion via Granicus iQM2 (miamifl.iqm2.com).

Miami's Legistar API client ("miamifl") turned out to hold only a handful
of legacy records with no sponsor data -- the city's actually-maintained
legislative record lives on a *different* Granicus product, iQM2, which has
no public JSON API. This module scrapes it instead: legislation detail
pages (Detail_LegiFile.aspx?ID=N) are sequentially numbered and consistently
structured, so recent records are found by walking IDs backward from the
current high-water mark.

More fragile than the Legistar API path in legistar.py by nature -- it
depends on undocumented page structure that could change without notice.
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import date, datetime, timezone
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bill, CrawlCheckpoint, Entity, Relationship, Source
from app.pipeline._retry import with_retry
from app.pipeline.flsenate import USER_AGENT
from app.pipeline.iqm2_pacing import BudgetExhausted, Pacer
from app.pipeline._status import normalize_status
from app.pipeline._text_limits import CHAMBER_MAX_LENGTH, fit
from app.pipeline.source_checks import record_check, record_partial
from app.pipeline.topic_tagging_ollama import tag_local_bill

logger = logging.getLogger(__name__)

IQM2_BASE_URL = "https://{subdomain}.iqm2.com/Citizens"
JURISDICTION = "Miami"
COUNTY = "Miami-Dade County"

# Detail_LegiFile.aspx?ID=N element IDs, confirmed stable across sampled records.
_FIELD_IDS = {
    "type": "ContentPlaceholder1_lblLegiFileType",
    "number": "ContentPlaceholder1_lblResNum",
    "status": "ContentPlaceholder1_lblStatus",
    "date_link": "ContentPlaceholder1_lnkDate",
    "title": "ContentPlaceholder1_lblLegiFileTitle",
}


class PolicyBlocked(Exception):
    """The portal's robots.txt disallows the pages we read."""


class IQM2Client:
    """Reads one iQM2 portal at the pace its robots.txt asks for.

    Every request, including each retry, goes through the Pacer: spacing
    (default 60 s, never below the portal's Crawl-delay), a request cap and
    a time cap. Constructing a client does no network I/O."""

    def __init__(self, subdomain: str = "miamifl", *, pacer: Pacer | None = None) -> None:
        self.subdomain = subdomain
        self.base_url = IQM2_BASE_URL.format(subdomain=subdomain)
        self._client = httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT})
        self.pacer = pacer or Pacer(
            pace_seconds=settings.iqm2_pace_seconds,
            max_requests=settings.iqm2_max_requests_per_run,
            max_seconds=settings.iqm2_max_minutes_per_run * 60,
        )
        self._robots_read = False

    def _paced_get(self, url: str, **kwargs) -> httpx.Response:
        def attempt() -> httpx.Response:
            self.pacer.before_request()
            resp = self._client.get(url, **kwargs)
            if resp.status_code >= 500:
                resp.raise_for_status()  # retried (and paced) by with_retry; a 5xx is not a gap in the ID space
            return resp

        return with_retry(attempt, description=f"iQM2[{self.subdomain}] GET {url}")

    def _read_robots(self) -> None:
        """Once per run: raise the pacing floor to the portal's Crawl-delay
        and stop if our pages are disallowed. An unreadable robots.txt is
        treated as 'no rules', like any crawler; a 5xx is not."""
        if self._robots_read:
            return
        resp = self._paced_get(self.base_url.rsplit("/Citizens", 1)[0] + "/robots.txt")
        self._robots_read = True
        if resp.status_code in (401, 403):
            raise PolicyBlocked(f"{self.subdomain}: robots.txt refuses us ({resp.status_code})")
        if resp.status_code != 200:
            return
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        delay = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*")
        if delay:
            self.pacer.raise_floor(float(delay))
        if not rp.can_fetch(USER_AGENT, f"{self.base_url}/Detail_LegiFile.aspx"):
            raise PolicyBlocked(f"{self.subdomain}: robots.txt disallows Detail_LegiFile.aspx")

    def get_legislation(self, legi_file_id: int) -> dict | None:
        """Fetch and parse one legislation record. None if this ID isn't a
        legislation detail page (gaps in the ID space are expected -- other
        content types share the same numbering)."""
        self._read_robots()
        resp = self._paced_get(f"{self.base_url}/Detail_LegiFile.aspx", params={"ID": legi_file_id})
        if resp.status_code != 200:
            return None
        return self._parse(resp.text, legi_file_id)

    def _parse(self, html: str, legi_file_id: int) -> dict | None:
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find(id=_FIELD_IDS["title"])
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None  # not a legislation record at this ID

        number_el = soup.find(id=_FIELD_IDS["number"])
        type_el = soup.find(id=_FIELD_IDS["type"])
        status_el = soup.find(id=_FIELD_IDS["status"])
        date_el = soup.find(id=_FIELD_IDS["date_link"])

        info: dict[str, str] = {}
        info_table = soup.find(id="tblLegiFileInfo")
        if info_table:
            headers = info_table.find_all("th")
            for th in headers:
                key = th.get_text(strip=True).rstrip(":")
                td = th.find_next_sibling("td")
                if td:
                    info[key] = td.get_text(strip=True)

        return {
            "legi_file_id": legi_file_id,
            "number": number_el.get_text(strip=True) if number_el else str(legi_file_id),
            "type": type_el.get_text(strip=True) if type_el else None,
            "status": status_el.get_text(strip=True) if status_el else "Unknown",
            "date_text": date_el.get_text(strip=True) if date_el else None,
            "title": title,
            "department": info.get("Department"),
            "sponsors": info.get("Sponsors") or "",
        }


_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DATE_RE = re.compile(rf"({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})")


def _parse_date_text(value: str | None) -> date | None:
    if not value:
        return None
    match = _DATE_RE.search(value)
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%b %d %Y").date()
    except ValueError:
        return None


def _known_high_water_mark(db: Session, *, fallback: int) -> int:
    """Highest iqm2_legi_file_id already ingested, so repeat runs probe
    forward from near the frontier instead of from a stale hardcoded guess
    (the ID space moves ~900/month at observed volume -- a cold-start probe
    from an old baseline took 7.5 minutes; this makes every run after the
    first one fast).
    """
    ids = db.execute(
        select(Entity.external_ids["iqm2_legi_file_id"].as_string()).where(
            Entity.entity_type == "bill", Entity.external_ids.has_key("iqm2_legi_file_id")
        )
    ).scalars().all()
    if not ids:
        return fallback
    return max(int(i) for i in ids)


def _get_or_create_bill_entity(db: Session, *, legi_file_id: int) -> Entity | None:
    return db.execute(
        select(Entity).where(
            Entity.entity_type == "bill",
            Entity.external_ids["iqm2_legi_file_id"].as_string() == str(legi_file_id),
        )
    ).scalar_one_or_none()


def _get_or_create_person(db: Session, *, name: str) -> Entity:
    existing = db.execute(
        select(Entity).where(
            Entity.entity_type == "person", Entity.name == name, Entity.jurisdiction_name == JURISDICTION
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="city",
        jurisdiction_name=JURISDICTION,
        external_ids={},
        attributes={},
    )
    db.add(person)
    db.flush()
    return person


def _write_record(db: Session, client: IQM2Client, record: dict, *, now: datetime) -> Entity:
    """Upsert one parsed iQM2 record (entity, source, bill, sponsors, tags)."""
    legi_file_id = record["legi_file_id"]
    detail_url = f"{client.base_url}/Detail_LegiFile.aspx?ID={legi_file_id}"
    full_title = record["title"]
    name = full_title if len(full_title) <= 490 else full_title[:489] + "…"

    entity = _get_or_create_bill_entity(db, legi_file_id=legi_file_id)
    if entity is None:
        entity = Entity(entity_type="bill", name=name, external_ids={})
        db.add(entity)

    entity.name = name
    entity.jurisdiction_level = "city"
    entity.jurisdiction_name = JURISDICTION
    entity.external_ids = {**entity.external_ids, "iqm2_legi_file_id": str(legi_file_id)}
    if record["type"]:
        entity.attributes = {**(entity.attributes or {}), "item_type": record["type"]}  # see item_kind.py
    db.flush()

    source = Source(
        url=detail_url,
        document_reference=record["number"],
        publisher=f"{JURISDICTION} (Granicus iQM2)",
        source_type="iqm2_legislation",
        retrieved_at=now,
        metadata_json={"legi_file_id": legi_file_id, "type": record["type"], "department": record["department"]},
    )
    db.add(source)
    db.flush()

    action_date = _parse_date_text(record["date_text"])

    bill = entity.bill
    if bill is None:
        bill = Bill(entity_id=entity.id, bill_number=record["number"], session="")
        db.add(bill)

    bill.bill_number = record["number"]
    bill.session = str(action_date.year) if action_date else "current"
    department = record["department"]
    bill.chamber = fit(department, CHAMBER_MAX_LENGTH)
    bill.status = normalize_status(record["status"])
    bill.last_action_date = action_date
    bill.last_action = record["status"]
    bill.full_text_url = detail_url
    bill.source_system = "iqm2"
    bill.description = full_title
    bill.geo_scope_type = "city"
    bill.geo_scope_names = [COUNTY]
    db.flush()

    for sponsor_name in _split_sponsors(record["sponsors"]):
        person = _get_or_create_person(db, name=sponsor_name)
        exists = db.execute(
            select(Relationship).where(
                Relationship.from_entity_id == person.id,
                Relationship.to_entity_id == entity.id,
                Relationship.relationship_type == "sponsor",
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                Relationship(
                    from_entity_id=person.id,
                    to_entity_id=entity.id,
                    relationship_type="sponsor",
                    source_id=source.id,
                )
            )

    tag_local_bill(db, entity.id, title=name, description=bill.description or "")
    return entity


CHECKPOINT_KEY = "iqm2:{subdomain}"
MAX_PROBE = 3000
MAX_MISSES = 25


def _load_state(db: Session, key: str) -> dict | None:
    row = db.execute(select(CrawlCheckpoint).where(CrawlCheckpoint.key == key)).scalar_one_or_none()
    return dict(row.state) if row else None


def _save_state(db: Session, key: str, state: dict) -> None:
    now = datetime.now(timezone.utc)
    row = db.execute(select(CrawlCheckpoint).where(CrawlCheckpoint.key == key)).scalar_one_or_none()
    if row is None:
        db.add(CrawlCheckpoint(key=key, state=state, updated_at=now))
    else:
        row.state, row.updated_at = state, now
    db.commit()  # the records written since the last save and the checkpoint land together


def _fresh_cycle(db: Session) -> dict:
    # Start probing just behind the last ID we've already seen, not a stale
    # hardcoded baseline -- see _known_high_water_mark.
    start = max(_known_high_water_mark(db, fallback=19550) - 5, 1)
    return {
        "phase": "probe", "probe_start": start, "probe_next": start, "misses": 0, "highest": start,
        "refresh": [], "refreshed": 0, "seen": [], "complete": False,
        "started_at": datetime.now(timezone.utc).isoformat(), "written": 0,
    }


def ingest_miami_legislation(
    db: Session, *, limit: int = 20, client: IQM2Client | None = None, subdomain: str = "miamifl"
) -> list[Entity]:
    """Scrape recent Miami legislation from iQM2 and upsert bill Entities.

    Resumable. A cycle has two phases -- probe forward from the known
    high-water mark until 25 consecutive misses (each record found is written
    on the spot, so nothing is fetched twice), then refresh the most recent
    `limit` records below the frontier to catch status changes. At the pace
    the portal asks for (60 s) a cycle takes longer than one run's budget, so
    progress is checkpointed after every record and the next run picks up
    where this one stopped. `source_checks` moves only when a cycle finishes.
    """
    client = client or IQM2Client(subdomain)
    key = CHECKPOINT_KEY.format(subdomain=subdomain)
    state = _load_state(db, key)
    if state is None or state.get("complete"):
        state = _fresh_cycle(db)
        _save_state(db, key, state)
    written: list[Entity] = []
    now = datetime.now(timezone.utc)

    try:
        if state["phase"] == "probe":
            probe_end = state["probe_start"] + MAX_PROBE
            while state["misses"] < MAX_MISSES and state["probe_next"] < probe_end:
                record = client.get_legislation(state["probe_next"])
                if record is not None:
                    written.append(_write_record(db, client, record, now=now))
                    state["highest"], state["misses"] = state["probe_next"], 0
                    state["seen"].append(state["probe_next"])
                    state["written"] += 1
                else:
                    state["misses"] += 1
                state["probe_next"] += 1
                _save_state(db, key, state)
            top = state["highest"]
            state["phase"] = "refresh"
            state["refresh"] = [i for i in range(top, max(top - limit * 2, 1), -1) if i not in set(state["seen"])]
            _save_state(db, key, state)

        while state["refresh"] and state["refreshed"] < limit:
            legi_file_id = state["refresh"][0]
            record = client.get_legislation(legi_file_id)
            if record is not None:
                written.append(_write_record(db, client, record, now=now))
                state["refreshed"] += 1
                state["written"] += 1
            state["refresh"].pop(0)
            _save_state(db, key, state)

        state["complete"] = True
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(db, key, state)
        record_check(db, f"iqm2_{subdomain.removesuffix('fl')}", f"{state['written']} records ingested")
        logger.info("iQM2 %s: cycle complete, %d records, %d requests", subdomain, state["written"], client.pacer.requests)
    except BudgetExhausted as exc:
        where = state["probe_next"] if state["phase"] == "probe" else f"refresh, {len(state['refresh'])} left"
        record_partial(
            db, f"iqm2_{subdomain.removesuffix('fl')}",
            f"incomplete: {exc}; {state['written']} records so far, resumes at {where}",
        )
        logger.warning("iQM2 %s: stopped (%s) after %d requests; resumes at %s", subdomain, exc, client.pacer.requests, where)
    return written


def _split_sponsors(raw: str) -> list[str]:
    if not raw:
        return []
    # Sponsors field is free text, sometimes multiple names separated by ";" or ",".
    # Titles like "Commissioner, District Four Ralph Rosado" contain a comma that
    # isn't a separator, so split on ";" only -- multi-sponsor items are rare
    # enough that under-splitting is safer than mangling a single name.
    return [s.strip() for s in raw.split(";") if s.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-requests", type=int, default=settings.iqm2_max_requests_per_run)
    parser.add_argument("--max-minutes", type=int, default=settings.iqm2_max_minutes_per_run)
    parser.add_argument("--pace", type=float, default=settings.iqm2_pace_seconds, help="seconds between requests (floor: the portal's Crawl-delay)")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    from app.db import SessionLocal

    pacer = Pacer(pace_seconds=args.pace, max_requests=args.max_requests, max_seconds=args.max_minutes * 60)
    with SessionLocal() as session:
        try:
            entities = ingest_miami_legislation(session, limit=args.limit, client=IQM2Client(pacer=pacer))
        except PolicyBlocked as exc:
            raise SystemExit(f"STOPPED by the portal's robots.txt: {exc}") from exc
        print(f"Wrote {len(entities)} Miami legislation records ({pacer.requests} requests).")


if __name__ == "__main__":
    main()
