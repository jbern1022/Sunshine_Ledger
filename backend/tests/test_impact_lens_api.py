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


def _criteria(db, layer, index, raw, *, vocab=VOCABULARY_VERSION, method="impact_lens_criteria/8", approve=False):
    item = layer.items[index]
    crit = validate_criteria(
        raw, entry_index=index, n_conditions=len(item.get("conditions") or []),
        n_exceptions=len(item.get("exceptions") or []), entry=item, vocabulary_version=vocab,
    )
    row = BillLayerCriteria(bill_layer_id=layer.id, entry_index=index, vocabulary_version=vocab,
                            method_version=method, generated_by="llm:test", criteria=crit)
    db.add(row)
    db.commit()
    if approve:
        db.add(BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer="test"))
        db.commit()
    return row


LANDLORD_RAW = {
    "audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]},
    "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Duval"], "from": {"kind": "condition", "index": 0}}],
    "excludes": [{"attr": "property_type", "op": "in", "values": ["single_family"], "from": {"kind": "exception", "index": 0}}],
}
# No exclusions, only plain "is one of" tests: tier "simple", so it is served before a person approves it.
SIMPLE_RAW = {
    "audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]},
    "requires": [{"attr": "jurisdiction", "op": "in", "values": ["municipality:Jacksonville"], "from": {"kind": "condition", "index": 0}}],
}  # maps the DISTRICTS item, which has no exceptions


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
    _criteria(db_session, layer, 0, LANDLORD_RAW, approve=True)
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["available"] and body["complete"] is True and body["incomplete_reasons"] == []
    e = body["entries"][0]
    assert e["group"] == "Landlords" and e["reviewed"] is True
    assert e["criteria"]["audience"]["any_of"] == ["landlord"]
    assert e["conditions"][0]["text"] == "Applies in Duval County."
    keys = [q["key"] for q in body["questions"]]
    # A landlord rule is about where the property is, so that is what is asked
    # (not where the landlord lives). No municipality: the bill names none.
    assert keys == ["role", "property_county", "property_type"]
    role = body["questions"][0]
    assert [o["value"] for o in role["options"]] == ["landlord", "none_of_these"] and role["options"][0]["label"] == "Landlord"
    assert role["options"][-1]["label"] == "None of These"  # a renter reading a landlord bill can still answer
    counties = body["questions"][1]["options"]
    assert len(counties) == 67 and "none_of_these" not in [c["value"] for c in counties] and {"value": "Duval", "label": "Duval County"} in counties
    assert [o["value"] for o in body["questions"][2]["options"]] == ["single_family", "none_of_these"]
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
    assert [o["value"] for o in questions["property_municipality"]["options"]] == ["Jacksonville", "none_of_these"]
    assert questions["property_municipality"]["counties"] == {"Jacksonville": ["Duval"]}
    assert "municipality" not in questions
    assert "property_type" not in questions


def test_an_entry_with_no_mapping_makes_the_layer_incomplete(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD, DISTRICTS])
    _criteria(db_session, layer, 0, LANDLORD_RAW, approve=True)
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["complete"] is False
    assert body["incomplete_reasons"] == ["1 of 2 entries have no questions mapped yet."]
    assert body["entries"][1]["criteria"] is None


def test_a_capped_or_unsupported_layer_is_incomplete(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD], scope="Bill text · first 20 of 31 entries")
    _criteria(db_session, layer, 0, LANDLORD_RAW, approve=True)
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["complete"] is False and body["incomplete_reasons"] == ["The analysis lists only the first entries of a longer list."]

    other = bill_factory(bill_number="HB 2")
    weak = _layer(db_session, other, [LANDLORD], state="insufficient_evidence")
    _criteria(db_session, weak, 0, LANDLORD_RAW, approve=True)
    assert "not marked supported" in client.get(f"/bills/{other.id}/impact-lens").json()["incomplete_reasons"][0]


