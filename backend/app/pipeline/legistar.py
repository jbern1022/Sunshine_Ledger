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

import html
import logging
import re
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
    # County commission, live Legistar (2 bodies; newest matter 2026-10-12). Its
    # types are agenda categories ("Consent Item", "Regular Item") and nearly
    # every title is "MOTION TO ...", so the kind of record comes from the title
    # (see derived_item_type). No sponsors are listed on its matters.
    "broward": {
        "jurisdiction": "Broward County",
        "county": "Broward County",
        "level": "county",
        "publisher": "Broward County Commission (Legistar)",
        "item_type_from_title": True,
        # Exhibit names vary ("Exhibit 2 - Proposed Ordinance", "Exhibit 1 -
        # Resolution to Publish Notice ..."); the proposed form is preferred.
        "text_attachment": [
            r"^\s*exhibit\s*\d+\s*[-\u2013\u2014]\s*proposed\s+(ordinance|resolution)",
            r"^\s*exhibit\s*\d+\s*[-\u2013\u2014]\s*(ordinance|resolution)\b",
        ],
        "nightly": True,
        "label": "Broward County Commission (Legistar)",
        "note": "The most recent county commission matters. Most are motions; the record is labelled "
        "legislation only when the motion adopts a resolution or enacts an ordinance. "
        "Matters without a PDF attachment have no full text.",
    },
    # Coral Gables, Key West, Delray Beach: sampled 2026-10-13 (200 newest
    # matters, sponsors on 12, attachments on 5 ordinances/resolutions each).
    "coralgables": {
        "jurisdiction": "Coral Gables",
        "county": "Miami-Dade County",
        "nightly": True,
        "label": "Coral Gables City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
        # "R-2025-465 Signed" (the adopted resolution), "Draft Ordinance".
        "text_attachment": [r"^\s*r-\d{4}-\d+", r"draft\s+ordinance", r"^\s*\d{4}\s+.*resolution\b"],
    },
    "keywest": {
        "jurisdiction": "Key West",
        "county": "Monroe County",
        "nightly": True,
        "label": "Key West City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
        # The attachment is simply named "Resolution" / "Resolution 24-137".
        "text_attachment": [r"^\s*resolution\s*$", r"^\s*(resolution|ordinance)\s+\d", r"^\s*ordinance\s*$"],
    },
    "delraybeach": {
        "jurisdiction": "Delray Beach",
        "county": "Palm Beach County",
        "nightly": True,
        # Sponsors are city departments ("Development Services Department"), not people.
        "body_sponsors_as_committees": True,
        "label": "Delray Beach City Commission (Legistar)",
        "note": "The most recent commission matters. Many are development requests, which are labelled "
        "as such rather than as legislation. Matters without a PDF attachment have no full text.",
        # "Ordinance No. 40-26" (anchored: "Legal Review, Ordinance No. 40-26" is not it).
        "text_attachment": [r"^\s*(ordinance|resolution)\s+no\.", r"^\s*resolution\b"],
    },
    # Hollywood and Clearwater: sampled 2026-10-13 (200 newest matters each, no
    # sponsors). Hollywood's own types ("Resolution", "Ordinance", "Planning - PDB",
    # "Presentation") already map to the right kinds. Clearwater types 166 of 200
    # as "Action Item", so those read the kind from the title.
    "hollywoodfl": {
        "jurisdiction": "Hollywood",
        "county": "Broward County",
        "nightly": True,
        "label": "Hollywood City Commission (Legistar)",
        "note": "The most recent commission matters. Planning board items, presentations and proclamations "
        "are labelled as such rather than as legislation. Matters without a PDF attachment have no full text.",
        # "Ordinance", "Resolution - Settlement of ...", "Reso - CRA Meeting Time Change",
        # "1 - FY27 Gen Fund SS Grants Resolution". Not "Business Impact Statement for Ordinance ...".
        "text_attachment": [r"^\s*(ordinance|resolution)\b", r"^\s*reso\b", r"\bresolution\b"],
    },
    "clearwater": {
        "jurisdiction": "Clearwater",
        "county": "Pinellas County",
        "nightly": True,
        "adopted_instrument_from_title": ["Action Item"],
        "label": "Clearwater City Council (Legistar)",
        "note": "The most recent council matters. Most are agenda actions (contracts, code-enforcement cases, "
        "presentations); an item is labelled legislation only when it adopts an ordinance or resolution. "
        "Matters without a PDF attachment have no full text.",
        # "9937-26_Operating_Ordinance_27", "Ordinance_9939-26.pdf", "26-09-01_Ordinance 9889-26.docx",
        # then "Resolution 26-17", "MILLAGE RESOLUTION-26-01.pdf". Exhibits carry neither word.
        "text_attachment": [r"(?<![a-z])ordinance", r"resolution[\s_-]*\d{2}-\d+"],
    },
    # Miramar, Doral, Hallandale Beach, Coconut Creek, Pinecrest: sampled 2026-10-15
    # (200 newest matters each). Their own types (Resolution / Ordinance / Discussion /
    # Presentation / Minutes ...) already map to the right kinds; only the attachment
    # that is the instrument itself needed a pattern.
    "miramar": {
        "jurisdiction": "Miramar",
        "county": "Broward County",
        "nightly": True,
        "label": "Miramar City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
        # "O1871 2nd Reading Millage" (the adopted reading, preferred), "TO1867 FIRST READING ...",
        # "R8832 Fire Station 84 ...", "TR8835 ...", "TR#8816 - ...".
        "text_attachment": [
            r"^\s*t?o\s?#?\d{3,}.*(2nd|second)\s+reading",
            r"^\s*t?[or]\s?#?\d{3,}",
        ],
    },
    "doral": {
        "jurisdiction": "Doral",
        "county": "Miami-Dade County",
        "nightly": True,
        # Sponsors mix council members and bodies ("Planning and Zoning").
        "body_sponsors_as_committees": True,
        "label": "Doral City Council (Legistar)",
        "note": "The most recent council matters. Matters without a PDF attachment have no full text.",
        # "Ord. No. 2026-26 Amendment to Micromobility Devices", "Res. No. 26-Special Event Permit ...".
        "text_attachment": [r"^\s*(res|ord)\.?\s*no\.?"],
    },
    "hallandalebeach": {
        "jurisdiction": "Hallandale Beach",
        "county": "Broward County",
        "nightly": True,
        "label": "Hallandale Beach City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
        # "Exhibit 1 - Ordinance" / "Exhibit 1 \u2013 Resolution" (hyphen or en dash).
        "text_attachment": [r"^\s*exhibit\s*1\s*[-\u2013\u2014]\s*(ordinance|resolution)\s*$"],
    },
    "coconutcreek": {
        "jurisdiction": "Coconut Creek",
        "county": "Broward County",
        "nightly": True,
        # Sponsors are partly departments ("City Clerk", "Resilient Design and Development").
        "body_sponsors_as_committees": True,
        "label": "Coconut Creek City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
        # "ORDINANCE 2026-045-Code Amdmt-... (2nd Reading)" and "RESOLUTION 2026-155-1-...", not "BACKUP-Resolution ...".
        "text_attachment": [r"^\s*(ordinance|resolution)\s+\d{4}-"],
    },
    "pinecrest": {
        "jurisdiction": "Pinecrest",
        "county": "Miami-Dade County",
        "nightly": True,
        "label": "Pinecrest Village Council (Legistar)",
        "note": "The most recent council matters. Matters without a PDF attachment have no full text.",
        # "TAB 7-Ordinance - First Reading - ...", "TAB 2-Consent - Resolution - Bid Award ...".
        "text_attachment": [r"^\s*tab\s*\d+\s*-\s*(consent\s*-\s*)?(resolutions?|ordinance)\b"],
    },
    "fortlauderdale": {
        "jurisdiction": "Fort Lauderdale",
        "county": "Broward County",
        "nightly": True,
        # Every sampled sponsor (25 of 25, 2026-10-13) is a meeting body such as
        # "City Commission Regular Meeting", never a person: store them as
        # committees so they stay out of the legislator lists.
        "body_sponsors_as_committees": True,
        # Attachment names that are the legislation itself, best first: the
        # adopted instrument ("ORDINANCE NO. C-26-40", "RESOLUTION NO. 26-84"),
        # then the proposed form ("Exhibit 4 - Resolution"). Not the
        # "Commission Agenda Memo", which is staff commentary.
        "text_attachment": [
            r"^\s*(ordinance|resolution)\s+no\.",
            r"^\s*exhibit\s*\d+\s*[-\u2013\u2014]\s*(ordinance|resolution)\s*$",
        ],
        "label": "Fort Lauderdale City Commission (Legistar)",
        "note": "The most recent commission matters. Matters without a PDF attachment have no full text.",
    },
}


