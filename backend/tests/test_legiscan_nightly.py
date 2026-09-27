"""Nightly LegiScan sync sized for 10,000 calls/month: dataset first, a
per-night call budget, and text refetched only when the document changed."""

import base64
import io
import json
import zipfile

import pytest
from sqlalchemy import select

import app.pipeline.legiscan as legiscan
from app.models import Bill, Entity, SourceCheck


def bill_detail(bill_id, *, doc_id=900, change_hash="h1"):
    return {"bill_id": bill_id, "bill_number": f"H{bill_id:04d}", "title": f"Bill {bill_id}", "status": 1,
            "change_hash": change_hash, "session": {"session_id": 2220, "session_name": "2026 Regular Session"},
            "sponsors": [], "votes": [], "texts": [{"doc_id": doc_id}]}


class FakeApi:
    """Counts calls into legiscan.API_CALLS the way the real client does."""

    def __init__(self, bills, *, dataset_hash="d1", dataset_bills=None):
        self.bills = bills
        self.dataset_hash = dataset_hash
        self.dataset_bills = dataset_bills or {}
        self.calls = []
        self.last_master_session = {}

    def _count(self, op):
        self.calls.append(op)
        legiscan.API_CALLS[op] += 1

    def get_master_list(self, state):
        self._count("getMasterList")
        self.last_master_session = {"session_id": 2220, "session_name": "2026 Regular Session"}
        return [{"bill_id": b, "change_hash": d["change_hash"], "number": d["bill_number"]} for b, d in self.bills.items()]

    def get_bill(self, bill_id):
        self._count("getBill")
        return self.bills[bill_id]

    def _call(self, op, **params):
        self._count(op)
        if op == "getDatasetList":
            return {"datasetlist": [{"session_id": 2220, "session_name": "2026 Regular Session",
                                     "dataset_hash": self.dataset_hash, "access_key": "k"}]}
        if op == "getDataset":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for bill_id, bill in self.dataset_bills.items():
                    z.writestr(f"FL/2026/bill/{bill_id}.json", json.dumps({"bill": bill}))
            return {"dataset": {"zip": base64.b64encode(buf.getvalue()).decode()}}
        raise AssertionError(op)


@pytest.fixture(autouse=True)
def fresh_counter(monkeypatch):
    monkeypatch.setattr(legiscan, "API_CALLS", legiscan.API_CALLS.__class__())


@pytest.fixture
def texts(monkeypatch):
    import app.pipeline.bill_text as bill_text

    fetched = []

    def fake_fetch(client, doc_id):
        legiscan.API_CALLS["getBillText"] += 1
        fetched.append(doc_id)
        return f"text of document {doc_id}"

    monkeypatch.setattr(bill_text, "fetch_bill_text", fake_fetch)
    return fetched


def stored_bill(db, legiscan_id):
    return db.execute(
        select(Entity).where(Entity.external_ids["legiscan_id"].as_string() == str(legiscan_id))
    ).scalar_one()


def test_budget_stops_fetching_and_leaves_the_rest_for_next_night(db_session, texts):
    api = FakeApi({i: bill_detail(i) for i in (1, 2, 3)})

    legiscan.ingest_state_bills(db_session, state="FL", client=api, master_list=api.get_master_list("FL"),
                                max_calls=2)

    assert api.calls.count("getBill") == 2
    assert db_session.execute(select(Bill)).scalars().all().__len__() == 2  # bill 3 waits


def test_text_is_fetched_for_new_bills_and_new_documents_only(db_session, texts):
    api = FakeApi({1: bill_detail(1, doc_id=900)})
    legiscan.ingest_state_bills(db_session, state="FL", client=api, master_list=api.get_master_list("FL"),
                                refresh_text=True)
    assert texts == [900]  # new bill: fetched
    bill = stored_bill(db_session, 1)
    assert bill.external_ids["legiscan_text_doc_id"] == "900"

    # Changed bill, same document: no fetch.
    api.bills[1] = bill_detail(1, doc_id=900, change_hash="h2")
    legiscan.ingest_state_bills(db_session, state="FL", client=api, master_list=api.get_master_list("FL"),
                                refresh_text=True)
    assert texts == [900]

    # New document version: fetched and stored.
    api.bills[1] = bill_detail(1, doc_id=901, change_hash="h3")
    legiscan.ingest_state_bills(db_session, state="FL", client=api, master_list=api.get_master_list("FL"),
                                refresh_text=True)
    assert texts == [900, 901]
    assert stored_bill(db_session, 1).bill.full_text == "text of document 901"


def test_existing_text_without_a_recorded_document_is_not_refetched(db_session, texts):
    api = FakeApi({1: bill_detail(1, doc_id=900)})
    legiscan.ingest_state_bills(db_session, state="FL", client=api, master_list=api.get_master_list("FL"))
    bill = stored_bill(db_session, 1)
    bill.bill.full_text = "re-extracted 2026-09-25"
    bill.external_ids = {k: v for k, v in bill.external_ids.items() if k != "legiscan_text_doc_id"}
    db_session.commit()

    api.bills[1] = bill_detail(1, doc_id=900, change_hash="h2")
    legiscan.ingest_state_bills(db_session, state="FL", client=api, master_list=api.get_master_list("FL"),
                                refresh_text=True)

    assert texts == []
    assert stored_bill(db_session, 1).external_ids["legiscan_text_doc_id"] == "900"


def test_nightly_imports_a_changed_dataset_once_then_only_fetches_later_changes(monkeypatch, db_session, texts):
    detail = {1: bill_detail(1), 2: bill_detail(2)}
    api = FakeApi(dict(detail), dataset_bills=dict(detail))
    monkeypatch.setattr(legiscan, "LegiScanClient", lambda *a, **k: api)

    legiscan.nightly_state_sync(db_session, state="FL")

    # Both bills came from the dataset: no getBill; the texts were fetched once each.
    assert api.calls.count("getDataset") == 1
    assert api.calls.count("getBill") == 0
    assert sorted(texts) == [900, 900]
    marker = db_session.execute(select(SourceCheck).where(SourceCheck.source_key == "legiscan_dataset")).scalar_one()
    assert marker.last_result == "2220:d1"

    # Next night: dataset unchanged, one bill changed since it was built.
    api.calls.clear()
    api.bills[2] = bill_detail(2, change_hash="h2")
    legiscan.nightly_state_sync(db_session, state="FL")

    assert "getDataset" not in api.calls
    assert api.calls.count("getBill") == 1
    assert db_session.execute(select(SourceCheck).where(SourceCheck.source_key == "legiscan")).scalar_one()
