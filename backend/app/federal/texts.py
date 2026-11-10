"""Text of federal bills the Florida delegation sponsored or cosponsored, and
the Florida places each names (Todoist 6hvxx9pcxPGM66Wp).

Congress.gov lists a bill's published text versions (Introduced, Engrossed,
Enrolled ...) and links each to the Government Publishing Office's printed
text. We keep every version as printed and mirror the latest into
`Bill.full_text`, which is what the layer generator reads. Only delegation
bills get text (policy.py); the rest stay a title, a status and a link.

Usage (needs CONGRESS_API_KEY):
    python -m app.federal.texts [--limit 50]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import time
from datetime import date, datetime, timezone
from typing import Callable

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.federal.congress_api import CongressClient
from app.federal.places import METHOD_VERSION, find_places
from app.models import Bill, Entity, FederalBillText, FederalPlaceFinding
from app.pipeline.flsenate import USER_AGENT
from app.pipeline.source_checks import record_check

logger = logging.getLogger(__name__)

MAX_TEXT_BYTES = 12 * 1024 * 1024
PREFERRED_FORMAT = "Formatted Text"


def gpo_text(html: str) -> str:
    """The printed text from a GPO page (a <pre> block), entities decoded."""
    soup = BeautifulSoup(html, "html.parser")
    pre = soup.find("pre")
    text = (pre or soup).get_text()
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip("\n")


def version_links(payload: dict) -> list[dict]:
    """[{type, date, url}] for each text version that has printed text."""
    out = []
    for v in payload.get("textVersions") or []:
        url = next((f.get("url") for f in v.get("formats") or [] if f.get("type") == PREFERRED_FORMAT), None)
        if not url:
            continue
        try:
            d = date.fromisoformat((v.get("date") or "")[:10]) if v.get("date") else None
        except ValueError:
            d = None
        out.append({"type": v.get("type"), "date": d, "url": url})
    return out


def analyze_text(db: Session, ft: FederalBillText) -> int:
    """(Re)find the Florida places in one text version. Replaces earlier
    findings for this text, so a new method version never leaves old ones."""
    db.execute(delete(FederalPlaceFinding).where(FederalPlaceFinding.text_id == ft.id))
    n = 0
    for f in find_places(ft.text):
        db.add(FederalPlaceFinding(
            bill_entity_id=ft.bill_entity_id, text_id=ft.id, kind=f.kind, matched_term=f.matched_term[:200],
            counties=list(f.counties), section=f.section, quote_text=f.quote_text,
            char_start=f.char_start, char_end=f.char_end, method_version=METHOD_VERSION,
        ))
        n += 1
    db.flush()
    return n


def store_version(db: Session, entity: Entity, *, version_type: str | None, version_date: date | None,
                  url: str, text: str, now: datetime | None = None) -> FederalBillText | None:
    """Keep one version (None if we already have it) and analyze it."""
    if db.execute(select(FederalBillText.id).where(FederalBillText.bill_entity_id == entity.id,
                                                    FederalBillText.source_url == url)).first():
        return None
    ft = FederalBillText(
        bill_entity_id=entity.id, version_type=version_type, version_date=version_date, source_url=url, text=text,
        text_hash=hashlib.sha256(text.encode()).hexdigest(), fetched_at=now or datetime.now(timezone.utc),
    )
    db.add(ft)
    db.flush()
    analyze_text(db, ft)
    refresh_latest(db, entity)
    return ft


def refresh_latest(db: Session, entity: Entity) -> None:
    """Bill.full_text follows the newest version (dated ones first)."""
    rows = db.execute(select(FederalBillText).where(FederalBillText.bill_entity_id == entity.id)).scalars().all()
    if not rows:
        return
    latest = max(rows, key=lambda r: (r.version_date or date.min, r.created_at or datetime.min.replace(tzinfo=timezone.utc)))
    if entity.bill is not None:
        entity.bill.full_text = latest.text


Fetch = Callable[[str], str | None]


def http_fetch(client: httpx.Client | None = None, *, pause: float = 1.0, sleep=time.sleep) -> Fetch:
    client = client or httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    def fetch(url: str) -> str | None:
        sleep(pause)
        resp = client.get(url)
        if resp.status_code != 200 or len(resp.content) > MAX_TEXT_BYTES:
            return None
        return resp.text

    return fetch


def _coords(entity: Entity) -> tuple[int, str, int]:
    congress, slug, number = entity.external_ids["congress_bill"].split("-")
    return int(congress), slug, int(number)


def sync_texts(db: Session, client: CongressClient, fetch: Fetch, *, limit: int | None = 50) -> dict:
    """Fetch missing text versions for delegation bills, newest-acting
    first. A bill's versions are checked again whenever it has fewer stored
    versions than the API lists, so a bill that passed a chamber gains its
    new version."""
    stmt = (
        select(Entity).join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.source_system == "congress",
               Entity.attributes["delegation_sponsored"].as_boolean().is_(True))
        .order_by(Bill.last_action_date.desc().nulls_last())
    )
    out = {"bills": 0, "versions": 0, "findings": 0, "no_text": 0}
    for entity in db.execute(stmt).scalars():
        if limit is not None and out["bills"] >= limit:
            break
        congress, slug, number = _coords(entity)
        links = version_links(client.get(f"/bill/{congress}/{slug}/{number}/text"))
        out["bills"] += 1
        if not links:
            out["no_text"] += 1  # not printed yet, or only a PDF
            continue
        for link in links:
            if db.execute(select(FederalBillText.id).where(FederalBillText.bill_entity_id == entity.id,
                                                            FederalBillText.source_url == link["url"])).first():
                continue
            html = fetch(link["url"])
            if not html:
                continue
            ft = store_version(db, entity, version_type=link["type"], version_date=link["date"], url=link["url"], text=gpo_text(html))
            if ft:
                out["versions"] += 1
                out["findings"] += len(ft.findings)
        db.commit()
    record_check(db, "congress_texts", f"{out['versions']} new text versions, {out['findings']} Florida places")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--api-key")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    client = CongressClient(args.api_key)
    with SessionLocal() as db:
        logger.info("texts: %s", sync_texts(db, client, http_fetch(), limit=args.limit))


if __name__ == "__main__":
    main()
