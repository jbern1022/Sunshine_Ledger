from datetime import datetime, timezone

import pytest

from app.models import BillLayer, Source
from app.pipeline.bill_layers import LayerResult
from app.pipeline.bill_layers_store import current_layer, layer_input_hash, store_layer_version


def _src():
    return Source(url="https://example.com/bill", source_type="legiscan_bill_text", retrieved_at=datetime.now(timezone.utc))


def _result(text="Removes the requirement."):
    return LayerResult("supported", "Bill text", [{"text": text, "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}])


def _store(db, entity, h, text="Removes the requirement."):
    return store_layer_version(
        db, bill_entity_id=entity.id, layer="interpretation", origin="sunshine_ledger_ai",
        result=_result(text), input_hash=h, generated_by="llm:test", sources=[_src()],
    )


def test_hash_depends_on_every_input():
    base = layer_input_hash("interpretation", "sunshine_ledger_ai", "text", "m1")
    assert base != layer_input_hash("interpretation", "sunshine_ledger_ai", "text2", "m1")
    assert base != layer_input_hash("interpretation", "sunshine_ledger_ai", "text", "m2")
    assert base != layer_input_hash("interpretation", "legislative_staff", "text", "m1")


def test_first_store_creates_version_1_with_sources(db_session, bill_factory):
    entity = bill_factory()
    row = _store(db_session, entity, "h1")
    assert row.version == 1 and row.superseded_at is None
    assert row.method_version == "interpretation/sunshine_ledger_ai/2"
    assert len(row.source_links) == 1


def test_unchanged_input_writes_nothing(db_session, bill_factory):
    entity = bill_factory()
    _store(db_session, entity, "h1")
    assert _store(db_session, entity, "h1") is None
    assert db_session.query(BillLayer).count() == 1


def test_changed_input_supersedes_and_preserves_old_text(db_session, bill_factory):
    entity = bill_factory()
    v1 = _store(db_session, entity, "h1", text="Old reading.")
    v2 = _store(db_session, entity, "h2", text="New reading.")
    db_session.refresh(v1)
    assert v2.version == 2 and v2.superseded_at is None
    assert v1.superseded_at is not None
    assert v1.items[0]["text"] == "Old reading."
    assert current_layer(db_session, entity.id, "interpretation", "sunshine_ledger_ai").id == v2.id


def test_disallowed_pair_raises(db_session, bill_factory):
    entity = bill_factory()
    with pytest.raises(ValueError):
        store_layer_version(
            db_session, bill_entity_id=entity.id, layer="bill_says", origin="legislative_staff",
            result=_result(), input_hash="h", generated_by="llm:test", sources=[],
        )
