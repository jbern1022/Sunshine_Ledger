from app.models import Claim
from app.pipeline.rhetoric_gap import CLAIM_TYPE
from app.pipeline.rhetoric_gap_batch import select_bills_needing_rhetoric_gap_check


def test_skips_bills_without_full_text(db_session, bill_factory):
    bill_factory()  # bill_factory doesn't set full_text
    candidates = select_bills_needing_rhetoric_gap_check(db_session)
    assert candidates == []


def test_selects_a_bill_with_full_text_and_no_existing_claim(db_session, bill_factory):
    entity = bill_factory()
    entity.bill.full_text = "Full text."
    db_session.commit()

    candidates = select_bills_needing_rhetoric_gap_check(db_session)
    assert [c.id for c in candidates] == [entity.id]


def test_skips_a_bill_that_already_has_a_rhetoric_gap_claim(db_session, bill_factory):
    entity = bill_factory()
    entity.bill.full_text = "Full text."
    db_session.add(Claim(bill_entity_id=entity.id, claim_type=CLAIM_TYPE, claim_text="x", generated_by="llm:x"))
    db_session.commit()

    candidates = select_bills_needing_rhetoric_gap_check(db_session)
    assert candidates == []


def test_does_not_skip_a_bill_whose_only_claims_are_a_different_type(db_session, bill_factory):
    entity = bill_factory()
    entity.bill.full_text = "Full text."
    db_session.add(Claim(bill_entity_id=entity.id, claim_type="what_it_does", claim_text="x", generated_by="llm:x"))
    db_session.commit()

    candidates = select_bills_needing_rhetoric_gap_check(db_session)
    assert [c.id for c in candidates] == [entity.id]


def test_limit_caps_candidates(db_session, bill_factory):
    for i in range(3):
        entity = bill_factory(bill_number=f"HB {i}")
        entity.bill.full_text = "Full text."
    db_session.commit()

    candidates = select_bills_needing_rhetoric_gap_check(db_session, limit=2)
    assert len(candidates) == 2
