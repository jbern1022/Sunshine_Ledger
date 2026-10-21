from app.impact_lens import review
from app.impact_lens.mapper import map_layer
from app.models import BillLayerCriteriaReview
from tests.test_impact_lens_mapper import ENTRY, GOOD_ANSWER, FakeClient, _who_layer


def _mapped_layer(db_session, bill_factory, items):
    layer = _who_layer(bill_factory(), items)
    db_session.add(layer)
    db_session.commit()
    map_layer(db_session, layer, FakeClient(GOOD_ANSWER), generated_by="llm:test")
    return layer


def test_approve_records_once_and_is_a_no_op_the_second_time(db_session, bill_factory):
    layer = _mapped_layer(db_session, bill_factory, [ENTRY])
    row = review.criteria_rows(db_session, layer)[0]
    assert not review.is_approved(row)

    assert review.approve(db_session, row, reviewer="joe", note="checked") is True
    db_session.refresh(row)
    assert review.is_approved(row)
    assert review.approve(db_session, row, reviewer="joe") is False
    assert db_session.query(BillLayerCriteriaReview).filter_by(criteria_id=row.id).count() == 1


def test_describe_lists_tier_and_approval_per_entry_and_marks_unmapped(db_session, bill_factory):
    layer = _who_layer(bill_factory(), [ENTRY, {**ENTRY, "group": "Renters"}])
    db_session.add(layer)
    db_session.commit()
    # Map only entry 0; entry 1 stays unmapped.
    from app.impact_lens.mapper import map_entry
    from app.models import BillLayerCriteria
    from app.impact_lens.mapper import METHOD_VERSION
    from app.impact_lens.vocabulary import VOCABULARY_VERSION

    db_session.add(BillLayerCriteria(
        bill_layer_id=layer.id, entry_index=0, vocabulary_version=VOCABULARY_VERSION, method_version=METHOD_VERSION,
        generated_by="llm:test", criteria=map_entry(ENTRY, 0, FakeClient(GOOD_ANSWER)),
    ))
    db_session.commit()

    from app.models import Bill
    bill = db_session.get(Bill, layer.bill_entity_id)
    lines = review.describe(bill, layer, review.criteria_rows(db_session, layer))
    assert "2 entries, 1 mapped" in lines[0]
    assert "needs_review" in lines[1] and "not approved" in lines[1]  # an exclusion makes it need review
    assert "not mapped" in lines[2]
