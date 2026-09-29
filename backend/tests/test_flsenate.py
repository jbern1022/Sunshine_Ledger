"""flsenate.gov documents: real documents only, politely spaced, LegiScan as
the fallback, and a budget that leaves the rest for the next run."""

import httpx
import pytest

import app.pipeline.legiscan as legiscan
from app.pipeline import flsenate

PDF = b"%PDF-1.7 fake"
SOFT_404 = b"<html><h1 class=\"print\">The Florida Senate</h1> File not found for this bill. </html>"
BASE = "https://www.flsenate.gov/Session/Bill/2026/1389"


@pytest.fixture(autouse=True)
def fresh_counter(monkeypatch):
    monkeypatch.setattr(legiscan, "API_CALLS", legiscan.API_CALLS.__class__())


@pytest.fixture
def site(monkeypatch):
    """Serve `pages` {url: (content type, body)}; everything else soft-404s."""
    pages: dict[str, tuple[str, bytes]] = {}
    requested: list[str] = []

    def handler(request):
        requested.append(str(request.url))
        content_type, body = pages.get(str(request.url), ("text/html; charset=utf-8", SOFT_404))
        return httpx.Response(200, headers={"content-type": content_type}, content=body)

    monkeypatch.setattr(flsenate, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    return pages, requested


def test_returns_pdfs_and_html_documents(site):
    pages, _ = site
    pages[f"{BASE}/BillText/Filed/PDF"] = ("application/pdf", PDF)
    pages[f"{BASE}/BillText/er/HTML"] = ("text/html; charset=utf-8", b"<html><span class=Insert>x</span></html>")

    assert flsenate.fetch_document(f"{BASE}/BillText/Filed/PDF") == (PDF, "pdf")
    assert flsenate.fetch_document(f"{BASE}/BillText/er/HTML")[1] == "html"
    assert flsenate.FETCHES["fetched"] == 2


def test_rejects_the_soft_404_and_other_hosts(site):
    with pytest.raises(flsenate.NotADocument):
        flsenate.fetch_document(f"{BASE}/BillText/Filed/HTML")  # House bills have no HTML version
    with pytest.raises(flsenate.NotADocument):
        flsenate.fetch_document("https://legiscan.com/FL/text/H1389/2026")
    assert flsenate.FETCHES["failed"] == 1  # the other host was never requested
    assert len(site[1]) == 1


def test_spaces_requests_by_the_crawl_delay(site, monkeypatch):
    now = [100.0]
    slept = []
    monkeypatch.setattr(flsenate, "_clock", lambda: now[0])
    monkeypatch.setattr(flsenate, "_sleep", lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    site[0][f"{BASE}/a"] = ("application/pdf", PDF)

    flsenate.fetch_document(f"{BASE}/a")
    now[0] += 3
    flsenate.fetch_document(f"{BASE}/a")
    assert slept == [7.0]


def test_budget_stops_the_run(site):
    site[0][f"{BASE}/a"] = ("application/pdf", PDF)
    flsenate.set_budget(1)
    flsenate.fetch_document(f"{BASE}/a")
    with pytest.raises(flsenate.BudgetExhausted):
        flsenate.fetch_document(f"{BASE}/a")
    assert len(site[1]) == 1


def test_bill_text_prefers_flsenate_and_falls_back_to_legiscan(site, monkeypatch):
    import app.pipeline.bill_text as bill_text

    site[0][f"{BASE}/BillText/Filed/PDF"] = ("application/pdf", PDF)
    monkeypatch.setattr(bill_text, "extract_pdf_text", lambda raw: f"text of {raw[:4].decode()}")
    legiscan_docs = []
    monkeypatch.setattr(bill_text, "fetch_bill_text", lambda client, doc_id: legiscan_docs.append(doc_id) or "legiscan")

    assert bill_text.fetch_text_document(None, {"doc_id": 1, "state_link": f"{BASE}/BillText/Filed/PDF"}) == "text of %PDF"
    assert bill_text.fetch_text_document(None, {"doc_id": 2, "state_link": f"{BASE}/BillText/Filed/HTML"}) == "legiscan"
    assert bill_text.fetch_text_document(None, {"doc_id": 3}) == "legiscan"
    assert legiscan_docs == [2, 3]
    with pytest.raises(bill_text.NeedsLegiScan):
        bill_text.fetch_text_document(None, {"doc_id": 4, "state_link": f"{BASE}/x"}, fallback=False)


def _state_bill(db, legiscan_id, **external):
    from app.models import Bill, Entity

    e = Entity(entity_type="bill", name=f"Bill {legiscan_id}", jurisdiction_level="state", jurisdiction_name="FL",
               external_ids={"legiscan_id": str(legiscan_id), **external}, attributes={})
    db.add(e)
    db.flush()
    db.add(Bill(entity_id=e.id, bill_number=f"H{legiscan_id}", session="2025 Regular Session", status="Introduced",
                source_system="legiscan", geo_scope_names=["FL"]))
    db.flush()
    return e


def test_latest_text_backfill_needs_no_legiscan_calls(db_session, site, monkeypatch):
    import app.pipeline.bill_text as bill_text
    from app.pipeline.text_versions import backfill_latest_text

    site[0][f"{BASE}/ok/PDF"] = ("application/pdf", PDF)
    monkeypatch.setattr(bill_text, "extract_pdf_text", lambda raw: "from flsenate")
    ok, missing = _state_bill(db_session, 1), _state_bill(db_session, 2)
    db_session.commit()
    bills = {
        1: {"status": 4, "texts": [{"doc_id": 11, "state_link": f"{BASE}/ok/PDF"}]},
        2: {"status": 1, "texts": [{"doc_id": 21, "state_link": f"{BASE}/gone/PDF"}]},
    }

    assert backfill_latest_text(db_session, bills, client=None, max_calls=0) == (1, 0, 1)
    assert ok.bill.full_text == "from flsenate"
    assert ok.external_ids["legiscan_text_doc_id"] == "11"
    assert missing.bill.full_text is None  # waits for a run that may use LegiScan
    assert sum(legiscan.API_CALLS.values()) == 0


def test_staff_analysis_from_flsenate(db_session, site, monkeypatch):
    from sqlalchemy import select

    import app.pipeline.staff_analysis as staff_analysis
    from app.models import StaffAnalysis

    site[0][f"{BASE}/Analyses/h1389.HSS.PDF"] = ("application/pdf", PDF)
    monkeypatch.setattr(staff_analysis, "extract_analysis_pdf_text", lambda raw: "analysis text")
    bill = _state_bill(db_session, 1)
    db_session.commit()

    class NoLegiScan:
        def get_supplement(self, supplement_id):
            raise AssertionError("LegiScan should not be called")

    supp = {"title": "Analysis", "supplement_id": 7, "state_link": f"{BASE}/Analyses/h1389.HSS.PDF"}
    assert staff_analysis.store_new_staff_analyses(
        db_session, NoLegiScan(), entity=bill, supplements=[supp], known_ids=set()
    ) == (1, 0)
    assert db_session.execute(select(StaffAnalysis.text)).scalar_one() == "analysis text"


def test_nightly_text_refresh_waits_when_the_budget_is_spent(db_session, site):
    from app.pipeline.legiscan import _refresh_bill_text

    bill = _state_bill(db_session, 1, legiscan_text_doc_id="10")
    flsenate.set_budget(0)
    _refresh_bill_text(bill, bill.bill, {"texts": [{"doc_id": 11, "state_link": f"{BASE}/new/PDF"}]}, client=None)
    assert bill.external_ids["legiscan_text_doc_id"] == "10"  # refetched next night


def test_amendment_links_are_recorded_and_used(db_session, site, monkeypatch):
    import app.pipeline.amendments as amendments
    from app.pipeline.text_versions import backfill_amendment_texts

    link = f"{BASE}/Amendment/208403/PDF"
    site[0][link] = ("application/pdf", PDF)
    monkeypatch.setattr(amendments, "extract_pdf_text", lambda raw: "amendment text")
    bill = _state_bill(db_session, 1)
    amendments.sync_bill_amendments(db_session, bill_entity=bill, amendments=[
        {"amendment_id": 271783, "chamber": "H", "adopted": 1, "title": "House Committee Amendment #208403",
         "date": "2026-02-10", "state_link": link},
    ])
    db_session.commit()
    bills = {1: {"status": 4, "amendments": [{"amendment_id": 271783, "state_link": link}]}}

    assert backfill_amendment_texts(db_session, bills, client=None, max_calls=0) == (1, 0, 0)
    from sqlalchemy import select

    from app.models import Event

    event = db_session.execute(select(Event).where(Event.event_type == "AMENDED")).scalar_one()
    assert event.attributes["state_link"] == link
    assert event.attributes["amendment_text"] == "amendment text"
