"""Florida's congressional delegation: roster, IDs and tenures
(Todoist 6hvxx9jPhj2Mp35p).

Source: github.com/unitedstates/congress-legislators (current members,
published as JSON). Each member becomes a person (keyed on the Bioguide ID,
a stable identifier) with one dated tenure per Florida term. The dataset
carries no Florida-legislature identifiers, so a member is NEVER linked to an
existing state-legislature person automatically: a same-name match in the
legislature is reported as a candidate for a person to confirm with
`--confirm BIOGUIDE=PERSON_UUID`.

Usage:
    python -m app.federal.roster [--confirm B001257=<uuid>]...
"""

from __future__ import annotations

import argparse
import logging
import uuid
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Entity, OfficeTenure
from app.pipeline.flsenate import USER_AGENT
from app.promises.winners import name_key

logger = logging.getLogger(__name__)

SOURCE_URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
SOURCE = "unitedstates/congress-legislators"
STATE = "FL"
HOUSE_SEATS = 28


def fetch_members(client: httpx.Client | None = None) -> list[dict]:
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True)
    resp = client.get(SOURCE_URL)
    resp.raise_for_status()
    return resp.json()


def _florida_terms(member: dict) -> list[dict]:
    return [t for t in member.get("terms", []) if t.get("state") == STATE and t.get("type") in ("rep", "sen")]


def florida_members(members: list[dict]) -> list[dict]:
    """Members whose CURRENT term is for Florida."""
    return [m for m in members if m.get("terms") and m["terms"][-1].get("state") == STATE]


def _person_for(db: Session, member: dict) -> tuple[Entity, bool]:
    bioguide = member["id"]["bioguide"]
    existing = db.execute(
        select(Entity).where(Entity.entity_type == "person", Entity.external_ids["bioguide_id"].as_string() == bioguide)
    ).scalar_one_or_none()
    current = member["terms"][-1]
    attributes = {
        "state": STATE,
        "role": "Rep" if current["type"] == "rep" else "Sen",
        "party": current.get("party"),
        "chamber": "us_house" if current["type"] == "rep" else "us_senate",
        **({"district": f"CD-{int(current['district']):03d}"} if current["type"] == "rep" and current.get("district") else {}),
    }
    attributes = {k: v for k, v in attributes.items() if v}
    name = member["name"].get("official_full") or f"{member['name']['first']} {member['name']['last']}"
    ids = {"bioguide_id": bioguide}
    for src, dst in (("govtrack", "govtrack_id"), ("opensecrets", "opensecrets_id"), ("fec", "fec_ids"), ("wikidata", "wikidata_id")):
        if member["id"].get(src):
            ids[dst] = member["id"][src]
    if existing:
        existing.name = name
        existing.attributes = {**(existing.attributes or {}), **attributes}
        existing.external_ids = {**(existing.external_ids or {}), **ids}
        return existing, False
    person = Entity(
        entity_type="person", name=name, jurisdiction_level="federal", jurisdiction_name="US",
        external_ids=ids, attributes=attributes,
    )
    db.add(person)
    db.flush()
    return person, True


def _tenures_for(db: Session, person: Entity, member: dict, *, today: date) -> int:
    added = 0
    terms = member["terms"]
    for term in _florida_terms(member):
        start = date.fromisoformat(term["start"])
        office = "us_house" if term["type"] == "rep" else "us_senate"
        district = term.get("district") if office == "us_house" else None
        row = db.execute(
            select(OfficeTenure).where(
                OfficeTenure.person_entity_id == person.id,
                OfficeTenure.office_type == office,
                OfficeTenure.district.is_(None) if district is None else OfficeTenure.district == district,
                OfficeTenure.start_date == start,
            )
        ).scalar_one_or_none()
        scheduled = date.fromisoformat(term["end"]) if term.get("end") else None
        is_current = term is terms[-1]
        if row is None:
            row = OfficeTenure(
                person_entity_id=person.id, office_type=office, state=STATE, district=district, start_date=start,
                source=SOURCE, source_url=SOURCE_URL, attributes={},
            )
            db.add(row)
            added += 1
        row.party = term.get("party")
        row.senate_class = term.get("class")
        row.official_url = term.get("url")
        # A past term's scheduled end is when it really ended, unless the
        # person was re-elected into the next one (the next term starts the
        # same day or within days); only a CURRENT term is open-ended.
        row.scheduled_end = scheduled
        if not is_current and scheduled:
            row.end_date = scheduled
    return added


def candidate_state_matches(db: Session, member: dict) -> list[Entity]:
    """Florida-legislature people with the same name key. Candidates for a
    human to confirm, never linked here."""
    key = name_key(member["name"].get("official_full") or f"{member['name']['first']} {member['name']['last']}")
    people = db.execute(
        select(Entity).where(Entity.entity_type == "person", Entity.jurisdiction_name == "FL", Entity.jurisdiction_level == "state")
    ).scalars()
    return [p for p in people if not (p.attributes or {}).get("committee") and name_key(p.name) == key]


def import_roster(db: Session, members: list[dict], *, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    fl = florida_members(members)
    out = {"members": len(fl), "people_created": 0, "tenures_added": 0, "possible_state_matches": [], "vacant_districts": []}
    filled: set[int] = set()
    for m in fl:
        person, created = _person_for(db, m)
        out["people_created"] += created
        out["tenures_added"] += _tenures_for(db, person, m, today=today)
        cur = m["terms"][-1]
        if cur["type"] == "rep":
            filled.add(cur["district"])
        cands = candidate_state_matches(db, m)
        if cands and not (person.attributes or {}).get("same_person_as"):
            out["possible_state_matches"].append(
                {"bioguide": m["id"]["bioguide"], "name": person.name, "candidates": [{"id": str(c.id), "name": c.name, "district": (c.attributes or {}).get("district")} for c in cands]}
            )
    out["vacant_districts"] = sorted(set(range(1, HOUSE_SEATS + 1)) - filled)
    db.flush()
    return out


def confirm_same_person(db: Session, bioguide: str, state_person_id: uuid.UUID) -> None:
    """A person has checked that this state-legislature person and this
    member are one human: record it on the federal person (both ways), so
    one person page can show both tenures. Nothing else is merged."""
    fed = db.execute(
        select(Entity).where(Entity.entity_type == "person", Entity.external_ids["bioguide_id"].as_string() == bioguide)
    ).scalar_one()
    state = db.get(Entity, state_person_id)
    if state is None or state.entity_type != "person":
        raise ValueError("no such person")
    fed.attributes = {**(fed.attributes or {}), "same_person_as": str(state.id)}
    state.attributes = {**(state.attributes or {}), "same_person_as": str(fed.id)}
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--confirm", action="append", default=[], metavar="BIOGUIDE=UUID")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    members = fetch_members()
    with SessionLocal() as db:
        result = import_roster(db, members)
        for item in args.confirm:
            bio, _, pid = item.partition("=")
            confirm_same_person(db, bio, uuid.UUID(pid))
        db.commit()
    logger.info("roster: %s", {k: v for k, v in result.items() if k != "possible_state_matches"})
    for m in result["possible_state_matches"]:
        logger.info("CONFIRM? %s (%s) may be state person(s): %s", m["name"], m["bioguide"], m["candidates"])


if __name__ == "__main__":
    main()
