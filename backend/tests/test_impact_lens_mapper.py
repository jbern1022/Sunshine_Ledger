import json

import pytest

from app.impact_lens import mapper
from app.impact_lens.criteria import is_fully_mapped
from app.models import BillLayer, BillLayerCriteria

ENTRY = {
    "group": "Landlords",
    "change": "Landlords must offer a 12-month lease renewal.",
    "change_kind": "obligation",
    "quote": "A landlord of a covered rental property shall offer a renewal term of at least 12 months.",
    "conditions": [{"text": "Applies in Duval and Miami-Dade counties.", "quote": "This section applies in Duval County and Miami-Dade County."}],
    "exceptions": [{"text": "Not single-family homes rented by their owner.", "quote": "This section does not apply to a single-family home rented by its owner."}],
}
GOOD_ANSWER = {
    "audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]},
    "requires": [{"attr": "jurisdiction", "op": "in", "values": ["county:Duval", "county:Miami-Dade"], "from": {"kind": "condition", "index": 0}}],
    "excludes": [{"attr": "property_type", "op": "in", "values": ["single_family"], "from": {"kind": "exception", "index": 0}}],
    "unmapped": [], "ambiguous": None,
}


class FakeClient:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def generate(self, prompt, *, json_mode=False):
        assert json_mode
        self.prompts.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


def test_prompt_shows_the_entry_numbered_items_and_names_found_in_the_text():
    p = mapper.build_prompt(ENTRY)
    assert "Landlords" in p and '0. Applies in Duval and Miami-Dade counties.' in p
    assert "county:Duval" in p and "county:Miami-Dade" in p
    assert "renter, landlord" in p and "single_family" in p
    assert "municipality:" in p  # the format is explained


def test_names_found_are_whole_words_only():
    assert mapper.names_in("the Bay area") == ["county:Bay"]
    assert mapper.names_in("a Bayonet and Baylor") == []
    assert "municipality:Jacksonville" in mapper.names_in("within Jacksonville")


def test_a_good_answer_becomes_validated_criteria():
    out = mapper.map_entry(ENTRY, 3, FakeClient(GOOD_ANSWER))
    assert out["entry_index"] == 3 and is_fully_mapped(out)
    assert out["requires"][0]["from"] == {"kind": "condition", "index": 0}


def test_a_bad_answer_is_stored_as_unmapped_not_trusted():
    bad = {**GOOD_ANSWER, "requires": [{"attr": "jurisdiction", "op": "in", "values": ["Duval"], "from": {"kind": "condition", "index": 0}}]}
    out = mapper.map_entry(ENTRY, 0, FakeClient(bad))
    assert out["requires"] == [] and out["unmapped"][0]["kind"] == "condition"
    assert not is_fully_mapped(out)


@pytest.mark.parametrize("answer", ["not json", "[1, 2]", '"text"', RuntimeError("connection refused")])
def test_a_failed_model_call_raises_instead_of_storing_anything(answer):
    with pytest.raises(mapper.MapperError):
        mapper.map_entry(ENTRY, 0, FakeClient(answer))


def _who_layer(entity, items):
    return BillLayer(
        bill_entity_id=entity.id, layer="who_it_affects", origin="sunshine_ledger_ai", version=1,
        evidence_state="supported", scope_note="Bill text", items=items,
        generated_by="llm:test", method_version="who_it_affects/sunshine_ledger_ai/11", input_hash="h1",
    )


def test_map_layer_stores_each_entry_once_and_skips_on_rerun(db_session, bill_factory):
    layer = _who_layer(bill_factory(), [ENTRY, {**ENTRY, "group": "Anyone", "conditions": [], "exceptions": []}])
    db_session.add(layer)
    db_session.commit()
    client = FakeClient(GOOD_ANSWER)
    assert mapper.map_layer(db_session, layer, client, generated_by="llm:test") == (2, 0, 0)
    assert len(client.prompts) == 2
    assert mapper.map_layer(db_session, layer, client, generated_by="llm:test") == (0, 2, 0)
    assert len(client.prompts) == 2  # no model calls the second time
    rows = db_session.query(BillLayerCriteria).filter_by(bill_layer_id=layer.id).order_by(BillLayerCriteria.entry_index).all()
    assert [r.entry_index for r in rows] == [0, 1]
    assert rows[0].method_version == mapper.METHOD_VERSION


def test_a_failed_entry_is_counted_and_can_be_retried(db_session, bill_factory):
    layer = _who_layer(bill_factory(), [ENTRY])
    db_session.add(layer)
    db_session.commit()
    assert mapper.map_layer(db_session, layer, FakeClient("oops"), generated_by="llm:test") == (0, 0, 1)
    assert db_session.query(BillLayerCriteria).count() == 0
    assert mapper.map_layer(db_session, layer, FakeClient(GOOD_ANSWER), generated_by="llm:test") == (1, 0, 0)


