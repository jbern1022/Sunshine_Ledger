import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import BillLayer, BillLayerReview

AUTH = ("testadmin", "testpass")


def _layer(db, entity, version=1, superseded=False):
    row = BillLayer(
        bill_entity_id=entity.id, layer="interpretation", origin="sunshine_ledger_ai", version=version,
        superseded_at=datetime.now(timezone.utc) if superseded else None, evidence_state="supported",
        scope_note="Bill text", items=[{"text": "t", "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test", method_version="interpretation/sunshine_ledger_ai/1", input_hash=f"h{version}",
    )
    db.add(row)
    db.commit()
    return row


def test_review_endpoints_require_auth(client):
    assert client.get("/bill-layers/admin/unreviewed").status_code == 401


def test_unreviewed_lists_current_unapproved_only(client, db_session, bill_factory):
    entity = bill_factory()
    _layer(db_session, entity, version=1, superseded=True)
    current = _layer(db_session, entity, version=2)
    body = client.get("/bill-layers/admin/unreviewed", auth=AUTH).json()
    assert [b["id"] for b in body] == [str(current.id)]
    assert body[0]["bill_number"] == "HB 123"


def test_approve_current_version(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    resp = client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved", "note": "checked"}, auth=AUTH)
    assert resp.status_code == 201
    assert "reviewer" not in resp.json() and "note" not in resp.json()
    assert client.get("/bill-layers/admin/unreviewed", auth=AUTH).json() == []


def test_approving_superseded_version_is_409(client, db_session, bill_factory):
    entity = bill_factory()
    old = _layer(db_session, entity, version=1, superseded=True)
    resp = client.post(f"/bill-layers/admin/{old.id}/review", json={"decision": "approved"}, auth=AUTH)
    assert resp.status_code == 409


def test_double_approval_is_409(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved"}, auth=AUTH)
    assert client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved"}, auth=AUTH).status_code == 409


def test_only_approved_decision_accepted(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    assert client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "rejected"}, auth=AUTH).status_code == 422


def test_review_unknown_id_is_404(client):
    resp = client.post(f"/bill-layers/admin/{uuid.uuid4()}/review", json={"decision": "approved"}, auth=AUTH)
    assert resp.status_code == 404


def test_review_without_auth_is_401(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    resp = client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved"})
    assert resp.status_code == 401


def test_db_guard_rejects_second_approval_row(db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    db_session.add(BillLayerReview(bill_layer_id=row.id, decision="approved", reviewer="a", note=None))
    db_session.commit()
    db_session.add(BillLayerReview(bill_layer_id=row.id, decision="approved", reviewer="b", note=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