# "MOTION TO ENACT Ordinance, ...", "MOTION TO ADOPT Resolution ...": the motion
# itself adopts the instrument. "MOTION TO DIRECT ... to draft an Ordinance" only
# asks for one to be written, so the verb is part of the rule.
_ADOPTS_LEGISLATION = re.compile(
    r"^\W*(?:a\.?\s+)?motion to (?:adopt|enact|approve|pass|amend)\b[^.\n]{0,60}?\b(ordinance|resolution)\b",
    re.IGNORECASE,
)


def derived_item_type(title: str) -> str:
    """Kind of record for a client whose own types are agenda categories.

    Broward's types are "Consent Item" / "Regular Item" and its titles are
    nearly all "MOTION TO ...". A motion that adopts a resolution or enacts an
    ordinance says so right after the verb, so those read as legislation;
    every other motion (including a direction to draft one) stays a motion.
    A heuristic, checked against Broward's 300 newest titles on 2026-10-13
    (82 legislation, none missed against a looser rule).
    """
    match = _ADOPTS_LEGISLATION.search(" ".join((title or "").split()))
    if match:
        return "Ordinance" if match.group(1).lower() == "ordinance" else "Resolution"
    return "Motion"


# "Adopt Ordinance 9931-26 on second reading", "... and adopt Resolution 26-02".
_ADOPTS_INSTRUMENT = re.compile(r"\badopt(?:ing)?\s+(?:the\s+)?(?:[\w-]+\s+){0,3}?(ordinance|resolution)\b", re.IGNORECASE)

