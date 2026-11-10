"""Florida delegation sponsorships and cosponsorships from Congress.gov
(Todoist 6hvxx9hHg2G2cWjp).

For each current Florida member (a person with a Bioguide ID from the roster
import), read the bills they sponsored and cosponsored in the current
Congress and record `sponsor` / `co_sponsor` relationships. These bills are
marked `delegation_sponsored`, which is what permits summaries and tags
(policy.py). Roll-call votes are in rollcalls.py.

Usage (needs CONGRESS_API_KEY):
    python -m app.federal.sponsorships [--congress 119]
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.federal.bills import TYPES, upsert_bill
from app.federal.congress_api import CongressClient
from app.models import Entity, Relationship, Source
from app.pipeline.source_checks import record_check

logger = logging.getLogger(__name__)

CURRENT_CONGRESS = 119
RELATIONSHIPS = {"sponsored-legislation": "sponsor", "cosponsored-legislation": "co_sponsor"}


def delegation_members(db: Session) -> list[Entity]:
    return list(
        db.execute(
            select(Entity).where(
                Entity.entity_type == "person",
                Entity.external_ids.has_key("bioguide_id"),
                Entity.attributes["state"].as_string() == "FL",
            )
        ).scalars()
    )


def _link(db: Session, person: Entity, bill: Entity, rel_type: str, source_id) -> bool:
    exists = db.execute(
        select(Relationship.id).where(
            Relationship.from_entity_id == person.id, Relationship.to_entity_id == bill.id,
            Relationship.relationship_type == rel_type,
        )
    ).first()
    if exists:
        return False
    db.add(Relationship(from_entity_id=person.id, to_entity_id=bill.id, relationship_type=rel_type, source_id=source_id))
    return True


def sync_member(db: Session, client: CongressClient, person: Entity, *, congress: int = CURRENT_CONGRESS) -> dict:
    bioguide = person.external_ids["bioguide_id"]
    out = {"bills": 0, "links": 0, "skipped": 0}
    for path, rel_type in RELATIONSHIPS.items():
        for item in client.paged(f"/member/{bioguide}/{path}", path.split("-")[0] + "Legislation"):
            slug = str(item.get("type", "")).lower()
            if item.get("congress") != congress or slug not in TYPES or not str(item.get("number", "")).isdigit():
                out["skipped"] += 1  # an earlier Congress, or an amendment/nomination
                continue
            latest = item.get("latestAction") or {}
            bill = upsert_bill(
                db, congress=congress, slug=slug, number=int(item["number"]), title=item.get("title"),
                introduced=item.get("introducedDate"), latest_action=latest.get("text"),
                latest_action_date=latest.get("actionDate"),
                policy_area=(item.get("policyArea") or {}).get("name"), delegation=True,
            )
            src = db.execute(
                select(Source).where(Source.source_type == "congress_bill", Source.url == bill.bill.full_text_url)
            ).scalars().first()
            out["bills"] += 1
            out["links"] += _link(db, person, bill, rel_type, src.id if src else None)
    db.flush()
    return out


def sync_delegation(db: Session, client: CongressClient, *, congress: int = CURRENT_CONGRESS) -> dict:
    totals = {"members": 0, "bills": 0, "links": 0, "skipped": 0}
    for person in delegation_members(db):
        res = sync_member(db, client, person, congress=congress)
        db.commit()  # a member's lists are one unit; an interrupted run resumes at the next member
        totals["members"] += 1
        for k in ("bills", "links", "skipped"):
            totals[k] += res[k]
    record_check(db, "congress_sponsorships", f"{totals['members']} members, {totals['links']} new links")
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--congress", type=int, default=CURRENT_CONGRESS)
    parser.add_argument("--api-key", help="override CONGRESS_API_KEY (DEMO_KEY works for a small trial)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    client = CongressClient(args.api_key)
    with SessionLocal() as db:
        logger.info("sponsorships: %s (%d requests)", sync_delegation(db, client, congress=args.congress), client.requests)


if __name__ == "__main__":
    main()
