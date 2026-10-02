import uuid

from app.models import Flag


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


def test_dismissing_starts_email_retention_clock_and_leaves_the_queue(client, bill_factory, db_session):
    entity = bill_factory()
    flag_id = client.post(
        "/flags",
        json={"bill_entity_id": str(entity.id), "reason_text": "Needs review", "reporter_email": "a@example.com"},
    ).json()["id"]
    flag = db_session.get(Flag, uuid.UUID(flag_id))
    assert flag.resolved_at is None

    resp = client.post(f"/flags/admin/{flag_id}/triage", json={"dismiss": True, "note": "spam"}, auth=("testadmin", "testpass"))
    assert resp.status_code == 200 and resp.json()["status"] == "dismissed"
    db_session.refresh(flag)
    assert flag.resolved_at is not None
    assert client.get("/flags/admin", auth=("testadmin", "testpass")).json() == []
