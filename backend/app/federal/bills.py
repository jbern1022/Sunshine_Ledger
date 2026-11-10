"""Federal bill records, however we first hear of them (sponsorship lists or a
roll call). One entity per bill, keyed `119-hr-10840`."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, Entity, Source
from app.pipeline._text_limits import CHAMBER_MAX_LENGTH, fit

JURISDICTION = "US"

# slug -> (display prefix, congress.gov URL segment, originating chamber)
TYPES = {
    "hr": ("H.R.", "house-bill", "House"),
    "s": ("S.", "senate-bill", "Senate"),
    "hres": ("H.Res.", "house-resolution", "House"),
    "sres": ("S.Res.", "senate-resolution", "Senate"),
    "hjres": ("H.J.Res.", "house-joint-resolution", "House"),
    "sjres": ("S.J.Res.", "senate-joint-resolution", "Senate"),
    "hconres": ("H.Con.Res.", "house-concurrent-resolution", "House"),
    "sconres": ("S.Con.Res.", "senate-concurrent-resolution", "Senate"),
}

# House Clerk "legis-num" / Senate "document_type" spellings -> slug
_LEGIS_NUM = {
    "H R": "hr", "S": "s", "H RES": "hres", "S RES": "sres", "H J RES": "hjres", "S J RES": "sjres",
    "H CON RES": "hconres", "S CON RES": "sconres",
    "H.R.": "hr", "S.": "s", "H.RES.": "hres", "S.RES.": "sres", "H.J.RES.": "hjres", "S.J.RES.": "sjres",
    "H.CON.RES.": "hconres", "S.CON.RES.": "sconres",
}


def parse_legis_num(text: str | None) -> tuple[str, int] | None:
    """('hr', 1234) from 'H R 1234', 'H CON RES 14', 'S. 9'. None for
    anything that is not a bill or resolution (quorum calls, nominations,
    the Speaker election, amendments)."""
    m = re.match(r"^\s*([A-Za-z.\s]+?)\s*(\d+)\s*$", text or "")
    if not m:
        return None
    slug = _LEGIS_NUM.get(re.sub(r"\s+", " ", m.group(1).strip().upper()))
    return (slug, int(m.group(2))) if slug else None


def bill_key(congress: int, slug: str, number: int) -> str:
    return f"{congress}-{slug}-{number}"


def congress_url(congress: int, slug: str, number: int) -> str:
    ordinal = {1: "st", 2: "nd", 3: "rd"}.get(congress % 10 if congress % 100 not in (11, 12, 13) else 0, "th")
    return f"https://www.congress.gov/bill/{congress}{ordinal}-congress/{TYPES[slug][1]}/{number}"


def coarse_status(latest_action: str | None) -> str:
    """A small, honest status from the latest action text; the full text is
    kept in last_action."""
    t = (latest_action or "").lower()
    if "became public law" in t or "signed by president" in t:
        return "Became Law"
    if "vetoed" in t:
        return "Vetoed"
    if "passed senate" in t or "agreed to in senate" in t or "passed/agreed to in senate" in t:
        return "Passed Senate"
    if "passed house" in t or "agreed to in house" in t or "passed/agreed to in house" in t:
        return "Passed House"
    if "referred to" in t or not t:
        return "Introduced"
    return "In Progress"


def _d(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def upsert_bill(
    db: Session,
    *,
    congress: int,
    slug: str,
    number: int,
    title: str | None = None,
    introduced: str | None = None,
    latest_action: str | None = None,
    latest_action_date: str | None = None,
    policy_area: str | None = None,
    delegation: bool = False,
) -> Entity:
    """Create or refresh a federal bill. `delegation=True` marks it as
    sponsored/cosponsored by a Florida delegation member, which is what
    allows summaries and tags (see policy.py); it is never cleared."""
    key = bill_key(congress, slug, number)
    entity = db.execute(
        select(Entity).where(Entity.entity_type == "bill", Entity.external_ids["congress_bill"].as_string() == key)
    ).scalar_one_or_none()
    prefix, _, chamber = TYPES[slug]
    url = congress_url(congress, slug, number)
    if entity is None:
        entity = Entity(
            entity_type="bill", name=(title or f"{prefix} {number}")[:490], jurisdiction_level="federal",
            jurisdiction_name=JURISDICTION, external_ids={"congress_bill": key}, attributes={},
        )
        db.add(entity)
        db.flush()
        db.add(Source(url=url, document_reference=f"{prefix} {number}", publisher="Congress.gov", source_type="congress_bill",
                      retrieved_at=datetime.now(timezone.utc), metadata_json={"congress": congress, "type": slug}))
    elif title:
        entity.name = title[:490]
    attrs = dict(entity.attributes or {})
    if delegation:
        attrs["delegation_sponsored"] = True
    if policy_area:
        attrs["policy_area"] = policy_area
    entity.attributes = attrs

    bill = entity.bill
    if bill is None:
        bill = Bill(entity_id=entity.id, bill_number=f"{prefix} {number}", session=f"{congress}th Congress",
                    status="Introduced", source_system="congress")
        entity.bill = bill  # keep the relationship in step with what we add
    bill.chamber = fit(chamber, CHAMBER_MAX_LENGTH)
    bill.full_text_url = url
    if introduced and _d(introduced):
        bill.introduced_date = _d(introduced)
    if latest_action:
        bill.last_action = latest_action
        bill.last_action_date = _d(latest_action_date) or bill.last_action_date
        bill.status = coarse_status(latest_action)
    # The title is the summarizer's input only for delegation bills; policy.py
    # keeps the generators away from the rest.
    if title and (delegation or attrs.get("delegation_sponsored")):
        bill.description = title
    db.flush()
    return entity
