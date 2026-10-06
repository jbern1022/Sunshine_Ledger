from datetime import datetime, timezone

from app.impact_lens.criteria import validate_criteria
from app.impact_lens.vocabulary import VOCABULARY_VERSION
from app.models import BillLayer, BillLayerCriteria, BillLayerCriteriaReview

LANDLORD = {
    "group": "Landlords", "text": "must offer a 12-month renewal", "quote": "A landlord shall offer a 12-month renewal.",
    "conditions": [{"text": "Applies in Duval County.", "quote": "This section applies in Duval County."}],
    "exceptions": [{"text": "Not single-family homes rented by their owner.", "quote": "This does not apply to a single-family home rented by its owner."}],
}
DISTRICTS = {
    "group": "Landlords", "text": "must register", "quote": "A landlord shall register.",
    "conditions": [{"text": "Applies in Jacksonville.", "quote": "This applies in Jacksonville."}], "exceptions": [],
}
LAYER_ARGS = dict(layer="who_it_affects", origin="sunshine_ledger_ai", generated_by="llm:test",
                  method_version="who_it_affects/sunshine_ledger_ai/11")


def _layer(db, entity, items, *, version=1, superseded=False, state="supported", scope="Bill text"):
    row = BillLayer(
        bill_entity_id=entity.id, version=version, evidence_state=state, scope_note=scope, items=items,
        superseded_at=datetime.now(timezone.utc) if superseded else None, input_hash=f"h{version}", **LAYER_ARGS,
    )
    db.add(row)
    db.commit()
    return row


def _criteria(db, layer, index, raw, *, vocab=VOCABULARY_VERSION, method="impact_lens_criteria/8"):
    item = layer.items[index]
    crit = validate_criteria(
        raw, entry_index=index, n_conditions=len(item.get("conditions") or []),
        n_exceptions=len(item.get("exceptions") or []), entry=item, vocabulary_version=vocab,
    )
    row = BillLayerCriteria(bill_layer_id=layer.id, entry_index=index, vocabulary_version=vocab,
                            method_version=method, generated_by="llm:test", criteria=crit)
    db.add(row)
    db.commit()
    return row


LANDLORD_RAW = {
    "audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]},
    "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Duval"], "from": {"kind": "condition", "index": 0}}],
    "excludes": [{"attr": "property_type", "op": "in", "values": ["single_family"], "from": {"kind": "exception", "index": 0}}],
}


def test_unknown_or_non_bill_is_404(client, bill_factory):
    import uuid
    assert client.get(f"/bills/{uuid.uuid4()}/impact-lens").status_code == 404


def test_a_bill_without_a_who_layer_is_unavailable_not_an_error(client, bill_factory):
    entity = bill_factory()
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["available"] is False and body["complete"] is False
    assert body["entries"] == [] and body["questions"] == []
    assert "no Who it affects" in body["unavailable_reason"]
    assert body["vocabulary_version"] == VOCABULARY_VERSION


def test_a_fully_mapped_supported_layer_is_complete_with_the_slice_it_needs(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    _criteria(db_session, layer, 0, LANDLORD_RAW)
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["available"] and body["complete"] is True and body["incomplete_reasons"] == []
    e = body["entries"][0]
    assert e["group"] == "Landlords" and e["reviewed"] is False
    assert e["criteria"]["audience"]["any_of"] == ["landlord"]
    assert e["conditions"][0]["text"] == "Applies in Duval County."
    keys = [q["key"] for q in body["questions"]]
    assert keys == ["role", "county", "property_type"]  # no municipality: the bill names none
    role = body["questions"][0]
    assert [o["value"] for o in role["options"]] == ["landlord"] and role["options"][0]["label"] == "Landlord"
    counties = body["questions"][1]["options"]
    assert len(counties) == 67 and {"value": "Duval", "label": "Duval County"} in counties
    assert [o["value"] for o in body["questions"][2]["options"]] == ["single_family"]
    assert body["layer"]["version"] == 1 and body["layer"]["evidence_state"] == "supported"


def test_municipalities_only_the_places_the_bill_names(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [DISTRICTS])
    _criteria(db_session, layer, 0, {
        "audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]},
        "requires": [{"attr": "jurisdiction", "op": "in", "values": ["municipality:Jacksonville", "county:Miami-Dade"],
                      "from": {"kind": "condition", "index": 0}}],
    })
    questions = {q["key"]: q for q in client.get(f"/bills/{entity.id}/impact-lens").json()["questions"]}
    assert [o["value"] for o in questions["municipality"]["options"]] == ["Jacksonville"]
    assert questions["municipality"]["counties"] == {"Jacksonville": ["Duval"]}
    assert "property_type" not in questions


def test_an_entry_with_no_mapping_makes_the_layer_incomplete(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD, DISTRICTS])
    _criteria(db_session, layer, 0, LANDLORD_RAW)
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["complete"] is False
    assert body["incomplete_reasons"] == ["1 of 2 entries have no questions mapped yet."]
    assert body["entries"][1]["criteria"] is None


def test_a_capped_or_unsupported_layer_is_incomplete(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD], scope="Bill text · first 20 of 31 entries")
    _criteria(db_session, layer, 0, LANDLORD_RAW)
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["complete"] is False and body["incomplete_reasons"] == ["The analysis lists only the first entries of a longer list."]

    other = bill_factory(bill_number="HB 2")
    weak = _layer(db_session, other, [LANDLORD], state="insufficient_evidence")
    _criteria(db_session, weak, 0, LANDLORD_RAW)
    assert "not marked supported" in client.get(f"/bills/{other.id}/impact-lens").json()["incomplete_reasons"][0]


def test_only_the_current_layer_and_current_vocabulary_count(client, db_session, bill_factory):
    entity = bill_factory()
    old = _layer(db_session, entity, [LANDLORD], version=1, superseded=True)
    _criteria(db_session, old, 0, LANDLORD_RAW)
    new = _layer(db_session, entity, [LANDLORD], version=2)
    _criteria(db_session, new, 0, LANDLORD_RAW, vocab=VOCABULARY_VERSION - 1, method="impact_lens_criteria/1")
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["layer"]["version"] == 2
    assert body["entries"][0]["criteria"] is None and body["complete"] is False  # old-vocabulary rows are ignored


def test_the_newest_mapping_wins_and_review_follows_the_row(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    first = _criteria(db_session, layer, 0, {}, method="impact_lens_criteria/7")  # nothing mapped
    second = _criteria(db_session, layer, 0, LANDLORD_RAW, method="impact_lens_criteria/8")
    db_session.add(BillLayerCriteriaReview(criteria_id=first.id, decision="approved", reviewer="joe", note="secret"))
    db_session.commit()
    resp = client.get(f"/bills/{entity.id}/impact-lens")
    e = resp.json()["entries"][0]
    assert e["criteria"]["audience"]["any_of"] == ["landlord"]
    assert e["reviewed"] is False  # the approval was on the older row
    db_session.add(BillLayerCriteriaReview(criteria_id=second.id, decision="approved", reviewer="joe"))
    db_session.commit()
    resp = client.get(f"/bills/{entity.id}/impact-lens")
    assert resp.json()["entries"][0]["reviewed"] is True
    assert "joe" not in resp.text and "secret" not in resp.text  # reviewer and note stay private


def test_a_rejected_review_does_not_count_as_approval(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    row = _criteria(db_session, layer, 0, LANDLORD_RAW)
    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="rejected", reviewer="joe"))
    db_session.commit()
    assert client.get(f"/bills/{entity.id}/impact-lens").json()["entries"][0]["reviewed"] is False
