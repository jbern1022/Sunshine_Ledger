from datetime import date, datetime, timedelta, timezone

from app.models import BillLayer, BillLayerReview, StaffAnalysis


def _row(db, entity, layer, origin, version=1, superseded=False, text="t"):
    row = BillLayer(
        bill_entity_id=entity.id, layer=layer, origin=origin, version=version,
        superseded_at=datetime.now(timezone.utc) if superseded else None, evidence_state="supported",
        scope_note="Bill text", items=[{"text": text, "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test", method_version=f"{layer}/{origin}/1", input_hash=f"{layer}{origin}{version}",
    )
    db.add(row)
    db.commit()
    return row


def test_bill_without_layers_has_empty_layers(client, bill_factory):
    entity = bill_factory()
    body = client.get(f"/bills/{entity.id}").json()
    assert body["layers"] == {"bill_says": [], "interpretation": [], "expected_effect": [], "who_it_affects": []}
    assert body["has_staff_analysis"] is False


def test_blocks_are_grouped_by_layer_with_earlier_versions(client, db_session, bill_factory):
    entity = bill_factory()
    _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=1, superseded=True, text="old")
    _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=2, text="new")
    _row(db_session, entity, "bill_says", "bill_text")
    layers = client.get(f"/bills/{entity.id}").json()["layers"]
    assert [b["origin"] for b in layers["bill_says"]] == ["bill_text"]
    block = layers["interpretation"][0]
    assert block["origin"] == "sunshine_ledger_ai"
    assert block["current"]["items"][0]["text"] == "new"
    assert [v["items"][0]["text"] for v in block["earlier_versions"]] == ["old"]
    assert layers["expected_effect"] == []


def test_review_status_is_derived_and_private_fields_hidden(client, db_session, bill_factory):
    entity = bill_factory()
    row = _row(db_session, entity, "interpretation", "sunshine_ledger_ai")
    db_session.add(BillLayerReview(bill_layer_id=row.id, decision="approved", reviewer="joe", note="secret"))
    db_session.commit()
    resp = client.get(f"/bills/{entity.id}")
    current = resp.json()["layers"]["interpretation"][0]["current"]
    assert current["review_status"] == "reviewed" and current["reviewed_at"] is not None
    assert "joe" not in resp.text and "secret" not in resp.text


def test_new_version_after_review_starts_unreviewed(client, db_session, bill_factory):
    entity = bill_factory()
    old = _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=1)
    db_session.add(BillLayerReview(bill_layer_id=old.id, decision="approved", reviewer="joe"))
    old.superseded_at = datetime.now(timezone.utc)
    db_session.commit()
    _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=2)
    block = client.get(f"/bills/{entity.id}").json()["layers"]["interpretation"][0]
    assert block["current"]["review_status"] == "not_reviewed"
    assert block["earlier_versions"][0]["review_status"] == "reviewed"


def test_has_staff_analysis(client, db_session, bill_factory):
    entity = bill_factory()
    db_session.add(StaffAnalysis(entity_id=entity.id, legiscan_supplement_id=77, committee="Rules",
                                 analysis_date=date(2026, 3, 1), source_url="https://x/a.pdf", text="III. Effect"))
    db_session.commit()
    assert client.get(f"/bills/{entity.id}").json()["has_staff_analysis"] is True


def test_has_staff_analysis_false_for_empty_text_only(client, db_session, bill_factory):
    entity = bill_factory()
    db_session.add(StaffAnalysis(entity_id=entity.id, legiscan_supplement_id=78, committee="Rules",
                                 analysis_date=date(2026, 3, 1), source_url="https://x/b.pdf", text=""))
    db_session.add(StaffAnalysis(entity_id=entity.id, legiscan_supplement_id=79, committee="Rules",
                                 analysis_date=date(2026, 3, 2), source_url="https://x/c.pdf", text=None))
    db_session.commit()
    assert client.get(f"/bills/{entity.id}").json()["has_staff_analysis"] is False


def test_who_it_affects_block_carries_group_conditions_and_exceptions(client, db_session, bill_factory):
    entity = bill_factory()
    db_session.add(BillLayer(
        bill_entity_id=entity.id, layer="who_it_affects", origin="sunshine_ledger_ai", version=1,
        evidence_state="supported", scope_note="Bill text",
        items=[{"text": "Must return deposits within 15 days.", "group": "Landlords", "change_kind": "obligation",
                "quote": "A landlord shall return ...", "section_ref": "Section 1",
                "conditions": [], "exceptions": [{"text": "Fewer than 3 units", "quote": "does not apply ..."}],
                "assumptions": [], "affected_groups": ["Landlords"]}],
        generated_by="llm:test", method_version="who_it_affects/sunshine_ledger_ai/1", input_hash="w1",
    ))
    db_session.commit()
    [block] = client.get(f"/bills/{entity.id}").json()["layers"]["who_it_affects"]
    item = block["current"]["items"][0]
    assert (item["group"], item["change_kind"]) == ("Landlords", "obligation")
    assert item["exceptions"] == [{"text": "Fewer than 3 units", "quote": "does not apply ..."}]