# Titles that stand in for a title: the clerk's template text, never a real name.
_PLACEHOLDER_TITLE = re.compile(r"^\W*(?:enter\s+(?:title|text)(?:\s+here)?|title\s+to\s+come|tbd|n/?a)\W*$", re.IGNORECASE)


def adopted_instrument(title: str) -> str | None:
    """"Ordinance" or "Resolution" when an agenda action's title says it adopts
    one, else None. For clients (Clearwater) that type most items "Action Item"."""
    match = _ADOPTS_INSTRUMENT.search(" ".join((title or "").split()))
    return match.group(1).capitalize() if match else None


def is_placeholder_title(text: str | None) -> bool:
    return bool(text) and bool(_PLACEHOLDER_TITLE.match(" ".join(text.split())))


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
    # Legistar titles carry HTML entities ("G&amp;B Oyster Bar"); the site
    # escapes text itself, so an undecoded entity would show literally.
    candidates = [t for t in (matter.get("MatterName"), matter.get("MatterTitle")) if t and not is_placeholder_title(t)]
    full_title = html.unescape(candidates[0] if candidates else f"Matter {matter['MatterId']}")
    return full_title if len(full_title) <= 490 else full_title[:489] + "…"


def _bill_number(matter: dict) -> str:
    """The clerk's file number. Hollywood's planning-board items carry
    "MatterFile": null (a present-but-null key, so dict.get's default does not
    apply), which violated bills.bill_number NOT NULL on the 2026-10-16 seed run."""
    return matter.get("MatterFile") or str(matter["MatterId"])


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


