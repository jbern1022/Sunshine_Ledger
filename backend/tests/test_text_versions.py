"""Filed-version backfill: only amended bills, only what isn't stored, within a call cap."""

import pytest
from sqlalchemy import select

import app.pipeline.legiscan as legiscan
from app.models import BillTextVersion, Entity
from app.pipeline.text_versions import backfill_filed_versions, filed_versions_to_fetch


@pytest.fixture(autouse=True)
def fresh_counter(monkeypatch):
    monkeypatch.setattr(legiscan, "API_CALLS", legiscan.API_CALLS.__class__())


@pytest.fixture
def fetch(monkeypatch):
    import app.pipeline.bill_text as bill_text

    fetched = []

    def fake(client, doc_id):
        legiscan.API_CALLS["getBillText"] += 1
        fetched.append(doc_id)
        return f"filed text {doc_id}"

    monkeypatch.setattr(bill_text, "fetch_bill_text", fake)
    return fetched


def _bill(db, legiscan_id):
    e = Entity(entity_type="bill", name=f"Bill {legiscan_id}", jurisdiction_level="state", jurisdiction_name="FL",
               external_ids={"legiscan_id": str(legiscan_id)}, attributes={})
    db.add(e)
    db.flush()
    return e


BILLS = {
    1: {"texts": [{"doc_id": 101, "type": "Introduced", "date": "2026-01-09"}, {"doc_id": 102, "type": "Enrolled"}]},
    2: {"texts": [{"doc_id": 201, "type": "Introduced"}]},  # never amended: nothing to compare
    3: {"texts": [{"doc_id": 301, "type": "Introduced"}, {"doc_id": 302}, {"doc_id": 303}]},
    9: {"texts": [{"doc_id": 901}, {"doc_id": 902}]},  # not in our database
}


def test_only_amended_stored_bills_are_fetched(db_session):
    for i in (1, 2, 3):
        _bill(db_session, i)
    db_session.commit()
    assert [first["doc_id"] for _, first in filed_versions_to_fetch(db_session, BILLS)] == [101, 301]


def test_stores_the_filed_version_and_skips_it_next_time(db_session, fetch):
    bill = _bill(db_session, 1)
    db_session.commit()

    assert backfill_filed_versions(db_session, BILLS, client=None, max_calls=10) == (1, 0, 0)
    row = db_session.execute(select(BillTextVersion)).scalar_one()
    assert (row.bill_entity_id, row.legiscan_doc_id, row.version_type, str(row.version_date), row.text) == (
        bill.id, 101, "Introduced", "2026-01-09", "filed text 101")

    assert backfill_filed_versions(db_session, BILLS, client=None, max_calls=10) == (0, 0, 0)
    assert fetch == [101]


def test_stops_at_the_call_cap(db_session, fetch):
    for i in (1, 3):
        _bill(db_session, i)
    db_session.commit()

    assert backfill_filed_versions(db_session, BILLS, client=None, max_calls=1) == (1, 0, 1)
    assert fetch == [101]


def test_latest_text_fills_missing_text_passed_bills_first(db_session, fetch):
    from app.models import Bill
    from app.pipeline.text_versions import backfill_latest_text

    def with_bill(legiscan_id, full_text=None):
        e = _bill(db_session, legiscan_id)
        db_session.add(Bill(entity_id=e.id, bill_number=f"H{legiscan_id}", session="2025 Regular Session",
                            status="Introduced", source_system="legiscan", geo_scope_names=["FL"],
                            full_text=full_text))
        db_session.flush()
        return e

    died, passed, has_text = with_bill(1), with_bill(3), with_bill(9, full_text="already here")
    db_session.commit()
    bills = {
        1: {"status": 1, "texts": [{"doc_id": 101}, {"doc_id": 102}]},
        3: {"status": 4, "texts": [{"doc_id": 301}, {"doc_id": 303}]},
        9: {"status": 4, "texts": [{"doc_id": 901}]},
    }

    assert backfill_latest_text(db_session, bills, client=None, max_calls=1) == (1, 0, 1)
    assert fetch == [303]  # the passed bill, its latest version
    assert passed.bill.full_text == "filed text 303"
    assert passed.external_ids["legiscan_text_doc_id"] == "303"

    backfill_latest_text(db_session, bills, client=None, max_calls=10)
    assert fetch == [303, 102]  # the bill that already had text was skipped
    assert has_text.bill.full_text == "already here"
