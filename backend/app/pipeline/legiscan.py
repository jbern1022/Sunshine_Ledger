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
from app.models import Bill, Entity, Event, Relationship, Source
from app.pipeline._status import normalize_status

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

    def get_sessions(self, state: str) -> list[dict]:
        """All known sessions for a state, newest first."""
        return self._call("getSessionList", state=state)["sessions"]

    def get_session_people(self, session_id: int) -> list[dict]:
        """Every legislator in a session, with district/role/party -- one API
        call for the whole chamber, rather than one getBill per bill."""
        return self._call("getSessionPeople", id=str(session_id))["sessionpeople"]["people"]

    def get_roll_call(self, roll_call_id: int) -> dict:
        """Per-legislator votes for one roll call. Confirmed live 2026-09-03:
        each entry is {people_id, vote_id, vote_text} -- no name, so callers
        must resolve people_id against a session people roster
        (get_session_people) to get a displayable name."""
        return self._call("getRollCall", id=str(roll_call_id))["roll_call"]


def _person_attributes(*, district: str | None, role: str | None, party: str | None) -> dict:
    """Only the fields LegiScan actually populates -- omitting empties keeps
    `attributes` free of null-valued keys that would otherwise have to be
    special-cased downstream."""
    return {k: v for k, v in (("district", district), ("role", role), ("party", party)) if v}


def _get_or_create_person(
    db: Session,
    *,
    name: str,
    external_id: str,
    district: str | None = None,
    role: str | None = None,
    party: str | None = None,
) -> Entity:
    """Upsert a legislator. `district` (e.g. "HD-120"/"SD-024") is what the
    district sponsorship map joins on -- see app/api/map.py. Attributes are
    refreshed on existing rows too, so people ingested before districts were
    tracked get backfilled on the next run that touches their bill.
    """
    attributes = _person_attributes(district=district, role=role, party=party)

    existing = db.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.external_ids["legiscan_people_id"].as_string() == external_id,
        )
    ).scalar_one_or_none()
    if existing:
        if attributes:
            existing.attributes = {**(existing.attributes or {}), **attributes}
        return existing

    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="state",
        jurisdiction_name=settings.legiscan_state,
        external_ids={"legiscan_people_id": external_id},
        attributes=attributes,
    )
    db.add(person)
    db.flush()
    return person


def _build_people_by_id(client: LegiScanClient, state: str, *, sessions: int = 2) -> dict[str, dict]:
    """people_id -> {name, district, role, party} for the state's most recent
    sessions. Shared by backfill_person_districts and vote syncing -- both
    need to resolve a bare people_id to a displayable legislator, and one
    getSessionPeople call per session covers the whole chamber rather than
    one call per person."""
    people: dict[str, dict] = {}
    for session in client.get_sessions(state)[:sessions]:
        for person in client.get_session_people(int(session["session_id"])):
            people.setdefault(str(person.get("people_id")), person)
    return people