def _get_or_create_person(
    db: Session, *, name: str, client_name: str, jurisdiction: str, committee: bool = False
) -> Entity:
    existing = db.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.name == name,
            Entity.jurisdiction_name == jurisdiction,
        )
    ).scalars().first()
    if existing:
        if committee and not (existing.attributes or {}).get("committee"):
            existing.attributes = {**(existing.attributes or {}), "committee": True}
        return existing

    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level=client_level(client_name),
        jurisdiction_name=jurisdiction,
        external_ids={"legistar_client": client_name},
        attributes={"committee": True} if committee else {},
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
        if all(is_placeholder_title(t) for t in (matter.get("MatterName"), matter.get("MatterTitle")) if t) and (
            matter.get("MatterName") or matter.get("MatterTitle")
        ):
            logger.info("Skipping Legistar matter %s (%s): placeholder title", matter_id, client_name)
            continue
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
        if info.get("item_type_from_title"):
            # source_item_type marks the type as derived, so item_kind --backfill
            # (which copies the source's own type) leaves it alone.
            entity.attributes = {
                **(entity.attributes or {}),
                "item_type": derived_item_type(title),
                "source_item_type": matter.get("MatterTypeName"),
            }
        elif matter.get("MatterTypeName") in info.get("adopted_instrument_from_title", ()) and adopted_instrument(title):
            # Only the items whose title adopts an instrument; the rest keep the
            # source's own type ("Action Item") like every other client.
            entity.attributes = {
                **(entity.attributes or {}),
                "item_type": adopted_instrument(title),
                "source_item_type": matter["MatterTypeName"],
            }
        elif matter.get("MatterTypeName"):
            entity.attributes = {**(entity.attributes or {}), "item_type": matter["MatterTypeName"]}  # see item_kind.py
        db.flush()

        source = Source(
            url=detail_url,
            document_reference=_bill_number(matter),
            publisher=info.get("publisher") or f"{jurisdiction} City Clerk (Legistar)",
            source_type="legistar_agenda",
            retrieved_at=now,
            metadata_json={"matter_id": matter_id, "matter_type": matter.get("MatterTypeName")},
        )
        db.add(source)
        db.flush()

        bill = entity.bill
        if bill is None:
            bill = Bill(entity_id=entity.id, bill_number=_bill_number(matter), session="")
            db.add(bill)

        bill.bill_number = _bill_number(matter)
        bill.session = _bill_session(matter)
        bill.chamber = fit(matter.get("MatterBodyName"), CHAMBER_MAX_LENGTH)
        bill.status = normalize_status(matter.get("MatterStatusName")) or "Introduced"
        bill.introduced_date = _parse_date(matter.get("MatterIntroDate"))
        bill.last_action_date = _parse_date(matter.get("MatterPassedDate")) or bill.introduced_date
        bill.last_action = matter.get("MatterStatusName")
        bill.full_text_url = detail_url
        bill.source_system = "legistar"
        bill.description = html.unescape(matter["MatterTitle"]) if matter.get("MatterTitle") else None
        bill.geo_scope_type = client_level(client_name)
        bill.geo_scope_names = [info["county"]]
        db.flush()

        try:
            for sponsor in client.get_sponsors(matter_id):
                name = sponsor.get("MatterSponsorName")
                if not name:
                    continue
                is_body = bool(sponsor.get("MatterSponsorBodyId")) and not sponsor.get("MatterSponsorNameId")
                person = _get_or_create_person(
                    db,
                    name=name,
                    client_name=client_name,
                    jurisdiction=jurisdiction,
                    committee=is_body and bool(info.get("body_sponsors_as_committees")),
                )
                exists = db.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == person.id,
                        Relationship.to_entity_id == entity.id,
                        Relationship.relationship_type == "sponsor",
                    )
                ).scalars().first()  # not scalar_one_or_none: a duplicated row once stopped Key West nightly (2026-10-14)
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
