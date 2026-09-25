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
from collections import Counter
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_setup import quiet_http_logging
from app.models import Bill, Entity, Event, Relationship, Source
from app.pipeline._retry import with_retry
from app.pipeline._status import normalize_status
from app.pipeline.topic_tagging import assign_tags_for_bill

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


# LegiScan calls made by this process, by operation, counting retries.
# HTTP request logging is silenced (it would print the API key), so this is
# the only record of what a run cost against the monthly quota (10,000
# calls from 2026-10-01).
API_CALLS: Counter[str] = Counter()


def api_usage_summary() -> str:
    total = sum(API_CALLS.values())
    detail = ", ".join(f"{op} {n}" for op, n in sorted(API_CALLS.items()))
    return f"LegiScan API calls this run: {total}" + (f" ({detail})" if detail else "")


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
        def _do_request() -> dict:
            API_CALLS[op] += 1
            resp = self._client.get("", params={"key": self.api_key, "op": op, **params})
            resp.raise_for_status()
            return resp.json()

        data = with_retry(_do_request, description=f"LegiScan op={op}")
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

    def get_amendment(self, amendment_id: int) -> dict:
        """Full amendment document (base64 doc + mime), per LegiScan's
        documented getAmendment op -- same shape family as getBillText.
        Unlike get_roll_call, this has not been hand-verified against a
        live call in this codebase; treat the exact field set as documented,
        not confirmed, until a real amendment_id has been run through it."""
        return self._call("getAmendment", id=str(amendment_id))["amendment"]

    def get_supplement(self, supplement_id: int) -> dict:
        """Full supplement document (base64 doc + mime) -- same shape family
        as getBillText/getAmendment. Used for staff bill analyses (see
        pipeline/staff_analysis.py): a supplement's own `state_link` 404s
        into a soft-404 HTML page for older/rotated links rather than
        serving the PDF directly (confirmed 2026-09-21), so the document is
        always fetched through this op instead of that URL."""
        return self._call("getSupplement", id=str(supplement_id))["supplement"]


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


def introduced_date(detail: dict) -> date | None:
    """When a bill was filed. getBill has no `introduced` field for FL bills
    (all 1,897 stored bills had no introduced date as of 2026-09-25), so fall
    back to the earliest entry in its action history, which is "Filed" for
    98% of them.
    """
    explicit = _parse_date(detail.get("introduced"))
    if explicit:
        return explicit
    dates = [d for d in (_parse_date(h.get("date")) for h in detail.get("history") or []) if d]
    return min(dates) if dates else None


ACTION_CHAMBERS = {"H": "House", "S": "Senate"}


def sync_bill_actions(db: Session, *, bill_entity: Entity, history: list[dict]) -> int:
    """Store LegiScan's action history (getBill `history`) as `action` Events.

    The raw material for a "how it became law" timeline: filed, referred,
    reported by committee, passed, signed, chaptered. Shape verified
    2026-09-25 against HB 1389 (55 entries): {date, action, chamber ("H",
    "S", or "" for governor/chapter steps), chamber_id, importance (0/1)}.

    Append-only and idempotent. An entry is identified by (date, chamber,
    action) plus how many times that same triple occurred before it, so a
    bill that is really referred to the same committee twice keeps both,
    and re-running against an unchanged history writes nothing. `seq`
    keeps LegiScan's order among same-day entries.

    Returns the number of new events written.
    """
    seen: dict[tuple, int] = {}
    for e in db.execute(
        select(Event).where(Event.entity_id == bill_entity.id, Event.event_type == "action")
    ).scalars():
        key = (e.event_date.isoformat(), e.attributes.get("chamber"), e.title)
        seen[key] = seen.get(key, 0) + 1

    written = 0
    occurrences: dict[tuple, int] = {}
    for seq, entry in enumerate(history):
        action_date = _parse_date(entry.get("date"))
        action = (entry.get("action") or "").strip()
        if action_date is None or not action:
            continue
        chamber = ACTION_CHAMBERS.get(entry.get("chamber") or "")
        title = action[:500]
        key = (action_date.isoformat(), chamber, title)
        occurrences[key] = occurrences.get(key, 0) + 1
        if occurrences[key] <= seen.get(key, 0):
            continue
        db.add(
            Event(
                entity_id=bill_entity.id,
                event_type="action",
                event_date=action_date,
                title=title,
                attributes={
                    "chamber": chamber,
                    "importance": bool(entry.get("importance")),
                    "seq": seq,
                },
            )
        )
        written += 1

    if written:
        db.flush()
    return written


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


