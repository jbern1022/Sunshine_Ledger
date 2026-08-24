"""Legistar ingestion for Miami and Jacksonville local legislation
(Roadmap Step 7: local bills, confirmed Legistar-platform cities only).

Legistar exposes a public read API per client at
https://webapi.legistar.com/v1/{client}/... with no auth required for read
access (BRD 9 assumption). Only Miami and Jacksonville are wired up for
MVP; other Florida cities are an explicit future research spike per the
Charter.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, Entity, Relationship, Source
from app.pipeline._status import normalize_status
from app.pipeline._text_limits import CHAMBER_MAX_LENGTH, fit

logger = logging.getLogger(__name__)

LEGISTAR_BASE_URL = "https://webapi.legistar.com/v1/{client}"

# Legistar client tokens confirmed against the live API (not guessable from
# city name -- e.g. Miami's is "miamifl", not "miami"; Jacksonville's is
# "jaxcityc", not "jacksonville"). Also doubles as the public site subdomain
# (https://{client}.legistar.com).
CLIENT_JURISDICTIONS = {
    "miamifl": {"jurisdiction": "Miami", "county": "Miami-Dade County"},
    "jaxcityc": {"jurisdiction": "Jacksonville", "county": "Duval County"},
}


class LegistarClient:
    def __init__(self, client_name: str) -> None:
        self.client_name = client_name
        self._client = httpx.Client(base_url=LEGISTAR_BASE_URL.format(client=client_name), timeout=30.0)

    def get_matters(self, *, top: int = 50) -> list[dict]:
        """Recent legislative matters (ordinances, resolutions), newest first."""
        resp = self._client.get(
            "/Matters",
            params={"$orderby": "MatterIntroDate desc", "$top": str(top)},
        )
        resp.raise_for_status()
        return resp.json()

    def get_sponsors(self, matter_id: int) -> list[dict]:
        resp = self._client.get(f"/Matters/{matter_id}/Sponsors")
        resp.raise_for_status()
        return resp.json()


def _get_or_create_bill_entity(db: Session, *, client_name: str, matter_id: int) -> Entity | None:
    return db.execute(
        select(Entity).where(
            Entity.entity_type == "bill",
            Entity.external_ids["legistar_matter_id"].as_string() == str(matter_id),
            Entity.external_ids["legistar_client"].as_string() == client_name,
        )
    ).scalar_one_or_none()


def _get_or_create_person(db: Session, *, name: str, client_name: str, jurisdiction: str) -> Entity:
    existing = db.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.name == name,
            Entity.jurisdiction_name == jurisdiction,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="city",
        jurisdiction_name=jurisdiction,
        external_ids={"legistar_client": client_name},
        attributes={},
    )
    db.add(person)
    db.flush()
    return person


def ingest_local_bills(db: Session, *, client_name: str, limit: int = 50) -> list[Entity]:
    """Pull recent Matters for one Legistar client and upsert bill Entities."""
    if client_name not in CLIENT_JURISDICTIONS:
        raise ValueError(f"Unsupported Legistar client '{client_name}'; MVP supports {list(CLIENT_JURISDICTIONS)}")

    info = CLIENT_JURISDICTIONS[client_name]
    jurisdiction = info["jurisdiction"]
    client = LegistarClient(client_name)
    matters = client.get_matters(top=limit)

    written: list[Entity] = []
    now = datetime.now(timezone.utc)

    for matter in matters:
        matter_id = matter["MatterId"]
        detail_url = f"https://{client_name}.legistar.com/LegislationDetail.aspx?ID={matter_id}"

        # MatterName is null in practice for both confirmed clients -- MatterTitle
        # carries the actual legislative title (full legal text, sometimes
        # several paragraphs). entities.name is capped at 500 chars, so
        # truncate here; the full text is kept in bill.description below.
        full_title = matter.get("MatterName") or matter.get("MatterTitle") or f"Matter {matter_id}"
        title = full_title if len(full_title) <= 490 else full_title[:489] + "…"

        entity = _get_or_create_bill_entity(db, client_name=client_name, matter_id=matter_id)
        if entity is None:
            entity = Entity(entity_type="bill", name=title, external_ids={})
            db.add(entity)

        entity.name = title
        entity.jurisdiction_level = "city"
        entity.jurisdiction_name = jurisdiction
        entity.external_ids = {
            **entity.external_ids,
            "legistar_matter_id": str(matter_id),
            "legistar_client": client_name,
        }
        db.flush()

        source = Source(
            url=detail_url,
            document_reference=matter.get("MatterFile"),
            publisher=f"{jurisdiction} City Clerk (Legistar)",
            source_type="legistar_agenda",
            retrieved_at=now,
            metadata_json={"matter_id": matter_id, "matter_type": matter.get("MatterTypeName")},
        )
        db.add(source)
        db.flush()

        bill = entity.bill
        if bill is None:
            bill = Bill(entity_id=entity.id, bill_number=matter.get("MatterFile", str(matter_id)), session="")
            db.add(bill)

        bill.bill_number = matter.get("MatterFile", str(matter_id))
        bill.session = str(matter.get("MatterAgendaDate", ""))[:4] or "current"
        bill.chamber = fit(matter.get("MatterBodyName"), CHAMBER_MAX_LENGTH)
        bill.status = normalize_status(matter.get("MatterStatusName")) or "Introduced"
        bill.introduced_date = _parse_date(matter.get("MatterIntroDate"))
        bill.last_action_date = _parse_date(matter.get("MatterPassedDate")) or bill.introduced_date
        bill.last_action = matter.get("MatterStatusName")
        bill.full_text_url = detail_url
        bill.source_system = "legistar"
        bill.description = matter.get("MatterTitle")
        bill.geo_scope_type = "city"
        bill.geo_scope_names = [info["county"]]
        db.flush()

        try:
            for sponsor in client.get_sponsors(matter_id):
                name = sponsor.get("MatterSponsorName")
                if not name:
                    continue
                person = _get_or_create_person(db, name=name, client_name=client_name, jurisdiction=jurisdiction)
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
        except httpx.HTTPStatusError:
            logger.warning("No sponsor data for matter %s (%s)", matter_id, client_name)

        written.append(entity)

    db.commit()
    logger.info("Ingested %d local matters from Legistar client=%s", len(written), client_name)
    return written


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
