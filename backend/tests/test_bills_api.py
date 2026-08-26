import uuid


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


def test_get_bill_not_found(client):
    resp = client.get(f"/bills/{uuid.uuid4()}")
    assert resp.status_code == 404


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
