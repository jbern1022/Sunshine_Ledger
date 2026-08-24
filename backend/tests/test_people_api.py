"""Legislator endpoint tests.

Sponsorship is a plain fact drawn from bill records. These pin the counting
rules -- particularly that a legislator listed twice on one bill counts
once -- because an inflated sponsorship count would read as a claim about
how active someone is.
"""

import uuid

from app.models import Claim, Entity, Relationship


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


def test_detail_404s_for_unknown_person(client):
    assert client.get(f"/people/{uuid.uuid4()}").status_code == 404


def test_detail_404s_for_a_bill_id(client, bill_factory):
    """Entity ids are shared across types, so asking for a bill here must
    not return a malformed person."""
    bill = bill_factory()
    assert client.get(f"/people/{bill.id}").status_code == 404
