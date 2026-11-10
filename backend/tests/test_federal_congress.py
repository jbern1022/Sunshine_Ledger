import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.federal.bills import coarse_status, congress_url, parse_legis_num, upsert_bill
from app.federal.congress_api import CongressApiError, CongressClient
from app.federal.policy import is_eligible
from app.federal.roster import import_roster
from app.federal.rollcalls import parse_house, parse_senate, store_roll_call, sync_chamber, _members_by_id
from app.federal.sponsorships import sync_delegation, sync_member
from app.models import Bill, Entity, Event, Relationship
from app.pipeline.summarize_batch import select_bills_needing_summary

FX = Path(__file__).parent / "fixtures"
ROSTER = json.loads((FX / "congress_legislators_sample.json").read_text())


@pytest.fixture()
def delegation(db_session):
    import_roster(db_session, ROSTER, today=date(2026, 11, 10))
    return {p.external_ids["bioguide_id"]: p for p in db_session.execute(select(Entity).where(Entity.entity_type == "person")).scalars()}


# --- identifiers and status --------------------------------------------------

def test_legis_num_spellings_and_non_bills():
    assert parse_legis_num("H CON RES 14") == ("hconres", 14)
    assert parse_legis_num("H R 1234") == ("hr", 1234)
    assert parse_legis_num("S. 9") == ("s", 9)
    assert parse_legis_num("S.J.Res. 5") == ("sjres", 5)
    assert parse_legis_num("QUORUM") is None
    assert parse_legis_num(None) is None
    assert parse_legis_num("PN 12") is None  # a nomination


def test_congress_urls_and_status():
    assert congress_url(119, "hr", 10840) == "https://www.congress.gov/bill/119th-congress/house-bill/10840"
    assert coarse_status("Referred to the House Committee on Veterans' Affairs.") == "Introduced"
    assert coarse_status("Became Public Law No: 119-4.") == "Became Law"
    assert coarse_status("Passed/agreed to in House: On passage") == "Passed House"
    assert coarse_status("Committee Consideration and Mark-up Session Held") == "In Progress"


# --- sponsorships --------------------------------------------------------------

SPONSORED = json.loads((FX / "congress_member_sponsored.json").read_text())["sponsoredLegislation"]


class FakeCongress:
    def __init__(self, sponsored, cosponsored):
        self.data = {"sponsoredLegislation": sponsored, "cosponsoredLegislation": cosponsored}
        self.requests = 0

    def paged(self, path, key, **params):
        self.requests += 1
        assert path.startswith("/member/B001257/") or path.startswith("/member/R000595/")
        yield from self.data[key]


def test_sponsored_and_cosponsored_bills_are_linked_and_marked(db_session, delegation):
    other = dict(SPONSORED[0], number="55", type="HR", title="A cosponsored bill", congress=119)
    old = dict(SPONSORED[1], congress=118)
    amend = dict(SPONSORED[1], type="HAMDT", number="9")
    client = FakeCongress(SPONSORED + [old, amend], [other])
    gus = delegation["B001257"]
    out = sync_member(db_session, client, gus)
    assert out["bills"] == 4 and out["skipped"] == 2  # 3 sponsored + 1 cosponsored; an older Congress and an amendment skipped
    rels = db_session.execute(select(Relationship).where(Relationship.from_entity_id == gus.id)).scalars().all()
    assert sorted(r.relationship_type for r in rels) == ["co_sponsor", "sponsor", "sponsor", "sponsor"]
    bill = db_session.execute(select(Entity).where(Entity.external_ids["congress_bill"].as_string() == "119-hr-10840")).scalar_one()
    assert bill.attributes["delegation_sponsored"] is True and bill.attributes["policy_area"]
    assert bill.bill.source_system == "congress" and bill.bill.status == "Introduced"
    assert bill.bill.description == bill.name  # input for the summarizer: delegation bills only
    assert sync_member(db_session, client, gus)["links"] == 0  # idempotent


