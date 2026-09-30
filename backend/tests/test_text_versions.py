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


def test_staff_analyses_passed_bills_first_within_the_cap(db_session, monkeypatch):
    import app.pipeline.staff_analysis as staff_analysis
    from app.models import StaffAnalysis
    from app.pipeline.text_versions import backfill_staff_analyses, staff_analyses_to_fetch

    fetched = []

    def fake_store(db, client, *, entity, supplements, known_ids, fallback=True):
        from app.pipeline.bill_text import NeedsLegiScan

        if not fallback:  # no state_link here, so only LegiScan could serve it
            raise NeedsLegiScan(supplements[0]["supplement_id"])
        for supp in supplements:
            legiscan.API_CALLS["getSupplement"] += 1
            fetched.append(supp["supplement_id"])
            db.add(StaffAnalysis(entity_id=entity.id, legiscan_supplement_id=supp["supplement_id"],
                                  source_url="https://example.test", text="t"))
            known_ids.add(supp["supplement_id"])
        db.commit()
        return len(supplements), 0

    monkeypatch.setattr(staff_analysis, "store_new_staff_analyses", fake_store)
    died, passed = _bill(db_session, 1), _bill(db_session, 3)
    db_session.commit()
    analysis = {"title": "Analysis"}
    bills = {
        1: {"status": 1, "supplements": [{**analysis, "supplement_id": 11}, {"title": "Vote", "supplement_id": 12}]},
        3: {"status": 4, "supplements": [{**analysis, "supplement_id": 31}, {**analysis, "supplement_id": 32}]},
        9: {"status": 4, "supplements": [{**analysis, "supplement_id": 91}]},  # not in our database
    }

    assert [s["supplement_id"] for _, s in staff_analyses_to_fetch(db_session, bills)] == [31, 32, 11]
    assert backfill_staff_analyses(db_session, bills, client=None, max_calls=2) == (2, 0, 1)
    assert fetched == [31, 32]
    assert backfill_staff_analyses(db_session, bills, client=None, max_calls=10) == (1, 0, 0)
    assert fetched == [31, 32, 11]


def test_superseded_house_analysis_drafts_are_skipped(db_session):
    from app.pipeline.text_versions import staff_analyses_to_fetch

    _bill(db_session, 1)
    db_session.commit()
    base = "https://www.flsenate.gov/Session/Bill/2024/117/Analyses/"
    names = ["h0117a.CRJ.PDF", "h0117b.EEG.PDF", "h0117c.EEG.PDF", "h0117d.JDC.PDF",
             "h0117e.JDC.PDF", "h0117z.CRJ.PDF", "h0117z1.CRJ.PDF"]
    supplements = [{"title": "Analysis", "supplement_id": i, "state_link": base + n} for i, n in enumerate(names, 1)]
    supplements.append({"title": "Analysis", "supplement_id": 99,
                        "state_link": "https://www.flsenate.gov/Session/Bill/2024/117/Analyses/2024s00117.pre.cj.PDF"})
    bills = {1: {"status": 4, "supplements": supplements}}

    kept = [s["state_link"].rsplit("/", 1)[1] for _, s in staff_analyses_to_fetch(db_session, bills)]
    # Only the latest revision per committee is still published; Senate names aren't touched.
    assert kept == ["h0117c.EEG.PDF", "h0117e.JDC.PDF", "h0117z1.CRJ.PDF", "2024s00117.pre.cj.PDF"]


def test_version_meta_labels_stored_texts_without_fetching(db_session):
    from app.pipeline.text_versions import record_version_meta

    bill = _bill(db_session, 1)
    bill.external_ids = {**bill.external_ids, "legiscan_text_doc_id": "103"}
    db_session.add(BillTextVersion(bill_entity_id=bill.id, legiscan_doc_id=101, version_type="Introduced", text="x"))
    other = _bill(db_session, 2)  # stored doc id no longer in the dataset: left alone
    other.external_ids = {**other.external_ids, "legiscan_text_doc_id": "999"}
    db_session.commit()
    bills = {
        1: {"texts": [{"doc_id": 101, "type": "Introduced", "date": "2026-01-09", "state_link": "https://fl/filed"},
                      {"doc_id": 103, "type": "Enrolled", "date": "2026-03-13", "state_link": "https://fl/er"}]},
        2: {"texts": [{"doc_id": 201, "type": "Introduced"}]},
    }

    assert record_version_meta(db_session, bills) == 1
    assert bill.external_ids["text_version"] == {"type": "Enrolled", "date": "2026-03-13", "url": "https://fl/er"}
    assert bill.external_ids["filed_text_url"] == "https://fl/filed"
    assert "text_version" not in other.external_ids
    assert record_version_meta(db_session, bills) == 0  # nothing new