def test_only_who_layers_have_criteria(db_session, bill_factory):
    layer = _who_layer(bill_factory(), [ENTRY])
    layer.layer, layer.origin = "interpretation", "sunshine_ledger_ai"
    with pytest.raises(ValueError):
        mapper.map_layer(db_session, layer, FakeClient(GOOD_ANSWER), generated_by="x")


def test_export_sheet_lists_each_entry_with_a_verdict_line(db_session, bill_factory):
    from app.impact_lens import map_batch

    bill = bill_factory(bill_number="HB 1389")
    layer = _who_layer(bill, [ENTRY, {**ENTRY, "group": "Tenants"}])
    db_session.add(layer)
    db_session.commit()
    mapper.map_layer(db_session, layer, FakeClient(GOOD_ANSWER), generated_by="llm:test")
    # Entry 1 is left unmapped to show the "not mapped yet" case.
    db_session.query(BillLayerCriteria).filter_by(entry_index=1).delete()
    db_session.commit()

    pairs = map_batch.current_who_layers(db_session, ["HB 1389", "HB 9999"])
    assert [b.bill_number for b, _ in pairs] == ["HB 1389"]
    sheet = map_batch.export_sheet(db_session, pairs)
    assert "### Entry 0: Landlords" in sheet and "Duval County, Miami-Dade County" in sheet
    assert "role in ['landlord']" in sheet and "(from condition 0)" in sheet
    assert "**Review tier:** needs_review" in sheet  # it has an exclusion
    assert sheet.count("**Verdict:**") == 1
    assert "### Entry 1: Tenants" in sheet and "Not mapped yet" in sheet


def test_the_prompt_has_no_placeholder_the_model_could_copy():
    p = mapper.build_prompt(ENTRY)
    assert "<Name>" not in p and 'for example "county:Duval"' in p


class FlakyClient:
    """Returns the given answers in order, one per call."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def generate(self, prompt, *, json_mode=False):
        self.calls += 1
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def test_one_bad_answer_is_retried_and_a_second_succeeds():
    client = FlakyClient('{"audience": {"kind": "attr", "attr": "role", "any_of": ["lan', json.dumps(GOOD_ANSWER))
    out = mapper.map_entry(ENTRY, 0, client)
    assert client.calls == 2 and out["audience"]["any_of"] == ["landlord"]


def test_two_bad_answers_fail_with_the_reason_and_it_is_logged(caplog):
    client = FlakyClient('{"audience": {"kind": "attr", "attr": "ro')
    with pytest.raises(mapper.MapperError) as err:
        mapper.map_entry(ENTRY, 7, client)
    assert client.calls == mapper.MAX_ATTEMPTS
    assert "invalid JSON" in str(err.value) and "entry 7" in str(err.value) and "starts" in str(err.value)


def test_a_connection_error_is_not_retried():
    client = FakeClient(RuntimeError("connection refused"))
    with pytest.raises(mapper.MapperError):
        mapper.map_entry(ENTRY, 0, client)
    assert len(client.prompts) == 1


def test_map_layer_logs_why_an_entry_failed(db_session, bill_factory, caplog):
    layer = _who_layer(bill_factory(), [ENTRY])
    db_session.add(layer)
    db_session.commit()
    with caplog.at_level("WARNING"):
        assert mapper.map_layer(db_session, layer, FlakyClient("nope"), generated_by="x") == (0, 0, 1)
    assert "entry 0 not mapped" in caplog.text and "invalid JSON" in caplog.text


LONG = "This subsection does not apply to: " + "Airport-impacted areas and other places. " * 12


def test_items_the_guards_would_refuse_are_not_shown_to_the_model():
    entry = {**ENTRY, "exceptions": [{"text": LONG, "quote": LONG}, ENTRY["exceptions"][0]]}
    p = mapper.build_prompt(entry)
    assert "0. (not shown: too long or compound to map. Leave it out.)" in p
    assert "Airport-impacted areas" not in p
    assert "1. Not single-family homes rented by their owner." in p  # the plain one stays
    assert len(p) < 3000


def test_an_unaddressed_long_item_gets_the_real_reason():
    entry = {**ENTRY, "exceptions": [{"text": LONG, "quote": LONG}]}
    out = mapper.map_entry(entry, 0, FakeClient({"audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]}}))
    assert {"kind": "exception", "index": 0, "reason": "It is too long or compound to map exactly"} in out["unmapped"]