def test_delegation_sync_covers_every_member_with_a_bioguide_id(db_session, delegation):
    class Both(FakeCongress):
        def paged(self, path, key, **params):
            yield from self.data[key] if "B001257" in path else []

    out = sync_delegation(db_session, Both(SPONSORED, []))
    assert out["members"] == 2 and out["links"] == 3


# --- the generation policy ---------------------------------------------------------

def test_only_delegation_bills_are_eligible_for_summaries(db_session, delegation):
    mine = upsert_bill(db_session, congress=119, slug="hr", number=1, title="Mine", delegation=True)
    theirs = upsert_bill(db_session, congress=119, slug="hr", number=2, title="Not ours")
    theirs.bill.description = "Not ours"  # even with text, it must not be picked up
    state = Entity(entity_type="bill", name="State bill", jurisdiction_level="state", jurisdiction_name="FL", external_ids={}, attributes={})
    db_session.add(state)
    db_session.flush()
    db_session.add(Bill(entity_id=state.id, bill_number="HB 1", session="2026", status="Introduced", source_system="legiscan", description="A state bill"))
    db_session.flush()
    chosen, _ = select_bills_needing_summary(db_session, model="m")
    names = {e.name for e in chosen}
    assert "Mine" in names and "State bill" in names and "Not ours" not in names
    assert is_eligible(mine) and not is_eligible(theirs) and is_eligible(state)


def test_a_bill_first_seen_in_a_roll_call_has_no_description_or_summary(db_session, delegation):
    stub = upsert_bill(db_session, congress=119, slug="s", number=9, title="A bill about athletics")
    assert stub.bill.description is None and stub.attributes.get("delegation_sponsored") is None
    again = upsert_bill(db_session, congress=119, slug="s", number=9, title="A bill about athletics", delegation=True)
    assert again.id == stub.id and again.bill.description == "A bill about athletics"
    assert upsert_bill(db_session, congress=119, slug="s", number=9, title="A bill about athletics").attributes["delegation_sponsored"] is True  # never cleared


# --- roll calls -------------------------------------------------------------------

HOUSE = (FX / "house_roll_100.xml").read_bytes()
SENATE = (FX / "senate_roll_100.xml").read_bytes()


def test_house_xml_is_parsed_with_bioguide_ids():
    rc = parse_house(HOUSE, url="https://clerk.house.gov/evs/2025/roll100.xml", year=2025)
    assert (rc.chamber, rc.number, rc.congress, rc.when) == ("house", 100, 119, date(2025, 4, 10))
    assert rc.legis_num == "H CON RES 14" and rc.roll_call_id == "house-119-2025-100"
    assert set(rc.votes) == {"A000370", "A000055", "B001257"} and rc.votes["A000370"] == "Nay"
    assert rc.totals["yea"] == 216 and rc.totals["nay"] == 214
    assert parse_house(b"<html>nope</html>", url="u", year=2025) is None


def test_senate_xml_is_parsed_with_lis_ids():
    rc = parse_senate(SENATE, url="u")
    assert (rc.chamber, rc.number, rc.when, rc.legis_num) == ("senate", 100, date(2025, 3, 3), "S. 9")
    assert set(rc.votes) == {"S404", "S428", "S354"}
    assert rc.totals["yea"] == 51 and rc.totals["nay"] == 45


