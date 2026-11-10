"""House and Senate roll-call votes involving the Florida delegation
(Todoist 6hvxx9hHg2G2cWjp).

Sources are the chambers' own published roll-call XML: the House Clerk
(clerk.house.gov/evs/<year>/roll<NNN>.xml, members keyed by Bioguide ID) and
the Senate (senate.gov/legislative/LIS/roll_call_votes, members keyed by LIS
ID). Neither site publishes a robots.txt; we still pause between requests.

Rules:
- Roll calls only. A voice vote has no member-by-member record, so nothing is
  attributed to anyone; we do not infer one.
- A roll call is stored only when it is about a bill or resolution (the
  quorum calls, Speaker elections and nominations are counted, not stored).
- Only Florida delegation members' individual votes are stored as `voted`
  relationships; the vote Event keeps the chamber's own totals.
- Plain facts: how each member voted. No score, no "alignment".

Usage:
    python -m app.federal.rollcalls [--congress 119] [--year 2025 --year 2026]
"""

from __future__ import annotations

import argparse
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.federal.bills import TYPES, bill_key, parse_legis_num, upsert_bill
from app.federal.sponsorships import CURRENT_CONGRESS, delegation_members
from app.models import Entity, Event, Relationship, Source
from app.pipeline.flsenate import USER_AGENT
from app.pipeline.source_checks import record_check

logger = logging.getLogger(__name__)

HOUSE_URL = "https://clerk.house.gov/evs/{year}/roll{num:03d}.xml"
SENATE_URL = "https://www.senate.gov/legislative/LIS/roll_call_votes/vote{congress}{session}/vote_{congress}_{session}_{num:05d}.xml"
PAUSE_SECONDS = 2.0


@dataclass
class RollCall:
    chamber: str  # house | senate
    congress: int
    number: int
    year: int
    url: str
    when: date | None
    question: str
    description: str
    result: str
    legis_num: str | None
    totals: dict
    votes: dict[str, str] = field(default_factory=dict)  # member id (bioguide | lis) -> vote text

    @property
    def roll_call_id(self) -> str:
        return f"{self.chamber}-{self.congress}-{self.year}-{self.number}"


def _text(el: ET.Element | None, path: str) -> str:
    node = el.find(path) if el is not None else None
    return (node.text or "").strip() if node is not None else ""


def _int(value: str) -> int | None:
    return int(value) if value.strip().isdigit() else None


def parse_house(xml_bytes: bytes, *, url: str, year: int) -> RollCall | None:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    if root.tag != "rollcall-vote":
        return None
    meta = root.find("vote-metadata")
    try:
        when = datetime.strptime(_text(meta, "action-date"), "%d-%b-%Y").date()
    except ValueError:
        when = None
    totals = root.find("vote-metadata/vote-totals/totals-by-vote")
    rc = RollCall(
        chamber="house", congress=int(_text(meta, "congress") or 0), number=int(_text(meta, "rollcall-num") or 0), year=year,
        url=url, when=when, question=_text(meta, "vote-question"), description=_text(meta, "vote-desc"),
        result=_text(meta, "vote-result"), legis_num=_text(meta, "legis-num") or None,
        totals={
            "yea": _int(_text(totals, "yea-total")), "nay": _int(_text(totals, "nay-total")),
            "present": _int(_text(totals, "present-total")), "not_voting": _int(_text(totals, "not-voting-total")),
        },
    )
    for rv in root.iterfind("vote-data/recorded-vote"):
        leg = rv.find("legislator")
        if leg is not None and leg.get("name-id"):
            rc.votes[leg.get("name-id")] = _text(rv, "vote")
    return rc


def parse_senate(xml_bytes: bytes, *, url: str) -> RollCall | None:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    if root.tag != "roll_call_vote":
        return None
    try:
        when = datetime.strptime(_text(root, "vote_date").split(",  ")[0].strip(), "%B %d, %Y").date()
    except ValueError:
        when = None
    doc_type, doc_num = _text(root, "document/document_type"), _text(root, "document/document_number")
    rc = RollCall(
        chamber="senate", congress=int(_text(root, "congress") or 0), number=int(_text(root, "vote_number") or 0),
        year=int(_text(root, "congress_year") or 0), url=url, when=when, question=_text(root, "question"),
        description=_text(root, "vote_document_text") or _text(root, "vote_title"), result=_text(root, "vote_result"),
        legis_num=f"{doc_type} {doc_num}".strip() if doc_type and doc_num else None,
        totals={"yea": _int(_text(root, "count/yeas")), "nay": _int(_text(root, "count/nays")),
                "present": _int(_text(root, "count/present")), "not_voting": _int(_text(root, "count/absent"))},
    )
    for m in root.iterfind("members/member"):
        lis = _text(m, "lis_member_id")
        if lis:
            rc.votes[lis] = _text(m, "vote_cast")
    return rc


Fetch = Callable[[str], bytes | None]


