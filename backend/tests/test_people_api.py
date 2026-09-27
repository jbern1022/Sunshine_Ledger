"""Legislator endpoint tests.

Sponsorship is a plain fact drawn from bill records. These pin the counting
rules -- particularly that a legislator listed twice on one bill counts
once -- because an inflated sponsorship count would read as a claim about
how active someone is.
"""

import uuid
from datetime import date

from app.models import Claim, Entity, Event, Relationship


def _add_person(db, *, name, district=None, role=None, party=None, jurisdiction="FL"):
    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="state",
        jurisdiction_name=jurisdiction,
        external_ids={"legiscan_people_id": name},
        attributes={k: v for k, v in (("district", district), ("role", role), ("party", party)) if v},
    )
    db.add(person)
    db.commit()
    return person


def _sponsor(db, person, bill_entity, rel_type="sponsor"):
    db.add(
        Relationship(
            from_entity_id=person.id, to_entity_id=bill_entity.id, relationship_type=rel_type
        )
    )
    db.commit()


def test_list_is_empty_without_sponsorships(client):
    body = client.get("/people").json()
    assert body == {"total": 0, "items": []}


def test_person_without_sponsorships_is_not_listed(client, db_session):
    """The list answers 'who sponsors tracked bills', so someone attached to
    nothing isn't an entry."""
    _add_person(db_session, name="Unattached Person")
    assert client.get("/people").json()["total"] == 0


def test_lists_sponsor_with_attributes(client, db_session, bill_factory):
    bill = bill_factory()
    person = _add_person(db_session, name="Jane Smith", district="HD-120", role="Rep", party="R")
    _sponsor(db_session, person, bill)

    item = client.get("/people").json()["items"][0]
    assert item["name"] == "Jane Smith"
    assert item["district"] == "HD-120"
    assert item["role"] == "Rep"
    assert item["sponsored_count"] == 1


def test_counts_cosponsorships(client, db_session, bill_factory):
    bill = bill_factory()
    person = _add_person(db_session, name="Co Sponsor")
    _sponsor(db_session, person, bill, rel_type="co_sponsor")

    assert client.get("/people").json()["items"][0]["sponsored_count"] == 1


def test_same_bill_twice_counts_once(client, db_session, bill_factory):
    """A legislator can be recorded as both sponsor and co-sponsor on one
    bill. Counting that twice would overstate how much they sponsor."""
    bill = bill_factory()
    person = _add_person(db_session, name="Dual Role")
    _sponsor(db_session, person, bill, rel_type="sponsor")
    _sponsor(db_session, person, bill, rel_type="co_sponsor")

    assert client.get("/people").json()["items"][0]["sponsored_count"] == 1


def test_ordered_by_sponsorship_count(client, db_session, bill_factory):
    prolific = _add_person(db_session, name="Prolific")
    occasional = _add_person(db_session, name="Occasional")
    for i in range(3):
        _sponsor(db_session, prolific, bill_factory(bill_number=f"HB {i}"))
    _sponsor(db_session, occasional, bill_factory(bill_number="HB 99"))

    names = [i["name"] for i in client.get("/people").json()["items"]]
    assert names == ["Prolific", "Occasional"]


def test_search_matches_name_and_district(client, db_session, bill_factory):
    person = _add_person(db_session, name="Jane Smith", district="HD-120")
    _sponsor(db_session, person, bill_factory())

    assert client.get("/people", params={"q": "Smith"}).json()["total"] == 1
    assert client.get("/people", params={"q": "HD-120"}).json()["total"] == 1
    assert client.get("/people", params={"q": "nobody"}).json()["total"] == 0


def test_total_reflects_full_match_count_not_just_the_page(client, db_session, bill_factory):
    """total must be a real count of every match, not len() of the paginated
    page -- otherwise a client paging through results sees `total` shrink to
    `limit` and never knows there's more to fetch."""
    for i in range(5):
        person = _add_person(db_session, name=f"Legislator {i}")
        _sponsor(db_session, person, bill_factory(bill_number=f"HB {i}"))

    body = client.get("/people", params={"limit": 2}).json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_detail_lists_bills_with_relationship_type(client, db_session, bill_factory):
    bill = bill_factory(bill_number="HB 7", name="A Test Bill")
    person = _add_person(db_session, name="Jane Smith", district="HD-120")
    _sponsor(db_session, person, bill, rel_type="co_sponsor")

    body = client.get(f"/people/{person.id}").json()
    assert body["name"] == "Jane Smith"
    assert len(body["bills"]) == 1
    assert body["bills"][0]["bill_number"] == "HB 7"
    assert body["bills"][0]["relationship_type"] == "co_sponsor"


def test_detail_includes_the_plain_language_summary(client, db_session, bill_factory):
    """So a reader sees what a legislator's bills actually do without
    clicking through each one."""
    bill = bill_factory()
    person = _add_person(db_session, name="Jane Smith")
    _sponsor(db_session, person, bill)
    db_session.add(
        Claim(
            bill_entity_id=bill.id,
            claim_type="what_it_does",
            claim_text="This bill does a thing.",
            generated_by="llm:llama3.1:8b",
        )
    )
    db_session.commit()

    assert client.get(f"/people/{person.id}").json()["bills"][0]["what_it_does"] == "This bill does a thing."