def test_only_delegation_votes_are_stored_and_attached_to_the_bill(db_session, delegation):
    rc = parse_house(HOUSE, url="https://clerk.house.gov/evs/2025/roll100.xml", year=2025)
    assert store_roll_call(db_session, rc, _members_by_id(db_session)) == "stored"
    bill = db_session.execute(select(Entity).where(Entity.external_ids["congress_bill"].as_string() == "119-hconres-14")).scalar_one()
    ev = db_session.execute(select(Event).where(Event.entity_id == bill.id)).scalar_one()
    assert ev.event_type == "vote" and ev.attributes["yea"] == 216 and ev.attributes["roll_call_id"] == "house-119-2025-100"
    voted = db_session.execute(select(Relationship).where(Relationship.relationship_type == "voted")).scalars().all()
    assert len(voted) == 1  # Bilirakis only; the two Alabama/North Carolina votes are not stored
    assert voted[0].from_entity_id == delegation["B001257"].id and voted[0].attributes["vote"] in ("Yea", "Nay", "Present", "Not Voting")
    assert bill.attributes.get("delegation_sponsored") is None  # a vote alone does not earn a summary
    assert store_roll_call(db_session, rc, _members_by_id(db_session)) == "duplicate"


def test_senate_vote_matches_the_senator_by_lis_id(db_session, delegation):
    rc = parse_senate(SENATE, url="u")
    assert store_roll_call(db_session, rc, _members_by_id(db_session)) == "stored"
    voted = db_session.execute(select(Relationship).where(Relationship.relationship_type == "voted")).scalar_one()
    assert voted.from_entity_id == delegation["S404" and next(k for k, v in delegation.items() if v.external_ids.get("lis_id") == "S404")].id


def test_roll_calls_without_a_bill_or_a_florida_vote_are_not_stored(db_session, delegation):
    rc = parse_house(HOUSE, url="u", year=2025)
    rc.legis_num = None
    assert store_roll_call(db_session, rc, _members_by_id(db_session)) == "no_bill"
    rc.legis_num = "H R 1"
    rc.votes = {"A000370": "Nay"}
    assert store_roll_call(db_session, rc, _members_by_id(db_session)) == "no_delegation_votes"
    assert db_session.execute(select(Event)).scalars().all() == []


def test_chamber_sync_walks_until_the_numbers_run_out_and_resumes(db_session, delegation):
    calls = []

    def fetch(url):
        calls.append(url)
        return HOUSE if url.endswith("roll100.xml") else None

    out = sync_chamber(db_session, fetch, chamber="house", congress=119, year=2025, start=100)
    assert out["stored"] == 1 and out["fetched"] == 1
    assert calls[-1].endswith("roll101.xml")
    calls.clear()
    again = sync_chamber(db_session, fetch, chamber="house", congress=119, year=2025)
    assert again["fetched"] == 0 and calls == [calls[0]] and calls[0].endswith("roll101.xml")  # resumed after the last stored


# --- the client -----------------------------------------------------------------

def test_client_needs_a_key_and_never_leaks_it():
    with pytest.raises(CongressApiError, match="CONGRESS_API_KEY"):
        CongressClient(api_key="")

    def handler(request):
        return httpx.Response(403, json={"error": "bad key"})

    c = CongressClient("SECRETKEY", pause=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(CongressApiError) as exc:
        c.get("/member/X")
    assert "SECRETKEY" not in str(exc.value)


def test_client_follows_pagination_and_treats_404_as_empty():
    pages = {0: {"items": [{"n": 1}, {"n": 2}], "pagination": {"next": "x"}}, 250: {"items": [{"n": 3}], "pagination": {}}}

    def handler(request):
        if request.url.path.endswith("/missing"):
            return httpx.Response(404)
        return httpx.Response(200, json=pages[int(request.url.params["offset"])])

    c = CongressClient("k", pause=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [i["n"] for i in c.paged("/things", "items")] == [1, 2, 3]
    assert c.get("/missing") == {}


def test_rate_limit_is_a_clear_error_and_a_renamed_list_key_is_still_read():
    def handler(request):
        if request.url.path.endswith("/limited"):
            return httpx.Response(429)
        return httpx.Response(200, json={"request": {}, "somethingElse": [{"n": 1}], "pagination": {}})

    c = CongressClient("k", pause=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(CongressApiError, match="rate limit"):
        c.get("/limited")
    assert list(c.paged("/x", "expectedKey")) == [{"n": 1}]