def test_only_the_current_layer_and_current_vocabulary_count(client, db_session, bill_factory):
    entity = bill_factory()
    old = _layer(db_session, entity, [LANDLORD], version=1, superseded=True)
    _criteria(db_session, old, 0, LANDLORD_RAW)
    new = _layer(db_session, entity, [LANDLORD], version=2)
    _criteria(db_session, new, 0, LANDLORD_RAW, vocab=1, method="impact_lens_criteria/1")  # an incompatible, older vocabulary
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    assert body["layer"]["version"] == 2
    assert body["entries"][0]["criteria"] is None and body["complete"] is False  # old-vocabulary rows are ignored


def test_the_newest_mapping_wins_and_review_follows_the_row(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [DISTRICTS])
    first = _criteria(db_session, layer, 0, {}, method="impact_lens_criteria/7")  # nothing mapped
    second = _criteria(db_session, layer, 0, SIMPLE_RAW, method="impact_lens_criteria/8")
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


def test_a_rejected_mapping_is_withheld_and_the_layer_is_incomplete(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    row = _criteria(db_session, layer, 0, LANDLORD_RAW)
    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="rejected", reviewer="joe", note="secret"))
    db_session.commit()
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    e = body["entries"][0]
    assert e["criteria"] is None and e["withdrawn"] is True and e["reviewed"] is False
    assert body["complete"] is False
    assert any("withdrawn after review" in r for r in body["incomplete_reasons"])
    assert not any("no questions mapped" in r for r in body["incomplete_reasons"])
    assert body["questions"] == []  # a withdrawn mapping asks nothing
    assert "joe" not in str(body) and "secret" not in str(body)


def test_rejection_beats_an_earlier_approval(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    row = _criteria(db_session, layer, 0, LANDLORD_RAW)
    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer="joe"))
    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="rejected", reviewer="joe"))
    db_session.commit()
    e = client.get(f"/bills/{entity.id}/impact-lens").json()["entries"][0]
    assert e["criteria"] is None and e["withdrawn"] is True and e["reviewed"] is False


def test_a_remapped_entry_replaces_a_withdrawn_one_and_starts_unreviewed(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [DISTRICTS])
    old = _criteria(db_session, layer, 0, LANDLORD_RAW, method="impact_lens_criteria/7")
    db_session.add(BillLayerCriteriaReview(criteria_id=old.id, decision="rejected", reviewer="joe"))
    db_session.commit()
    _criteria(db_session, layer, 0, SIMPLE_RAW, method="impact_lens_criteria/8")
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    e = body["entries"][0]
    assert e["criteria"] is not None and e["withdrawn"] is False and e["reviewed"] is False
    assert body["complete"] is True