def test_detail_includes_voting_record_with_the_roll_calls_own_date_and_description(
    client, db_session, bill_factory
):
    bill = bill_factory(bill_number="HB 7", name="A Test Bill")
    person = _add_person(db_session, name="Jane Smith")

    db_session.add(
        Event(
            entity_id=bill.id,
            event_type="vote",
            event_date=date(2026, 2, 25),
            title="House: Third Reading RCS#549",
            attributes={"roll_call_id": "1644238", "chamber": "H", "yea": 82, "nay": 30, "passed": True},
        )
    )
    db_session.add(
        Relationship(
            from_entity_id=person.id,
            to_entity_id=bill.id,
            relationship_type="voted",
            attributes={"roll_call_id": "1644238", "vote": "Yea"},
        )
    )
    db_session.commit()

    body = client.get(f"/people/{person.id}").json()
    assert len(body["votes"]) == 1
    vote = body["votes"][0]
    assert vote["bill_number"] == "HB 7"
    assert vote["vote"] == "Yea"
    assert vote["roll_call_description"] == "House: Third Reading RCS#549"
    assert vote["date"] == "2026-02-25"


def test_voting_record_is_empty_for_a_sponsor_who_never_voted(client, db_session, bill_factory):
    bill = bill_factory()
    person = _add_person(db_session, name="Jane Smith")
    _sponsor(db_session, person, bill)

    assert client.get(f"/people/{person.id}").json()["votes"] == []


def test_detail_404s_for_unknown_person(client):
    assert client.get(f"/people/{uuid.uuid4()}").status_code == 404


def test_detail_404s_for_a_bill_id(client, bill_factory):
    """Entity ids are shared across types, so asking for a bill here must
    not return a malformed person."""
    bill = bill_factory()
    assert client.get(f"/people/{bill.id}").status_code == 404


def _roll_call(db, bill, person, *, roll_call_id, title, vote, when, source_url=None):
    from app.models import Source

    source_id = None
    if source_url:
        from datetime import datetime, timezone

        source = Source(url=source_url, publisher="FL Legislature via LegiScan", source_type="legiscan_roll_call",
                        retrieved_at=datetime(2026, 9, 25, tzinfo=timezone.utc))
        db.add(source)
        db.flush()
        source_id = source.id
    db.add(Event(entity_id=bill.id, event_type="vote", event_date=when, title=title,
                 attributes={"roll_call_id": roll_call_id}, source_id=source_id))
    db.add(Relationship(from_entity_id=person.id, to_entity_id=bill.id, relationship_type="voted",
                        attributes={"roll_call_id": roll_call_id, "vote": vote}))
    db.commit()


def test_votes_carry_stage_topics_and_roll_call_link(client, db_session, bill_factory):
    from app.models import Tag
    from app.pipeline.topic_tagging import assign_tags_for_bill

    db_session.add(Tag(slug="housing", label="Housing", active=True))
    db_session.commit()
    bill = bill_factory(bill_number="HB 1389", name="Affordable Housing")
    assign_tags_for_bill(db_session, bill.id, ollama_tag_slugs=["housing"])
    person = _add_person(db_session, name="Mike Redondo", district="HD-118")
    _roll_call(db_session, bill, person, roll_call_id="1", title="House Commerce Committee", vote="Yea",
               when=date(2026, 2, 24))
    _roll_call(db_session, bill, person, roll_call_id="2", title="House: Third Reading RCS#662", vote="Nay",
               when=date(2026, 3, 4), source_url="https://legiscan.com/FL/rollcall/H1389/id/2")

    votes = client.get(f"/people/{person.id}").json()["votes"]

    assert [(v["roll_call_id"], v["stage"], v["vote"]) for v in votes] == [("2", "floor", "Nay"), ("1", "committee", "Yea")]
    assert votes[0]["source_url"] == "https://legiscan.com/FL/rollcall/H1389/id/2"
    assert votes[1]["source_url"] is None
    assert votes[0]["tags"] == [{"slug": "housing", "label": "Housing"}]


def test_committees_are_flagged_and_filterable(client, db_session, bill_factory):
    bill = bill_factory()
    rep = _add_person(db_session, name="Mike Redondo", district="HD-118")
    committee = _add_person(db_session, name="Commerce Committee")
    committee.attributes = {"committee": True}
    db_session.commit()
    _sponsor(db_session, rep, bill)
    _sponsor(db_session, committee, bill)

    everyone = {p["name"]: p["is_committee"] for p in client.get("/people").json()["items"]}
    assert everyone == {"Mike Redondo": False, "Commerce Committee": True}
    assert [p["name"] for p in client.get("/people?kind=legislator").json()["items"]] == ["Mike Redondo"]
    assert [p["name"] for p in client.get("/people?kind=committee").json()["items"]] == ["Commerce Committee"]
    assert client.get(f"/people/{committee.id}").json()["is_committee"] is True
