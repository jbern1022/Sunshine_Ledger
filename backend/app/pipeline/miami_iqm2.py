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

import logging
import re
from datetime import date, datetime, timezone

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, Entity, Relationship, Source
from app.pipeline._text_limits import CHAMBER_MAX_LENGTH, fit

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


class IQM2Client:
    def __init__(self, subdomain: str = "miamifl") -> None:
        self.subdomain = subdomain
        self.base_url = IQM2_BASE_URL.format(subdomain=subdomain)
        self._client = httpx.Client(timeout=20.0)

    def get_legislation(self, legi_file_id: int) -> dict | None:
        """Fetch and parse one legislation record. None if this ID isn't a
        legislation detail page (gaps in the ID space are expected -- other
        content types share the same numbering)."""
        resp = self._client.get(f"{self.base_url}/Detail_LegiFile.aspx", params={"ID": legi_file_id})
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

    def find_recent_ids(self, *, count: int, probe_start: int = 18700, max_probe: int = 3000) -> list[int]:
        """Find the current high-water mark by probing forward from
        `probe_start`, then return the `count` IDs immediately below it.
        Sequential IDs aren't all legislation records (gaps exist), so this
        over-fetches slightly and lets the caller skip Nones.
        """
        highest = probe_start
        misses = 0
        probe_id = probe_start
        while misses < 25 and probe_id < probe_start + max_probe:
            if self.get_legislation(probe_id) is not None:
                highest = probe_id
                misses = 0
            else:
                misses += 1
            probe_id += 1

        return list(range(highest, max(highest - count * 2, 1), -1))


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


def ingest_miami_legislation(db: Session, *, limit: int = 20) -> list[Entity]:
    """Scrape recent Miami legislation from iQM2 and upsert bill Entities."""
    client = IQM2Client()
    # Start probing just behind the last ID we've already seen, not a stale
    # hardcoded baseline -- see _known_high_water_mark.
    probe_start = max(_known_high_water_mark(db, fallback=19550) - 5, 1)
    candidate_ids = client.find_recent_ids(count=limit, probe_start=probe_start)

    written: list[Entity] = []
    now = datetime.now(timezone.utc)

    for legi_file_id in candidate_ids:
        if len(written) >= limit:
            break

        record = client.get_legislation(legi_file_id)
        if record is None:
            continue

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
        bill.status = record["status"]
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

        written.append(entity)

    db.commit()
    logger.info("Ingested %d Miami legislation records from iQM2", len(written))
    return written


def _split_sponsors(raw: str) -> list[str]:
    if not raw:
        return []
    # Sponsors field is free text, sometimes multiple names separated by ";" or ",".
    # Titles like "Commissioner, District Four Ralph Rosado" contain a comma that
    # isn't a separator, so split on ";" only -- multi-sponsor items are rare
    # enough that under-splitting is safer than mangling a single name.
    return [s.strip() for s in raw.split(";") if s.strip()]


if __name__ == "__main__":
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        entities = ingest_miami_legislation(session, limit=20)
        print(f"Ingested {len(entities)} Miami legislation records.")
    finally:
        session.close()
