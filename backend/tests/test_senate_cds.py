from datetime import date

import httpx
import pytest

from app.federal import senate_cds as sc
from app.models import Entity, FederalEarmark, OfficeTenure


def row(n, member="Senator Scott", state="FL", **kw):
    return {"row": n, "member": member, "member_state": state, "recipient": f"Recipient {n}", "project_purpose": "Do a thing.",
            "subcommittee": "Agriculture", "project_location": "Tampa", "project_state": "FL", "amount_requested": 2500000.0,
            "cds_website": "https://scott.senate.gov/fy27", **kw}


def client(pages):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        calls.append(form)
        rows = pages.get((form["search"], int(form["start"])), [])
        total = sum(len(v) for (s, _), v in pages.items() if s == form["search"])
        return httpx.Response(200, json={"RECORDSFILTERED": total, "RECORDSTOTAL": total, "DATA": rows})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_fetch_keeps_only_florida_members_dedupes_and_pauses_between_requests():
    pages = {("Scott", 0): [row(1), row(2, "Senator Scott", "SC")], ("Moody", 0): [row(3, "Senator Moody"), row(1)]}
    c, calls = client(pages)
    naps = []
    got = sc.fetch_florida(2027, ["Scott", "Moody"], client=c, sleep=naps.append)
    assert sorted(r["row"] for r in got) == [1, 3]
    assert len(calls) == 2 and naps == [sc.PAUSE_SECONDS]
    assert calls[0]["method"] == "getCDSTable27" and calls[0]["length"] == "50"


def test_fetch_pages_through_a_long_result_and_obeys_the_request_cap():
    big = {("Scott", 0): [row(i) for i in range(50)], ("Scott", 50): [row(i) for i in range(50, 60)]}
    c, calls = client(big)
    assert len(sc.fetch_florida(2027, ["Scott"], client=c, sleep=lambda s: None)) == 60 and len(calls) == 2
    c2, calls2 = client(big)
    sc.fetch_florida(2027, ["Scott"], client=c2, sleep=lambda s: None, max_requests=1)
    assert len(calls2) == 1


def test_unknown_year_and_unexpected_body_fail_clearly():
    with pytest.raises(sc.SenateCdsError):
        sc.fetch_florida(2031, ["Scott"])
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"error": "x"})))
    with pytest.raises(sc.SenateCdsError):
        sc.fetch_florida(2027, ["Scott"], client=c, sleep=lambda s: None)


def test_import_stores_requests_links_one_senator_and_is_idempotent(db_session):
    p = Entity(entity_type="person", name="Rick Scott")
    db_session.add(p)
    db_session.flush()
    db_session.add(OfficeTenure(person_entity_id=p.id, office_type="us_senate", state="FL", district=None, start_date=date(2019, 1, 8), source="t"))
    db_session.commit()
    s = sc.import_rows(db_session, [row(1), row(2)], fiscal_year=2027)
    assert s == {"rows": 2, "new": 2, "existing": 0, "linked": 2}
    e = db_session.query(FederalEarmark).filter_by(recipient="Recipient 1").one()
    assert (e.chamber, e.stage, e.district, e.member_last, e.amount, e.person_entity_id) == ("senate", "requested", "FL", "Scott", 2500000, p.id)
    assert e.recipient_address == "Tampa, FL"
    assert sc.import_rows(db_session, [row(1)], fiscal_year=2027)["existing"] == 1
