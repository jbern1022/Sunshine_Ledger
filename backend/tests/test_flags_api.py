import uuid


def test_create_flag_success(client, bill_factory):
    entity = bill_factory()

    resp = client.post("/flags", json={"bill_entity_id": str(entity.id), "reason_text": "This looks wrong"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["bill_entity_id"] == str(entity.id)
    assert body["status"] == "pending"


def test_create_flag_bill_not_found(client):
    resp = client.post("/flags", json={"bill_entity_id": str(uuid.uuid4()), "reason_text": "Not a real bill"})
    assert resp.status_code == 404


def test_create_flag_rejects_short_reason(client, bill_factory):
    entity = bill_factory()

    resp = client.post("/flags", json={"bill_entity_id": str(entity.id), "reason_text": "no"})
    assert resp.status_code == 422


def test_admin_flags_requires_auth(client):
    resp = client.get("/flags/admin")
    assert resp.status_code == 401


def test_admin_flags_rejects_bad_credentials(client):
    resp = client.get("/flags/admin", auth=("wrong", "wrong"))
    assert resp.status_code == 401


def test_admin_flags_lists_pending(client, bill_factory):
    entity = bill_factory()
    client.post("/flags", json={"bill_entity_id": str(entity.id), "reason_text": "Needs review"})

    resp = client.get("/flags/admin", auth=("testadmin", "testpass"))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["reason_text"] == "Needs review"
    assert body[0]["bill_number"] == "HB 123"


def test_admin_flag_status_update(client, bill_factory):
    entity = bill_factory()
    create_resp = client.post("/flags", json={"bill_entity_id": str(entity.id), "reason_text": "Needs review"})
    flag_id = create_resp.json()["id"]

    resp = client.patch(
        f"/flags/admin/{flag_id}",
        json={"status": "reviewed"},
        auth=("testadmin", "testpass"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewed"

    # No longer shows up under the default pending-only filter.
    pending = client.get("/flags/admin", auth=("testadmin", "testpass")).json()
    assert pending == []
