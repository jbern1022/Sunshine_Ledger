"""Correction, dispute and right-of-reply process (Notion spec, decisions
agreed 2026-10-01)."""
import uuid
from datetime import datetime, timezone

from app.models import BillLayer, CorrectionRecord, Flag

ADMIN = ("testadmin", "testpass")


def _layer(db, entity, version=1, text="Requires landlords to return deposits in 15 days."):
    row = BillLayer(
        bill_entity_id=entity.id, layer="interpretation", origin="sunshine_ledger_ai", version=version,
        evidence_state="supported", scope_note="Bill text",
        items=[{"text": text, "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test", method_version="interpretation/sunshine_ledger_ai/6", input_hash=f"h{version}",
    )
    db.add(row)
    db.commit()
    return row


def _challenge(client, entity, layer, **extra):
    body = {
        "bill_entity_id": str(entity.id), "object_type": "bill_layer", "object_id": str(layer.id),
        "object_version": 1, "category": "factually_wrong", "reason_text": "The bill says 30 days, not 15.",
        "evidence_url": "https://www.flsenate.gov/Session/Bill/2026/1/BillText/Filed/PDF", **extra,
    }
    resp = client.post("/flags", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_challenge_records_target_category_and_evidence(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity)
    flag = db_session.get(Flag, uuid.UUID(_challenge(client, entity, layer, is_named_party=True)))
    assert (flag.object_type, flag.object_id, flag.object_version) == ("bill_layer", layer.id, 1)
    assert (flag.category, flag.is_named_party, flag.status) == ("factually_wrong", True, "pending")
    assert flag.evidence_url.startswith("https://www.flsenate.gov/")


def test_challenge_target_must_belong_to_the_bill(client, db_session, bill_factory):
    entity, other = bill_factory(), bill_factory(bill_number="HB 9")
    layer = _layer(db_session, other)
    resp = client.post("/flags", json={
        "bill_entity_id": str(entity.id), "object_type": "bill_layer", "object_id": str(layer.id),
        "reason_text": "Wrong bill entirely",
    })
    assert resp.status_code == 404


def test_old_form_still_works(client, bill_factory):
    entity = bill_factory()
    resp = client.post("/flags", json={"bill_entity_id": str(entity.id), "reason_text": "This looks wrong"})
    assert resp.status_code == 201
    assert (resp.json()["object_type"], resp.json()["category"]) == ("bill", "other")


def test_triage_marks_disputed_and_the_statement_stays_visible(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity)
    flag_id = _challenge(client, entity, layer)
    resp = client.post(f"/flags/admin/{flag_id}/triage", json={"severity": "critical", "disputed": True}, auth=ADMIN)
    assert resp.status_code == 200 and resp.json()["disputed_since"]

    bill = client.get(f"/bills/{entity.id}").json()
    [dispute] = bill["disputes"]
    assert (dispute["object_type"], dispute["object_id"], dispute["severity"]) == ("bill_layer", str(layer.id), "critical")
    # Decision 2: labelled, never hidden -- the block is still served.
    assert bill["layers"]["interpretation"][0]["current"]["items"][0]["text"].startswith("Requires landlords")


def test_minor_challenges_cannot_mark_disputed(client, db_session, bill_factory):
    entity = bill_factory()
    flag_id = _challenge(client, entity, _layer(db_session, entity))
    resp = client.post(f"/flags/admin/{flag_id}/triage", json={"severity": "minor", "disputed": True}, auth=ADMIN)
    assert resp.status_code == 422


def test_decision_records_correction_with_both_versions_and_evidence(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity)
    flag_id = _challenge(client, entity, layer)
    client.post(f"/flags/admin/{flag_id}/triage", json={"severity": "material", "disputed": True}, auth=ADMIN)
    resp = client.post(f"/flags/admin/{flag_id}/decide", auth=ADMIN, json={
        "decision": "correction",
        "explanation": "The bill sets 30 days; the interpretation said 15.",
        "correction": {
            "change_type": "correction", "severity": "material",
            "explanation": "Interpretation misread the deadline in Section 1.",
            "prior_text": "Requires landlords to return deposits in 15 days.",
            "current_text": "Requires landlords to return deposits in 30 days.",
            "prior_version": 1, "current_version": 2,
            "evidence_links": [{"url": "https://www.flsenate.gov/x.pdf", "role": "supporting", "note": "Section 1"}],
            "origin": "sunshine_ledger_ai", "was_reviewed": False,
            "methodology_version": "interpretation/sunshine_ledger_ai/6",
        },
    })
    assert resp.status_code == 200, resp.text
    assert (resp.json()["status"], resp.json()["disputed_since"]) == ("decided", None)

    bill = client.get(f"/bills/{entity.id}").json()
    assert bill["disputes"] == []
    [c] = bill["corrections"]
    assert (c["prior_text"], c["current_text"]) == (
        "Requires landlords to return deposits in 15 days.", "Requires landlords to return deposits in 30 days.")
    assert c["evidence_links"][0]["role"] == "supporting"
    assert (c["trigger"], c["origin"], c["was_reviewed"]) == ("challenge", "sunshine_ledger_ai", False)
    assert c["decided_by_label"] == "Sunshine Ledger editor" and "decided_by" not in c
    assert db_session.query(CorrectionRecord).one().decided_by == "testadmin"

    log = client.get("/corrections").json()
    assert [x["id"] for x in log] == [c["id"]]


def test_a_correction_decision_needs_its_record(client, db_session, bill_factory):
    entity = bill_factory()
    flag_id = _challenge(client, entity, _layer(db_session, entity))
    resp = client.post(f"/flags/admin/{flag_id}/decide", auth=ADMIN,
                       json={"decision": "correction", "explanation": "It was wrong, fixed."})
    assert resp.status_code == 422


def test_no_change_needs_only_an_explanation(client, db_session, bill_factory):
    entity = bill_factory()
    flag_id = _challenge(client, entity, _layer(db_session, entity))
    resp = client.post(f"/flags/admin/{flag_id}/decide", auth=ADMIN,
                       json={"decision": "no_change", "explanation": "The bill does say 15 days (Section 1)."})
    assert resp.status_code == 200 and resp.json()["decision"] == "no_change"
    assert client.get(f"/bills/{entity.id}").json()["corrections"] == []


def test_minor_corrections_are_on_the_bill_but_not_the_headline_log(client, bill_factory):
    entity = bill_factory()
    resp = client.post("/corrections/admin", auth=ADMIN, json={
        "bill_entity_id": str(entity.id), "object_type": "page_copy", "trigger": "internal_review",
        "change_type": "correction", "severity": "minor", "explanation": "Fixed a broken source link.",
    })
    assert resp.status_code == 201, resp.text
    assert len(client.get(f"/bills/{entity.id}").json()["corrections"]) == 1
    assert client.get("/corrections").json() == []
    assert len(client.get("/corrections", params={"severity": "all"}).json()) == 1


def test_admin_endpoints_need_auth(client, bill_factory):
    entity = bill_factory()
    assert client.post("/corrections/admin", json={}).status_code == 401
    assert client.post("/responses/admin", json={}).status_code == 401
    assert client.post(f"/flags/admin/{uuid.uuid4()}/triage", json={}).status_code == 401


def test_responses_are_kept_when_superseded(client, bill_factory):
    entity = bill_factory()
    base = {
        "bill_entity_id": str(entity.id), "responder_name": "Rep. Example", "responder_role": "Sponsor",
        "verified_via": "confirmed via the email on the Division of Elections candidate filing",
        "received_at": datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
    }
    first = client.post("/responses/admin", auth=ADMIN, json={**base, "text": "The bill does not change deposits."})
    assert first.status_code == 201, first.text
    second = client.post("/responses/admin", auth=ADMIN,
                         json={**base, "text": "Clarifying: Section 1 changes the deadline only.", "supersedes_id": first.json()["id"]})
    assert second.status_code == 201
    responses = client.get(f"/bills/{entity.id}").json()["responses"]
    assert len(responses) == 2
    assert responses[0]["superseded_by_id"] == second.json()["id"]
    assert responses[0]["verified_via"].startswith("confirmed via")


def test_a_decided_challenge_cannot_be_decided_again(client, db_session, bill_factory):
    entity = bill_factory()
    flag_id = _challenge(client, entity, _layer(db_session, entity))
    client.post(f"/flags/admin/{flag_id}/decide", auth=ADMIN, json={"decision": "no_change", "explanation": "Checked; accurate."})
    again = client.post(f"/flags/admin/{flag_id}/decide", auth=ADMIN, json={"decision": "no_change", "explanation": "Checked; accurate."})
    assert again.status_code == 409


def _admin_correction(client, entity, **fields):
    body = {
        "bill_entity_id": str(entity.id), "object_type": "page_copy", "trigger": "internal_review",
        "change_type": "correction", "severity": "material", "explanation": "Wrong committee named.", **fields,
    }
    resp = client.post("/corrections/admin", auth=ADMIN, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_log_entries_name_the_bill(client, bill_factory):
    entity = bill_factory(bill_number="H1389", name="Affordable Housing")
    _admin_correction(client, entity)
    [entry] = client.get("/corrections").json()
    assert (entry["bill_number"], entry["bill_name"]) == ("H1389", "Affordable Housing")


def test_log_filters_by_change_type_and_severity(client, bill_factory):
    entity = bill_factory()
    _admin_correction(client, entity, change_type="clarification")
    _admin_correction(client, entity, change_type="correction", severity="critical")
    _admin_correction(client, entity, change_type="correction", severity="minor")
    assert len(client.get("/corrections").json()) == 2
    assert [e["change_type"] for e in client.get("/corrections", params={"change_type": "clarification"}).json()] == ["clarification"]
    assert [e["severity"] for e in client.get("/corrections", params={"severity": "critical"}).json()] == ["critical"]
    assert client.get("/corrections", params={"change_type": "bogus"}).status_code == 422
