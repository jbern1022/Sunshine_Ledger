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