def _extract_subjects(detail: dict) -> list[str]:
    """Raw FL Subject Index strings from a getBill response.

    Shape verified by hand 2026-09-16 against live getBill responses (63
    bills across FL, CA, NY): `subjects` is present as documented --
    {"subject_id": int, "subject_name": str} -- but was empty on every bill
    tested, in every state tested, on this API key's tier. This is a data
    availability limit, not a parsing bug: LegiScan simply isn't returning
    subject data here, so tag coverage from this source will be zero until
    that's resolved (see the LegiScan getBill verification ticket). Still
    defensive against the field being absent or shaped unexpectedly so a
    wrong guess degrades to "no tags assigned" rather than breaking
    ingestion.
    """
    subjects = detail.get("subjects")
    if not isinstance(subjects, list):
        return []
    names = []
    for s in subjects:
        if isinstance(s, dict) and s.get("subject_name"):
            names.append(s["subject_name"])
    return names


def _get_or_create_bill_entity(db: Session, *, legiscan_bill_id: int) -> Entity | None:
    return db.execute(
        select(Entity).where(
            Entity.entity_type == "bill",
            Entity.external_ids["legiscan_id"].as_string() == str(legiscan_bill_id),
        )
    ).scalar_one_or_none()


def ingest_state_bills(
    db: Session,
    *,
    state: str | None = None,
    limit: int | None = None,
    sync_votes: bool = True,
    client: LegiScanClient | None = None,
    master_list: list[dict] | None = None,
) -> list[Entity]:
    """Pull the master bill list for `state` and upsert each bill + sponsors + source.

    `sync_votes` also stores any roll-call vote data already present in the
    same getBill response as `vote` Events + per-legislator `voted`
    Relationships -- no extra API cost for the chamber-level tallies, one
    getRollCall call per *new* roll call for the individual breakdown. Only
    covers bills this run actually fetches fresh detail for (i.e. new or
    changed bills); see sync_state_bill_history for backfilling the rest of an
    already-ingested corpus.

    `client` and `master_list` let a caller substitute another source for
    the API's current-session master list -- ingest_session_dataset feeds
    a whole session from its LegiScan dataset this way.

    Returns the list of bill Entities written (new or refreshed).
    """
    state = state or settings.legiscan_state
    client = client or LegiScanClient()

    if master_list is None:
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
        if sync_votes:
            # This pass syncs amendments, history and votes from `detail`,
            # so sync_state_bill_history has nothing left to fetch for it.
            entity.external_ids = {**entity.external_ids, "legiscan_history_hash": row_change_hash}
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
        bill.introduced_date = introduced_date(detail)
        bill.last_action_date = _parse_date(detail.get("status_date") or row.get("last_action_date"))
        bill.last_action = detail.get("last_action") or row.get("last_action")
        bill.full_text_url = detail.get("state_link") or row.get("url")
        bill.source_system = "legiscan"
        bill.description = detail.get("description")
        bill.geo_scope_type = "statewide"
        bill.geo_scope_names = [state]
        db.flush()

        # Timeline entries only -- no extra API cost since `amendments` is
        # already present on this getBill response. Amendment *text* (for
        # a future diff view) is a separate opt-in backfill; see
        # pipeline/amendments.py. Imported lazily here (rather than at
        # module scope) because amendments.py imports bill_text.py, which
        # imports LegiScanClient from this module -- a top-level import
        # here would be a circular import.
        from app.pipeline.amendments import sync_bill_amendments

        sync_bill_amendments(db, bill_entity=entity, amendments=detail.get("amendments", []))
        sync_bill_actions(db, bill_entity=entity, history=detail.get("history") or [])

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

        subjects = _extract_subjects(detail)
        if not subjects:
            # LegiScan's subjects are empty for FL on this API tier, so
            # classify with the local model instead, as local bills are. It
            # falls back to "governance" if Ollama is unreachable.
            from app.pipeline.topic_tagging_ollama import STATE_KIND, tag_local_bill

            tag_local_bill(db, entity.id, title=entity.name, description=bill.description or "", kind=STATE_KIND)
        if subjects:
            try:
                assign_tags_for_bill(db, entity.id, raw_subjects=subjects)
            except RuntimeError:
                # Governance tag not seeded (run topic_tagging_seed) -- log
                # and keep going rather than failing the whole ingestion run
                # over a tagging problem. Bills/sponsors/votes above are
                # already committed-worthy on their own.
                logger.warning(
                    "Skipping topic tagging for bill %s: tag seed data missing "
                    "(run `python -m app.pipeline.topic_tagging_seed`)",
                    entity.id,
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


def ingest_session_dataset(db: Session, *, session_name: str, state: str | None = None) -> list[Entity]:
    """Ingest every bill of one past session from its LegiScan dataset.

    Nightly ingestion only sees the current session's master list, so
    sessions it never covered (e.g. the 2026 special sessions) come in this
    way: 2 API calls for the dataset, then the same ingest_state_bills path
    as nightly bills (sponsors, tags, amendments, history, roll calls with
    individual votes), all answered from the dataset. Bill text is separate:
    run bill_text afterwards (2 calls per new bill).
    """
    from app.pipeline.legiscan_dataset import DatasetClient, fetch_session_dataset

    state = state or settings.legiscan_state
    api = LegiScanClient()
    client = DatasetClient(fetch_session_dataset(api, state, session_name), fallback=api)
    master_list = [
        {"bill_id": bill_id, "change_hash": bill.get("change_hash"), "number": bill.get("bill_number"),
         "title": bill.get("title"), "url": bill.get("state_link") or bill.get("url") or "",
         "status": bill.get("status")}
        for bill_id, bill in sorted(client.bills.items())
    ]
    written = ingest_state_bills(db, state=state, client=client, master_list=master_list)
    logger.info(
        "%s: %d bills in dataset, %d written, %d API calls beyond the dataset",
        session_name, len(master_list), len(written), client.fallback_calls,
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


def sync_state_bill_history(
    db: Session,
    *,
    state: str | None = None,
    limit: int | None = None,
    fetch_individual: bool = True,
    client: LegiScanClient | None = None,
) -> tuple[int, int]:
    """Backfill amendments, action history and roll-call votes for bills
    already in the DB that `ingest_state_bills` will never revisit, because their change_hash
    already matches (that skip exists specifically to protect the API quota,
    so this is a deliberate, explicit, one-time-per-bill re-fetch rather than
    something folded into the nightly job).

    Costs one getBill call per bill (its response carries the amendments,
    history, votes and supplements arrays) plus one getRollCall call per
    roll call and one getSupplement call per staff analysis not already
    stored. Each bill is marked with the change_hash it was
    synced at (`legiscan_history_hash`), so an interrupted or repeated run
    skips bills already done instead of paying for them again. Pass `limit`
    to test on a small batch first: at ~1,900 bills this is a meaningful
    share of the monthly LegiScan quota.

    Returns (bills_processed, roll_calls_fetched).
    """
    # Imported here: both modules import this one (see ingest_state_bills).
    from app.models import StaffAnalysis
    from app.pipeline.amendments import sync_bill_amendments
    from app.pipeline.staff_analysis import store_new_staff_analyses

    state = state or settings.legiscan_state
    client = client or LegiScanClient()

    stmt = select(Entity).where(
        Entity.entity_type == "bill", Entity.external_ids.has_key("legiscan_id")
    )
    bill_entities = [
        e
        for e in db.execute(stmt).scalars().all()
        if not e.external_ids.get("legiscan_history_hash")
        or e.external_ids.get("legiscan_history_hash") != e.external_ids.get("legiscan_change_hash")
    ]
    if limit:
        bill_entities = bill_entities[:limit]
    people_by_id = _build_people_by_id(client, state) if fetch_individual and bill_entities else {}

    known_analysis_ids = {row[0] for row in db.execute(select(StaffAnalysis.legiscan_supplement_id))}

    bills_processed = 0
    roll_calls_fetched = 0
    analyses_fetched = 0

    for entity in bill_entities:
        legiscan_bill_id = int(entity.external_ids["legiscan_id"])
        detail = client.get_bill(legiscan_bill_id)
        bills_processed += 1

        sync_bill_amendments(db, bill_entity=entity, amendments=detail.get("amendments") or [])
        sync_bill_actions(db, bill_entity=entity, history=detail.get("history") or [])
        if entity.bill is not None and entity.bill.introduced_date is None:
            entity.bill.introduced_date = introduced_date(detail)
        votes = detail.get("votes") or []
        if votes:
            roll_calls_fetched += _sync_bill_votes(
                db,
                bill_entity=entity,
                votes=votes,
                client=client,
                state=state,
                people_by_id=people_by_id,
                fetch_individual=fetch_individual,
            )
        entity.external_ids = {
            **entity.external_ids,
            "legiscan_history_hash": entity.external_ids.get("legiscan_change_hash"),
        }
        db.commit()
        # After the commit: this helper commits or rolls back on its own.
        analyses_fetched += store_new_staff_analyses(
            db, client, entity=entity, supplements=detail.get("supplements") or [],
            known_ids=known_analysis_ids,
        )[0]

    logger.info(
        "Bill history backfill: checked %d bills, fetched %d new roll calls and %d new staff analyses (state=%s)",
        bills_processed,
        roll_calls_fetched,
        analyses_fetched,
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


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description="LegiScan backfills.")
    parser.add_argument(
        "--sync-history",
        action="store_true",
        help="Backfill amendments and roll-call votes for already-ingested bills (costs API quota).",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--from-dataset",
        metavar="SESSION_NAME",
        help=(
            'With --sync-history: read bills and roll calls from that session\'s LegiScan '
            'dataset (e.g. "2026 Regular Session"; 2 API calls) instead of one call per bill.'
        ),
    )
    parser.add_argument(
        "--ingest-dataset",
        metavar="SESSION_NAME",
        action="append",
        help='Ingest every bill of a past session from its LegiScan dataset (repeatable), '
             'e.g. "2026 Fourth Special Session". 2 API calls per session.',
    )
    args = parser.parse_args()
    if args.ingest_dataset:
        session = SessionLocal()
        try:
            for name in args.ingest_dataset:
                written = ingest_session_dataset(session, session_name=name)
                print(f"{name}: {len(written)} bills written.")
        finally:
            session.close()
            print(api_usage_summary())
        raise SystemExit(0)
    if not args.sync_history:
        parser.error("nothing to do: pass --sync-history or --ingest-dataset")
    session = SessionLocal()
    try:
        client = None
        if args.from_dataset:
            from app.pipeline.legiscan_dataset import DatasetClient, fetch_session_dataset

            api = LegiScanClient()
            client = DatasetClient(
                fetch_session_dataset(api, settings.legiscan_state, args.from_dataset), fallback=api
            )
            print(f"Dataset: {len(client.bills)} bills, {len(client.roll_calls)} roll calls, "
                  f"{len(client.people)} legislators.")
        bills, roll_calls = sync_state_bill_history(session, limit=args.limit, client=client)
        print(f"Done: {bills} bills checked, {roll_calls} new roll calls stored.")
        if client is not None:
            print(f"API calls beyond the dataset download: {client.fallback_calls}.")
    finally:
        session.close()
        print(api_usage_summary())
