import uuid
from datetime import date

from app.models import Entity, Event, Relationship


def test_list_bills_empty(client):
    resp = client.get("/bills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_bills_returns_created_bill(client, bill_factory):
    entity = bill_factory()

    resp = client.get("/bills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 123"
    assert body["items"][0]["entity_id"] == str(entity.id)


def test_list_bills_filters_by_status(client, bill_factory):
    bill_factory(bill_number="HB 1", status="Introduced")
    bill_factory(bill_number="HB 2", status="Passed")

    resp = client.get("/bills", params={"status": "Passed"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 2"


def test_list_bills_search_matches_bill_number(client, bill_factory):
    bill_factory(bill_number="HB 456", name="Unrelated title")

    resp = client.get("/bills", params={"q": "HB 456"})
    body = resp.json()
    assert body["total"] == 1


def test_list_bills_filters_by_geo_scope_name(client, bill_factory):
    bill_factory(bill_number="HB 1", geo_scope_names=["Miami-Dade County"])
    bill_factory(bill_number="HB 2", geo_scope_names=["Duval County"])

    resp = client.get("/bills", params={"geo_scope_name": "Miami-Dade County"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 1"


def test_get_bill_detail(client, bill_factory):
    entity = bill_factory()

    resp = client.get(f"/bills/{entity.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bill_number"] == "HB 123"
    assert body["claims"] == []
    assert body["news"] == []
    assert body["votes"] == []


def test_get_bill_not_found(client):
    resp = client.get(f"/bills/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_bill_detail_includes_a_roll_call_and_its_individual_votes(client, bill_factory, db_session):
    entity = bill_factory()
    person = Entity(
        entity_type="person",
        name="Jane Smith",
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_people_id": "19426"},
        attributes={},
    )
    db_session.add(person)
    db_session.flush()

    vote_event = Event(
        entity_id=entity.id,
        event_type="vote",
        event_date=date(2026, 2, 25),
        title="House: Third Reading RCS#549",
        attributes={
            "roll_call_id": "1644238",
            "chamber": "H",
            "yea": 82,
            "nay": 30,
            "nv": 5,
            "absent": 0,
            "total": 117,
            "passed": True,
        },
    )
    db_session.add(vote_event)
    db_session.add(
        Relationship(
            from_entity_id=person.id,
            to_entity_id=entity.id,
            relationship_type="voted",
            attributes={"roll_call_id": "1644238", "vote": "Yea"},
        )
    )
    db_session.commit()

    resp = client.get(f"/bills/{entity.id}")
    assert resp.status_code == 200
    votes = resp.json()["votes"]

    assert len(votes) == 1
    roll_call = votes[0]
    assert roll_call["description"] == "House: Third Reading RCS#549"
    assert roll_call["yea"] == 82
    assert roll_call["passed"] is True
    assert roll_call["votes"] == [
        {"person_entity_id": str(person.id), "person_name": "Jane Smith", "vote": "Yea"}
    ]


# --- status filter options ------------------------------------------------


def test_statuses_endpoint_is_empty_without_bills(client):
    assert client.get("/bills/statuses").json() == []


def test_statuses_returns_counts(client, bill_factory):
    bill_factory(bill_number="HB 1", status="Introduced")
    bill_factory(bill_number="HB 2", status="Introduced")
    bill_factory(bill_number="HB 3", status="Passed")

    body = client.get("/bills/statuses").json()
    assert {s["status"]: s["count"] for s in body} == {"Introduced": 2, "Passed": 1}


def test_statuses_ordered_by_count_descending(client, bill_factory):
    """Common statuses first so a dropdown isn't led by one-off municipal
    vocabulary."""
    bill_factory(bill_number="HB 1", status="Rare Status")
    for i in range(3):
        bill_factory(bill_number=f"HB 1{i}", status="Introduced")

    assert [s["status"] for s in client.get("/bills/statuses").json()] == ["Introduced", "Rare Status"]


def test_statuses_scoped_by_jurisdiction(client, db_session, bill_factory):
    a = bill_factory(bill_number="HB 1", status="Introduced")
    b = bill_factory(bill_number="ORD 1", status="Enacted")
    b.jurisdiction_name = "Jacksonville"
    db_session.commit()

    body = client.get("/bills/statuses", params={"jurisdiction_name": "Jacksonville"}).json()
    assert [s["status"] for s in body] == ["Enacted"]
    assert a.jurisdiction_name == "FL"


def test_statuses_route_is_not_shadowed_by_the_bill_detail_route(client, bill_factory):
    """FastAPI matches in definition order, so /bills/{entity_id} declared
    first would swallow this path and fail parsing "statuses" as a UUID."""
    bill_factory()
    assert client.get("/bills/statuses").status_code == 200
