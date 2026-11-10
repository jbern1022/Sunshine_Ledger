"""Florida senators' Congressionally Directed Spending requests (Senate Appropriations Committee chart).

    python -m app.federal.senate_cds --fiscal-year 2027

The committee's public chart (appropriations.senate.gov/congressionally-directed-spending-requests-fy2027)
fills its table from the site's own data endpoint, the same request the page makes for every visitor. We
ask it for the same thing, politely: the chart is paged through once at 500 rows per request with a pause
between requests and a hard cap on requests (its search box matches project text, not the member). Nothing is fetched except what the chart shows. The
site states no reuse licence for the list (checked 2026-11-10); the lists are published by Congress, but
confirm before showing more than a link-back.

Stored in `federal_earmarks` with chamber "senate", stage "requested" (a request, never funding) and district
"FL" (a senator has no district). A row is kept only when the chart says the member's state is FL, and is
linked to a person only when exactly one US Senate tenure matches the surname.
"""

from __future__ import annotations

import argparse
import re
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.federal.earmarks import _amount, _s
from app.models import Entity, FederalEarmark, OfficeTenure

CHART_URL = "https://www.appropriations.senate.gov/congressionally-directed-spending-requests-fy{year}"
ENDPOINT = "https://www.appropriations.senate.gov/cfc_extensions/data/cds_requests.cfc"
METHOD_BY_YEAR = {2027: "getCDSTable27"}
PAGE = 500
MAX_REQUESTS = 40
PAUSE_SECONDS = 6.0
USER_AGENT = "sunshine-ledger-research/1.0"


class SenateCdsError(RuntimeError):
    pass


def fetch_florida(
    year: int, *, client: httpx.Client | None = None, sleep=time.sleep, max_requests: int = MAX_REQUESTS,
) -> list[dict]:
    """Rows whose member_state is FL. The endpoint's search box matches project text, not the member, so the
    only way to find a state's senators is to page through the whole chart (about 13,400 rows in FY27): 500
    rows per request, a pause between requests, and a cap on requests."""
    method = METHOD_BY_YEAR.get(year)
    if method is None:
        raise SenateCdsError(f"no known data method for fiscal year {year}; check the chart's page source")
    client = client or httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT})
    out: dict[int, dict] = {}
    start = requests = 0
    while True:
        if requests >= max_requests:
            raise SenateCdsError(f"stopped at {max_requests} requests before reaching the end of the chart; raise the cap deliberately")
        if requests:
            sleep(PAUSE_SECONDS)
        requests += 1
        resp = client.post(ENDPOINT, data={"method": method, "start": start, "length": PAGE, "search": ""})
        resp.raise_for_status()
        body = resp.json()
        rows = body.get("DATA")
        if not isinstance(rows, list):
            raise SenateCdsError(f"unexpected response: {str(body)[:200]}")
        for r in rows:
            if r.get("member_state") == "FL" and r.get("row") is not None:
                out[int(r["row"])] = r
        total = int(body.get("RECORDSFILTERED") or 0)
        start += PAGE
        if not rows or start >= total:
            return list(out.values())


def _senator_surname(member: str) -> str:
    return re.sub(r"^(Senator|Sen\.)\s+", "", member.strip(), flags=re.IGNORECASE)


def match_senator(db: Session, surname: str):
    people = db.execute(
        select(Entity).join(OfficeTenure, OfficeTenure.person_entity_id == Entity.id)
        .where(OfficeTenure.office_type == "us_senate", OfficeTenure.state == "FL")
    ).scalars().unique().all()
    want = surname.strip().lower()
    hits = {p.id for p in people if want and (p.name or "").lower().split()[-1:] == want.split()[-1:]}
    return next(iter(hits)) if len(hits) == 1 else None


def import_rows(db: Session, rows: list[dict], *, fiscal_year: int) -> dict:
    stats = {"rows": len(rows), "new": 0, "existing": 0, "linked": 0}
    source = CHART_URL.format(year=fiscal_year)
    for r in rows:
        last = _senator_surname(r.get("member") or "")
        recipient, desc, subc = _s(r.get("recipient")), _s(r.get("project_purpose")), _s(r.get("subcommittee"))
        if not (last and recipient and desc and subc):
            continue
        place = ", ".join(x for x in (_s(r.get("project_location")), _s(r.get("project_state"))) if x)
        exists = db.execute(select(FederalEarmark.id).where(
            FederalEarmark.fiscal_year == fiscal_year, FederalEarmark.stage == "requested", FederalEarmark.member_last == last,
            FederalEarmark.district == "FL", FederalEarmark.subcommittee == subc, FederalEarmark.recipient == recipient[:300],
            FederalEarmark.description == desc,
        )).first()
        if exists:
            stats["existing"] += 1
            continue
        person = match_senator(db, last)
        stats["linked"] += 1 if person else 0
        db.add(FederalEarmark(
            fiscal_year=fiscal_year, stage="requested", chamber="senate", member_last=last, district="FL", subcommittee=subc,
            recipient=recipient[:300], description=desc, recipient_address=place or None, amount=_amount(r.get("amount_requested")),
            member_url=_s(r.get("cds_website")), source_url=source, person_entity_id=person,
        ))
        stats["new"] += 1
    db.commit()
    return stats


def main() -> None:
    from app.db import SessionLocal

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fiscal-year", type=int, required=True)
    a = p.parse_args()
    rows = fetch_florida(a.fiscal_year)
    db = SessionLocal()
    try:
        print(import_rows(db, rows, fiscal_year=a.fiscal_year))
    finally:
        db.close()


if __name__ == "__main__":
    main()