def test_a_rejected_newest_row_does_not_fall_back_to_an_older_row(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    _criteria(db_session, layer, 0, LANDLORD_RAW, method="impact_lens_criteria/7")
    newer = _criteria(db_session, layer, 0, LANDLORD_RAW, method="impact_lens_criteria/8")
    db_session.add(BillLayerCriteriaReview(criteria_id=newer.id, decision="rejected", reviewer="joe"))
    db_session.commit()
    e = client.get(f"/bills/{entity.id}/impact-lens").json()["entries"][0]
    assert e["criteria"] is None and e["withdrawn"] is True


# ---- role-specific locations (docs/IMPACT_LENS_ROLE_LOCATIONS.md) ----------

def test_every_role_has_a_location_kind_and_the_response_sends_the_table(client, bill_factory):
    from app.impact_lens.vocabulary import REGISTRY

    expected = {
        "renter": "residence", "insured": "residence", "local_government": "residence",
        "landlord": "property", "homeowner": "property", "property_developer": "property",
        "employer": "business", "business_owner": "business", "employee": "business",
        "healthcare_provider": "business",
        "flood_insurance_policyholder": "property", "medicare_beneficiary": "residence", "small_employer": "business",
    }
    # A role added to the vocabulary must say which location it regulates.
    assert set(REGISTRY["role"].values) == set(expected)

    entity = bill_factory()  # no Who layer: the table is static, so it is sent anyway
    assert client.get(f"/bills/{entity.id}/impact-lens").json()["role_locations"] == expected


def test_a_landlord_bill_asks_where_the_property_is_not_where_the_reader_lives(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    _criteria(db_session, layer, 0, LANDLORD_RAW, approve=True)  # landlord, requires county:Duval
    questions = {q["key"]: q for q in client.get(f"/bills/{entity.id}/impact-lens").json()["questions"]}
    assert "county" not in questions
    prop = questions["property_county"]
    assert prop["question"] == "In which Florida county is the property?"
    assert len(prop["options"]) == 67 and {"value": "Duval", "label": "Duval County"} in prop["options"]


def _entry(group, role, place):
    name = place.partition(":")[2]  # the mapper keeps a place only if the cited text names it
    return (
        {"group": group, "text": "t", "quote": "q",
         "conditions": [{"text": f"Applies in {name}.", "quote": f"This applies in {name}."}], "exceptions": []},
        {"audience": {"kind": "attr", "attr": "role", "any_of": [role]} if role else {"kind": "anyone"},
         "requires": [{"attr": "jurisdiction", "op": "in", "values": [place], "from": {"kind": "condition", "index": 0}}]},
    )


def _question_keys(client, db_session, bill_factory, *entries):
    entity = bill_factory()
    layer = _layer(db_session, entity, [item for item, _ in entries])
    for i, (_, raw) in enumerate(entries):
        _criteria(db_session, layer, i, raw)
    return [q["key"] for q in client.get(f"/bills/{entity.id}/impact-lens").json()["questions"]]


def test_a_renter_bill_still_asks_where_the_reader_lives(client, db_session, bill_factory):
    keys = _question_keys(client, db_session, bill_factory, _entry("Renters", "renter", "county:Duval"))
    assert keys == ["role", "county"]


def test_an_employee_bill_asks_where_the_workplace_is(client, db_session, bill_factory):
    keys = _question_keys(client, db_session, bill_factory, _entry("Employees", "employee", "municipality:Jacksonville"))
    assert keys == ["role", "business_county", "business_municipality"]


def test_a_bill_with_several_kinds_asks_each_location_once(client, db_session, bill_factory):
    keys = _question_keys(
        client, db_session, bill_factory,
        _entry("Landlords", "landlord", "county:Duval"),
        _entry("Renters", "renter", "county:Duval"),
        _entry("Landlords", "landlord", "county:Broward"),
        _entry("Employers", "employer", "county:Orange"),
    )
    assert keys == ["role", "county", "property_county", "business_county"]


def test_an_anyone_provision_asks_where_the_reader_lives(client, db_session, bill_factory):
    keys = _question_keys(client, db_session, bill_factory, _entry("Anyone", None, "county:Duval"))
    assert keys == ["county"]


def test_a_needs_review_mapping_is_held_until_a_person_approves_it(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [LANDLORD])
    row = _criteria(db_session, layer, 0, LANDLORD_RAW)  # an exclusion makes it needs_review
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    e = body["entries"][0]
    assert e["criteria"] is None and e["held"] is True and e["withdrawn"] is False and e["reviewed"] is False
    assert body["complete"] is False
    assert body["incomplete_reasons"] == ["1 of 1 entries are waiting for a person to review their questions."]
    assert body["questions"] == []  # a held mapping asks nothing

    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer="joe"))
    db_session.commit()
    body = client.get(f"/bills/{entity.id}/impact-lens").json()
    e = body["entries"][0]
    assert e["criteria"] is not None and e["held"] is False and e["reviewed"] is True and body["complete"] is True


def test_a_simple_mapping_is_served_unreviewed_and_a_rejected_held_row_is_withdrawn_not_held(client, db_session, bill_factory):
    entity = bill_factory()
    layer = _layer(db_session, entity, [DISTRICTS, LANDLORD])
    _criteria(db_session, layer, 0, SIMPLE_RAW)
    bad = _criteria(db_session, layer, 1, LANDLORD_RAW)
    db_session.add(BillLayerCriteriaReview(criteria_id=bad.id, decision="rejected", reviewer="joe"))
    db_session.commit()
    entries = client.get(f"/bills/{entity.id}/impact-lens").json()["entries"]
    assert entries[0]["criteria"] is not None and entries[0]["held"] is False and entries[0]["reviewed"] is False
    assert entries[1]["criteria"] is None and entries[1]["withdrawn"] is True and entries[1]["held"] is False
