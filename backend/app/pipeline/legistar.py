"""Legistar ingestion for city legislation
(Roadmap Step 7: local bills, confirmed Legistar-platform cities only).

Legistar exposes a public read API per client at
https://webapi.legistar.com/v1/{client}/... with no auth required for read
access (BRD 9 assumption).

Adding a Legistar city is one entry in CLIENT_JURISDICTIONS: the nightly
run (`python -m app.pipeline.legistar --nightly`), the data-freshness
registry and the per-city counts all read from it. A client's `level` is
"city" (the default) or "county" (e.g. Broward County); it sets the stored
jurisdiction_level and geo_scope_type.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, Entity, Relationship, Source
from app.pipeline._retry import with_retry
from app.pipeline._status import normalize_status
from app.pipeline._text_limits import CHAMBER_MAX_LENGTH, fit
from app.pipeline.source_checks import record_check
from app.pipeline.topic_tagging_ollama import tag_local_bill

logger = logging.getLogger(__name__)

LEGISTAR_BASE_URL = "https://webapi.legistar.com/v1/{client}"

# Legistar client tokens confirmed against the live API (not guessable from
# city name -- e.g. Miami's is "miamifl", not "miami"; Jacksonville's is
# "jaxcityc", not "jacksonville"). Also doubles as the public site subdomain
# (https://{client}.legistar.com).
#
# `nightly` marks the clients the nightly job ingests. Miami stays False: its
# Legistar client holds ~6 legacy records and the real data is scraped from
# iQM2 (miami_iqm2.py). `label` and `note` feed the data-freshness registry
# (app/api/sources.py).
CLIENT_JURISDICTIONS = {
    "miamifl": {"jurisdiction": "Miami", "county": "Miami-Dade County", "nightly": False},
    "jaxcityc": {
        "jurisdiction": "Jacksonville",
        "county": "Duval County",
        "nightly": True,
        "label": "Jacksonville City Council (Legistar)",
        "note": "The most recent council matters. Matters without a PDF attachment have no full text.",
    },
    # County commission, live Legistar. Not nightly yet: enabling it needs a
    # look at how county items read on the site (Todoist 6hm2FqVh66Mmww6G).
    "broward": {
        "jurisdiction": "Broward County",
        "county": "Broward County",
        "level": "county",
        "publisher": "Broward County Commission (Legistar)",
        "nightly": False,
        "label": "Broward County Commission (Legistar)",
        "note": "The most recent county commission matters. Matters without a PDF attachment have no full text.",
    },
    "fortlauderdale": {
        "jurisdiction": "Fort Lauderdale",
        "county": "Broward County",
        "nightly": True,
        "label": "Fort Lauderdale City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
    },
}


def client_level(client_name: str) -> str:
    return CLIENT_JURISDICTIONS[client_name].get("level", "city")


def source_key(client_name: str) -> str:
    """The source_checks / data-freshness key for one Legistar client."""
    return f"legistar_{client_name}"


def nightly_clients() -> list[str]:
    return [name for name, info in CLIENT_JURISDICTIONS.items() if info.get("nightly")]


class LegistarClient:
    def __init__(self, client_name: str) -> None:
        self.client_name = client_name
        self._client = httpx.Client(base_url=LEGISTAR_BASE_URL.format(client=client_name), timeout=30.0)

    def get_matters(self, *, top: int = 50) -> list[dict]:
        """Recent legislative matters (ordinances, resolutions), newest first."""

        def _do_request() -> list[dict]:
            resp = self._client.get(
                "/Matters",
                params={"$orderby": "MatterIntroDate desc", "$top": str(top)},
            )
            resp.raise_for_status()
            return resp.json()

        return with_retry(_do_request, description=f"Legistar[{self.client_name}] get_matters")

    def get_sponsors(self, matter_id: int) -> list[dict]:
        def _do_request() -> list[dict]:
            resp = self._client.get(f"/Matters/{matter_id}/Sponsors")
            resp.raise_for_status()
            return resp.json()

        return with_retry(_do_request, description=f"Legistar[{self.client_name}] get_sponsors({matter_id})")


def _bill_title(matter: dict) -> str:
    """MatterName is null in practice for both confirmed clients -- MatterTitle
    carries the actual legislative title (full legal text, sometimes several
    paragraphs). entities.name is capped at 500 chars, so truncate here; the
    full text is kept in bill.description instead.

    A version of exactly this kind of untruncated-field bug (a different
    column, same root cause) crashed nightly ingestion for four consecutive
    nights in August 2026 -- see docs/RUNBOOK.md's "Steps are deliberately
    isolated" note. This function exists so the truncation rule has a name
    and can be tested on its own."""
    full_title = matter.get("MatterName") or matter.get("MatterTitle") or f"Matter {matter['MatterId']}"
    return full_title if len(full_title) <= 490 else full_title[:489] + "…"


def _bill_session(matter: dict) -> str:
    """Legistar has no real 'session' concept (that's a state-legislature
    idea) -- we derive a year label from the agenda date so bills group
    sensibly, falling back to "current" when the date is missing or doesn't
    start with a parseable year."""
    year = str(matter.get("MatterAgendaDate", ""))[:4]
    return year if year.isdigit() else "current"


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
        jurisdiction_level=client_level(client_name),
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

        title = _bill_title(matter)

        entity = _get_or_create_bill_entity(db, client_name=client_name, matter_id=matter_id)
        if entity is None:
            entity = Entity(entity_type="bill", name=title, external_ids={})
            db.add(entity)

        entity.name = title
        entity.jurisdiction_level = client_level(client_name)
        entity.jurisdiction_name = jurisdiction
        entity.external_ids = {
            **entity.external_ids,
            "legistar_matter_id": str(matter_id),
            "legistar_client": client_name,
        }
        if matter.get("MatterTypeName"):
            entity.attributes = {**(entity.attributes or {}), "item_type": matter["MatterTypeName"]}  # see item_kind.py
        db.flush()

        source = Source(
            url=detail_url,
            document_reference=matter.get("MatterFile"),
            publisher=info.get("publisher") or f"{jurisdiction} City Clerk (Legistar)",
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
        bill.session = _bill_session(matter)
        bill.chamber = fit(matter.get("MatterBodyName"), CHAMBER_MAX_LENGTH)
        bill.status = normalize_status(matter.get("MatterStatusName")) or "Introduced"
        bill.introduced_date = _parse_date(matter.get("MatterIntroDate"))
        bill.last_action_date = _parse_date(matter.get("MatterPassedDate")) or bill.introduced_date
        bill.last_action = matter.get("MatterStatusName")
        bill.full_text_url = detail_url
        bill.source_system = "legistar"
        bill.description = matter.get("MatterTitle")
        bill.geo_scope_type = client_level(client_name)
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

        tag_local_bill(db, entity.id, title=title, description=bill.description or "")

        written.append(entity)

    db.commit()
    logger.info("Ingested %d local matters from Legistar client=%s", len(written), client_name)
    record_check(db, source_key(client_name), f"{len(written)} matters upserted")
    return written


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Ingest recent Legistar matters.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--nightly", action="store_true", help="every client marked nightly in CLIENT_JURISDICTIONS")
    group.add_argument("--client", help="one client token, e.g. fortlauderdale")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    clients = nightly_clients() if args.nightly else [args.client]
    failed = []
    for name in clients:
        session = SessionLocal()
        try:
            written = ingest_local_bills(session, client_name=name, limit=args.limit)
            print(f"Legistar ({name}): {len(written)} bills upserted")
        except Exception as exc:  # one city's outage must not stop the others
            logger.exception("Legistar ingest failed for %s", name)
            print(f"Legistar ({name}): FAILED: {exc}")
            failed.append(name)
        finally:
            session.close()
    raise SystemExit(1 if failed else 0)