def http_fetch(client: httpx.Client | None = None, *, pause: float = PAUSE_SECONDS, sleep=time.sleep) -> Fetch:
    client = client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=False)

    def fetch(url: str) -> bytes | None:
        sleep(pause)
        resp = client.get(url)
        return resp.content if resp.status_code == 200 else None

    return fetch


def store_roll_call(db: Session, rc: RollCall, members_by_id: dict[str, Entity], now: datetime | None = None) -> str:
    """Returns 'stored', 'duplicate', 'no_bill' or 'no_delegation_votes'."""
    parsed = parse_legis_num(rc.legis_num)
    if parsed is None:
        return "no_bill"
    mine = {mid: v for mid, v in rc.votes.items() if mid in members_by_id}
    if not mine:
        return "no_delegation_votes"
    slug, number = parsed
    bill = upsert_bill(db, congress=rc.congress, slug=slug, number=number, title=None)
    dup = db.execute(
        select(Event.id).where(
            Event.entity_id == bill.id, Event.event_type == "vote",
            Event.attributes["roll_call_id"].as_string() == rc.roll_call_id,
        )
    ).first()
    if dup:
        return "duplicate"
    src = Source(url=rc.url, publisher="U.S. House Clerk" if rc.chamber == "house" else "U.S. Senate", source_type=f"congress_{rc.chamber}_roll_call",
                 retrieved_at=now or datetime.now(timezone.utc), metadata_json={"roll_call_id": rc.roll_call_id})
    db.add(src)
    db.flush()
    db.add(Event(
        entity_id=bill.id, event_type="vote", event_date=rc.when or date.today(),
        title=f"{rc.question}: {rc.description}"[:480] if rc.description else (rc.question or "Roll call vote"),
        attributes={"roll_call_id": rc.roll_call_id, "chamber": rc.chamber.title(), "question": rc.question,
                    "result": rc.result, **{k: v for k, v in rc.totals.items() if v is not None}},
        source_id=src.id,
    ))
    for mid, vote in mine.items():
        db.add(Relationship(from_entity_id=members_by_id[mid].id, to_entity_id=bill.id, relationship_type="voted",
                            attributes={"roll_call_id": rc.roll_call_id, "vote": vote}, source_id=src.id))
    return "stored"


def _members_by_id(db: Session) -> dict[str, Entity]:
    out: dict[str, Entity] = {}
    for p in delegation_members(db):
        out[p.external_ids["bioguide_id"]] = p
        if p.external_ids.get("lis_id"):
            out[p.external_ids["lis_id"]] = p
    return out


def _last_stored(db: Session, chamber: str, congress: int, year: int) -> int:
    prefix = f"{chamber}-{congress}-{year}-"
    ids = db.execute(select(Event.attributes["roll_call_id"].as_string()).where(Event.event_type == "vote",
                     Event.attributes["roll_call_id"].as_string().like(prefix + "%"))).scalars().all()
    return max((int(i.rsplit("-", 1)[1]) for i in ids), default=0)


def sync_chamber(db: Session, fetch: Fetch, *, chamber: str, congress: int, year: int, start: int | None = None,
                 max_roll_calls: int = 1000) -> dict:
    """Walk roll-call numbers from the first not yet seen until the chamber
    has no more. Progress is committed per roll call, so a stopped run
    resumes. (A roll call that fails the delegation or bill test is not
    stored, so it is re-read next run; they are cheap.)"""
    members = _members_by_id(db)
    session = 1 if year % 2 == 1 else 2
    counts = {"stored": 0, "duplicate": 0, "no_bill": 0, "no_delegation_votes": 0, "fetched": 0}
    num = start or (_last_stored(db, chamber, congress, year) + 1)
    while num <= max_roll_calls:
        url = (HOUSE_URL.format(year=year, num=num) if chamber == "house"
               else SENATE_URL.format(congress=congress, session=session, num=num))
        body = fetch(url)
        rc = None if body is None else (parse_house(body, url=url, year=year) if chamber == "house" else parse_senate(body, url=url))
        if rc is None or rc.number != num:
            break  # past the last roll call
        counts["fetched"] += 1
        counts[store_roll_call(db, rc, members)] += 1
        db.commit()
        num += 1
    return counts


def sync_rollcalls(db: Session, fetch: Fetch, *, congress: int = CURRENT_CONGRESS, years: tuple[int, ...] = (2025, 2026)) -> dict:
    totals = {}
    for chamber in ("house", "senate"):
        for year in years:
            totals[f"{chamber}_{year}"] = sync_chamber(db, fetch, chamber=chamber, congress=congress, year=year)
    record_check(db, "congress_rollcalls", "; ".join(f"{k}: {v['stored']} stored" for k, v in totals.items()))
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--congress", type=int, default=CURRENT_CONGRESS)
    parser.add_argument("--year", type=int, action="append")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        logger.info("roll calls: %s", sync_rollcalls(db, http_fetch(), congress=args.congress, years=tuple(args.year or (2025, 2026))))


if __name__ == "__main__":
    main()