def _sync_bill_votes(
    db: Session,
    *,
    bill_entity: Entity,
    votes: list[dict],
    client: LegiScanClient,
    state: str,
    people_by_id: dict[str, dict],
    fetch_individual: bool,
) -> int:
    """Store LegiScan's roll-call summaries (already present in every getBill
    response) as `vote` Events, and -- if fetch_individual -- each
    legislator's Yea/Nay/NV/Absent as a `voted` Relationship.

    Idempotent per roll_call_id: a roll call already recorded is skipped
    entirely (including its individual votes), so re-running this against
    the same bill costs nothing extra in API quota. Returns the number of
    NEW getRollCall calls actually made, so callers can log real quota use.

    Deliberately plain facts only -- yea/nay counts and who voted which way,
    no scoring or "consistency" framing. That kind of comparison is Phase
    3/4 roadmap work gated behind the legal review already required for the
    rhetoric-vs-substance work; this only extends the same sourced-fact
    pattern the rest of the pipeline already follows.
    """
    roll_calls_fetched = 0

    for v in votes:
        roll_call_id = v.get("roll_call_id")
        if roll_call_id is None:
            continue
        roll_call_id = str(roll_call_id)

        vote_date = _parse_date(v.get("date"))
        if vote_date is None:
            logger.warning(
                "Skipping roll call %s on bill %s: no parseable date", roll_call_id, bill_entity.id
            )
            continue

        existing = db.execute(
            select(Event).where(
                Event.entity_id == bill_entity.id,
                Event.event_type == "vote",
                Event.attributes["roll_call_id"].as_string() == roll_call_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        vote_source = Source(
            url=v.get("url") or v.get("state_link") or "",
            publisher=f"{state} Legislature via LegiScan",
            source_type="legiscan_roll_call",
            retrieved_at=datetime.now(timezone.utc),
            metadata_json={"roll_call_id": roll_call_id},
        )
        db.add(vote_source)
        db.flush()

        db.add(
            Event(
                entity_id=bill_entity.id,
                event_type="vote",
                event_date=vote_date,
                title=v.get("desc") or "Roll call vote",
                attributes={
                    "roll_call_id": roll_call_id,
                    "chamber": v.get("chamber"),
                    "yea": v.get("yea"),
                    "nay": v.get("nay"),
                    "nv": v.get("nv"),
                    "absent": v.get("absent"),
                    "total": v.get("total"),
                    "passed": bool(v.get("passed")),
                },
                source_id=vote_source.id,
            )
        )

        if not fetch_individual:
            continue

        roll_call_detail = client.get_roll_call(int(roll_call_id))
        roll_calls_fetched += 1

        for vote_row in roll_call_detail.get("votes", []):
            people_id = str(vote_row.get("people_id"))
            person_info = people_by_id.get(people_id)
            if person_info is None:
                # Not in the fetched session roster (e.g. a since-departed
                # legislator from an older session) -- skip rather than
                # record a vote under a name we can't verify.
                continue

            person = _get_or_create_person(
                db,
                name=person_info.get("name", "Unknown"),
                external_id=people_id,
                district=person_info.get("district"),
                role=person_info.get("role"),
                party=person_info.get("party"),
            )
            db.add(
                Relationship(
                    from_entity_id=person.id,
                    to_entity_id=bill_entity.id,
                    relationship_type="voted",
                    attributes={"roll_call_id": roll_call_id, "vote": vote_row.get("vote_text")},
                    source_id=vote_source.id,
                )
            )

    return roll_calls_fetched


def _get_or_create_bill_entity(db: Session, *, legiscan_bill_id: int) -> Entity | None:
    return db.execute(
        select(Entity).where(
            Entity.entity_type == "bill",
            Entity.external_ids["legiscan_id"].as_string() == str(legiscan_bill_id),
        )
    ).scalar_one_or_none()


def ingest_state_bills(
    db: Session, *, state: str | None = None, limit: int | None = None, sync_votes: bool = True
) -> list[Entity]:
    """Pull the master bill list for `state` and upsert each bill + sponsors + source.

    `sync_votes` also stores any roll-call vote data already present in the
    same getBill response as `vote` Events + per-legislator `voted`
    Relationships -- no extra API cost for the chamber-level tallies, one
    getRollCall call per *new* roll call for the individual breakdown. Only
    covers bills this run actually fetches fresh detail for (i.e. new or
    changed bills); see sync_state_votes for backfilling the rest of an
    already-ingested corpus.

    Returns the list of bill Entities written (new or refreshed).
    """
    state = state or settings.legiscan_state
    client = LegiScanClient()

    master_list = client.get_master_list(state)
    if limit:
        master_list = master_list[:limit]

    written: list[Entity] = []
    now = datetime.now(timezone.utc)
    people_by_id: dict[str, dict] | None = None  # built lazily, at most once
    roll_calls_fetched = 0

    for row in master_list:
        legiscan_bill_id = int(row["bill_id"])
        row_change_hash = row.get("change_hash")

        entity = _get_or_create_bill_entity(db, legiscan_bill_id=legiscan_bill_id)
        if (
            entity is not None
            and row_change_hash
            and entity.external_ids.get("legiscan_change_hash") == row_change_hash
        ):
            # Unchanged since our last pull -- skip the getBill call entirely.
            # Matters for a daily scheduled run: LegiScan's free tier is
            # 30,000 queries/month, and re-fetching detail for ~1,900
            # already-stable bills every day would blow through that in
            # under a week.
            continue

        detail = client.get_bill(legiscan_bill_id)

        if entity is None:
            entity = Entity(entity_type="bill", name=detail.get("title", row.get("title", "")), external_ids={})
            db.add(entity)

        entity.name = detail.get("title") or row.get("title", "")
        entity.jurisdiction_level = "state"
        entity.jurisdiction_name = state
        entity.external_ids = {
            **entity.external_ids,
            "legiscan_id": str(legiscan_bill_id),
            "legiscan_change_hash": row_change_hash,
        }
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
        # Falling back to the master list's `status` leaks LegiScan's raw
        # numeric code into a user-facing field -- that is how a bill came to
        # display a status of "0". Only accept the fallback if it isn't a bare
        # number.
        fallback = str(row.get("status", "") or "").strip()
        if not fallback or fallback.isdigit():
            fallback = "Unknown"
        bill.status = normalize_status(STATUS_MAP.get(status_code, fallback))
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
                db,
                name=sponsor.get("name", "Unknown"),
                external_id=str(sponsor.get("people_id")),
                district=sponsor.get("district"),
                role=sponsor.get("role"),
                party=sponsor.get("party"),
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

        votes = detail.get("votes") or []
        if sync_votes and votes:
            if people_by_id is None:
                people_by_id = _build_people_by_id(client, state)
            roll_calls_fetched += _sync_bill_votes(
                db,
                bill_entity=entity,
                votes=votes,
                client=client,
                state=state,
                people_by_id=people_by_id,
                fetch_individual=True,
            )

        written.append(entity)

    db.commit()
    logger.info(
        "Ingested %d bills from LegiScan for state=%s (%d new roll calls fetched)",
        len(written),
        state,
        roll_calls_fetched,
    )
    return written


def backfill_person_districts(db: Session, *, state: str | None = None, sessions: int = 2) -> int:
    """Attach district/role/party to already-stored legislators.

    `ingest_state_bills` records these going forward, but it skips bills whose
    `change_hash` is unchanged (to stay inside the API quota), so legislators
    ingested before districts were tracked would never be updated by a normal
    run. This backfills them via `getSessionPeople` -- one API call per
    session rather than one per bill.

    Returns the number of people actually updated.
    """
    state = state or settings.legiscan_state
    client = LegiScanClient()
    people = _build_people_by_id(client, state, sessions=sessions)

    updated = 0
    for people_id, person in people.items():
        attributes = _person_attributes(
            district=person.get("district"), role=person.get("role"), party=person.get("party")
        )
        if not attributes:
            continue

        entity = db.execute(
            select(Entity).where(
                Entity.entity_type == "person",
                Entity.external_ids["legiscan_people_id"].as_string() == people_id,
            )
        ).scalar_one_or_none()
        if entity is None:
            continue  # legislator we've never seen sponsor a tracked bill

        merged = {**(entity.attributes or {}), **attributes}
        if merged != entity.attributes:
            entity.attributes = merged
            updated += 1

    db.commit()
    logger.info("Backfilled district/role/party for %d legislators (state=%s)", updated, state)
    return updated


def sync_state_votes(
    db: Session, *, state: str | None = None, limit: int | None = None, fetch_individual: bool = True
) -> tuple[int, int]:
    """Backfill vote data for bills already in the DB that `ingest_state_bills`
    will never revisit, because their change_hash already matches (that skip
    exists specifically to protect the API quota, so this is a deliberate,
    explicit, one-time-per-bill re-fetch rather than something folded into
    the nightly job).

    Costs one getBill call per already-ingested bill (to see its current
    votes array) plus one getRollCall call per roll call not already
    recorded -- idempotent, so a partial or repeated run only pays for what
    it hasn't already fetched. Pass `limit` to test on a small batch before
    running the full corpus; at ~2,300 bills this is a meaningful chunk of
    the 30,000/month free-tier quota and worth running as one deliberate
    pass, not a repeated habit.

    Returns (bills_processed, roll_calls_fetched).
    """
    state = state or settings.legiscan_state
    client = LegiScanClient()
    people_by_id = _build_people_by_id(client, state) if fetch_individual else {}

    stmt = select(Entity).where(
        Entity.entity_type == "bill", Entity.external_ids.has_key("legiscan_id")
    )
    if limit:
        stmt = stmt.limit(limit)
    bill_entities = db.execute(stmt).scalars().all()

    bills_processed = 0
    roll_calls_fetched = 0

    for entity in bill_entities:
        legiscan_bill_id = int(entity.external_ids["legiscan_id"])
        detail = client.get_bill(legiscan_bill_id)
        bills_processed += 1

        votes = detail.get("votes") or []
        if not votes:
            continue

        roll_calls_fetched += _sync_bill_votes(
            db,
            bill_entity=entity,
            votes=votes,
            client=client,
            state=state,
            people_by_id=people_by_id,
            fetch_individual=fetch_individual,
        )
        db.commit()

    logger.info(
        "Vote backfill: checked %d bills, fetched %d new roll calls (state=%s)",
        bills_processed,
        roll_calls_fetched,
        state,
    )
    return bills_processed, roll_calls_fetched


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
