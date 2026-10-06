import pytest
from sqlalchemy.exc import IntegrityError

from app.impact_lens.criteria import validate_criteria
from app.models import BillLayer, BillLayerCriteria, BillLayerCriteriaReview


def _who_layer(entity):
    return BillLayer(
        bill_entity_id=entity.id, layer="who_it_affects", origin="sunshine_ledger_ai", version=1,
        evidence_state="supported", scope_note="Bill text", items=[{"group": "Landlords", "conditions": [], "exceptions": []}],
        generated_by="llm:test", method_version="who_it_affects/sunshine_ledger_ai/11", input_hash="h1",
    )


def _criteria(layer, **kw):
    crit = validate_criteria({"audience": {"kind": "attr", "attr": "role", "any_of": ["landlord"]}},
                             entry_index=0, n_conditions=0, n_exceptions=0)
    defaults = dict(bill_layer_id=layer.id, entry_index=0, vocabulary_version=1,
                    method_version="criteria/1", generated_by="llm:test", criteria=crit)
    defaults.update(kw)
    return BillLayerCriteria(**defaults)


def test_criteria_round_trip_and_remap_is_a_new_row(db_session, bill_factory):
    layer = _who_layer(bill_factory())
    db_session.add(layer)
    db_session.commit()
    first = _criteria(layer)
    db_session.add(first)
    db_session.commit()
    db_session.refresh(first)
    assert first.criteria["audience"]["any_of"] == ["landlord"]
    # A new vocabulary version maps the same entry again: a second row, not an edit.
    db_session.add(_criteria(layer, vocabulary_version=2))
    db_session.commit()
    assert db_session.query(BillLayerCriteria).filter_by(bill_layer_id=layer.id).count() == 2


def test_the_same_mapping_cannot_be_stored_twice(db_session, bill_factory):
    layer = _who_layer(bill_factory())
    db_session.add(layer)
    db_session.commit()
    db_session.add(_criteria(layer))
    db_session.commit()
    db_session.add(_criteria(layer))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_approval_per_criteria_row_and_rejections_are_kept(db_session, bill_factory):
    layer = _who_layer(bill_factory())
    db_session.add(layer)
    db_session.commit()
    row = _criteria(layer)
    db_session.add(row)
    db_session.commit()
    db_session.add_all([
        BillLayerCriteriaReview(criteria_id=row.id, decision="rejected", reviewer="joe", note="wrong county"),
        BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer="joe"),
    ])
    db_session.commit()
    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="approved", reviewer="joe"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_unknown_review_decision_is_rejected(db_session, bill_factory):
    layer = _who_layer(bill_factory())
    db_session.add(layer)
    db_session.commit()
    row = _criteria(layer)
    db_session.add(row)
    db_session.commit()
    db_session.add(BillLayerCriteriaReview(criteria_id=row.id, decision="maybe", reviewer="joe"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_the_layer_removes_its_criteria(db_session, bill_factory):
    layer = _who_layer(bill_factory())
    db_session.add(layer)
    db_session.commit()
    db_session.add(_criteria(layer))
    db_session.commit()
    db_session.delete(layer)
    db_session.commit()
    assert db_session.query(BillLayerCriteria).count() == 0
