import pytest
from sqlalchemy.exc import IntegrityError

from app.models import BillLayer, BillLayerReview


def _layer(entity, **kw):
    defaults = dict(
        bill_entity_id=entity.id,
        layer="interpretation",
        origin="sunshine_ledger_ai",
        version=1,
        evidence_state="supported",
        scope_note="Bill text",
        items=[{"text": "t", "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test",
        method_version="interpretation/sunshine_ledger_ai/1",
        input_hash="h1",
    )
    defaults.update(kw)
    return BillLayer(**defaults)


def test_layer_round_trips(db_session, bill_factory):
    entity = bill_factory()
    row = _layer(entity)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.superseded_at is None
    assert row.items[0]["section_ref"] == "Section 1"


def test_only_one_current_row_per_bill_layer_origin(db_session, bill_factory):
    entity = bill_factory()
    db_session.add(_layer(entity, version=1))
    db_session.commit()
    db_session.add(_layer(entity, version=2, input_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_disallowed_layer_origin_pair_rejected(db_session, bill_factory):
    entity = bill_factory()
    db_session.add(_layer(entity, layer="bill_says", origin="sunshine_ledger_ai"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_review_row_links_to_layer(db_session, bill_factory):
    entity = bill_factory()
    row = _layer(entity)
    db_session.add(row)
    db_session.commit()
    db_session.add(BillLayerReview(bill_layer_id=row.id, decision="approved", reviewer="admin"))
    db_session.commit()
    db_session.refresh(row)
    assert [r.decision for r in row.reviews] == ["approved"]
