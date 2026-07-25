"""LegiScan ingestion (Roadmap Step 4: automate the state bill pipeline).

Pulls Florida state bill text/status/sponsor data from the LegiScan API
(free tier: 30,000 queries/month) and writes it into the shared
Entity/Relationship/Event/Source schema, with a Source attached at write
time for every fact (BRD 5.1).

Requires LEGISCAN_API_KEY. Without a key, use `seed.py` sample data instead
so the rest of the pipeline can still be exercised locally.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bill, Entity, Relationship, Source

logger = logging.getLogger(__name__)

LEGISCAN_BASE_URL = "https://api.legiscan.com/"

# LegiScan status codes -> human-readable status (see LegiScan API docs).
STATUS_MAP = {
    1: "Introduced",
    2: "Engrossed",
    3: "Enrolled",
    4: "Passed",
    5: "Vetoed",
    6: "Failed",
}


class LegiScanError(RuntimeError):
    pass


class LegiScanClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.legiscan_api_key
        if not self.api_key:
            raise LegiScanError(
                "LEGISCAN_API_KEY is not set. Get a free key at https://legiscan.com/legiscan "
                "or use app/pipeline/seed.py sample data instead."
            )
        self._client = httpx.Client(base_url=LEGISCAN_BASE_URL, timeout=30.0)

    def _call(self, op: str, **params: str) -> dict:
        resp = self._client.get("", params={"key": self.api_key, "op": op, **params})
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            raise LegiScanError(f"LegiScan op={op} failed: {data}")
        return data

    def get_master_list(self, state: str) -> list[dict]:
        """Session bill list: id, number, title, last action/date, status, url."""
        data = self._call("getMasterList", state=state)
        master = data["masterlist"]
        return [v for k, v in master.items() if k != "session"]

    def get_bill(self, bill_id: int) -> dict:
        """Full bill detail: sponsors, status, text docs, description."""
        return self._call("getBill", id=str(bill_id))["bill"]


def _get_or_create_person(db: Session, *, name: str, external_id: str) -> Entity:
    existing = db.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.external_ids["legiscan_people_id"].as_string() == external_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="state",
        jurisdiction_name=settings.legiscan_state,
        external_ids={"legiscan_people_id": external_id},
        attributes={},
    )
    db.add(person)
    db.flush()
    return person


def _get_or_create_bill_entity(db: Session, *, legiscan_bill_id: int) -> Entity | None:
    return db.execute(
        select(Entity).where(
            Entity.entity_type == "bill",
            Entity.external_ids["legiscan_id"].as_string() == str(legiscan_bill_id),
        )
    ).scalar_one_or_none()


def ingest_state_bills(db: Session, *, state: str | None = None, limit: int | None = None) -> list[Entity]:
    """Pull the master bill list for `state` and upsert each bill + sponsors + source.

    Returns the list of bill Entities written (new or refreshed).
    """
    state = state or settings.legiscan_state
    client = LegiScanClient()

    master_list = client.get_master_list(state)
    if limit:
        master_list = master_list[:limit]

    written: list[Entity] = []
    now = datetime.now(timezone.utc)

    for row in master_list:
        legiscan_bill_id = int(row["bill_id"])
        detail = client.get_bill(legiscan_bill_id)

        entity = _get_or_create_bill_entity(db, legiscan_bill_id=legiscan_bill_id)
        if entity is None:
            entity = Entity(entity_type="bill", name=detail.get("title", row.get("title", "")), external_ids={})
            db.add(entity)

        entity.name = detail.get("title") or row.get("title", "")
        entity.jurisdiction_level = "state"
        entity.jurisdiction_name = state
        entity.external_ids = {**entity.external_ids, "legiscan_id": str(legiscan_bill_id)}
        db.flush()

        source = Source(
            url=detail.get("state_link") or row.get("url", ""),
            document_reference=detail.get("bill_number"),
            publisher=f"{state} Legislature via LegiScan",
            source_type="legiscan_bill",
            retrieved_at=now,
            metadata_json={"legiscan_bill_id": legiscan_bill_id, "change_hash": detail.get("change_hash")},
        )
        db.add(source)
        db.flush()

        bill = entity.bill
        if bill is None:
            bill = Bill(entity_id=entity.id, bill_number=detail.get("bill_number", row.get("number", "")), session="")
            db.add(bill)

        status_code = detail.get("status")
        bill.bill_number = detail.get("bill_number", row.get("number", ""))
        bill.session = detail.get("session", {}).get("session_name", "")
        bill.chamber = "Senate" if bill.bill_number.upper().startswith("S") else "House"
        bill.status = STATUS_MAP.get(status_code, row.get("status", "Introduced"))
        bill.introduced_date = _parse_date(detail.get("introduced"))
        bill.last_action_date = _parse_date(detail.get("status_date") or row.get("last_action_date"))
        bill.last_action = detail.get("last_action") or row.get("last_action")
        bill.full_text_url = detail.get("state_link") or row.get("url")
        bill.source_system = "legiscan"
        bill.description = detail.get("description")
        bill.geo_scope_type = "statewide"
        bill.geo_scope_names = [state]
        db.flush()

        for sponsor in detail.get("sponsors", []):
            person = _get_or_create_person(
                db, name=sponsor.get("name", "Unknown"), external_id=str(sponsor.get("people_id"))
            )
            rel_type = "sponsor" if sponsor.get("sponsor_type_id") == 1 else "co_sponsor"
            exists = db.execute(
                select(Relationship).where(
                    Relationship.from_entity_id == person.id,
                    Relationship.to_entity_id == entity.id,
                    Relationship.relationship_type == rel_type,
                )
            ).scalar_one_or_none()
            if not exists:
                db.add(
                    Relationship(
                        from_entity_id=person.id,
                        to_entity_id=entity.id,
                        relationship_type=rel_type,
                        source_id=source.id,
                    )
                )

        written.append(entity)

    db.commit()
    logger.info("Ingested %d bills from LegiScan for state=%s", len(written), state)
    return written


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
