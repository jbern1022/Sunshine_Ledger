from datetime import date

import httpx
import pytest

from app.federal import senate_cds as sc
from app.models import Entity, FederalEarmark, OfficeTenure


def row(n, member="Senator Scott", state="FL", **kw):
    return {"row": n, "member": member, "member_state": state, "recipient": f"Recipient {n}", "project_purpose": "Do a thing.",
            "subcommittee": "Agriculture", "project_location": "Tampa", "project_state": "FL", "amount_requested": 2500000.0,
            "cds_website": "https://scott.senate.gov/fy27", **kw}


def client(rows, total=None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        calls.append(form)
        start, length = int(form["start"]), int(form["length"])
        n = total if total is not None else len(rows)
        return httpx.Response(200, json={"RECORDSFILTERED": n, "RECORDSTOTAL": n, "DATA": rows[start:start + length]})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_fetch_pages_the_whole_chart_keeps_only_florida_members_and_pauses():
    rows = [row(i, "Senator Moody" if i % 2 else "Senator Scott", "FL" if i % 100 == 0 else "SC") for i in range(1, 1201)]
    c, calls = client(rows)
    naps = []
    got = sc.fetch_florida(2027, client=c, sleep=naps.append)
    assert sorted(r["row"] for r in got) == [i for i in range(1, 1201) if i % 100 == 0]
    assert len(calls) == 3 and naps == [sc.PAUSE_SECONDS] * 2
    assert calls[0]["method"] == "getCDSTable27" and calls[0]["length"] == "500" and calls[0]["search"] == ""


def test_the_request_cap_is_an_error_not_a_silent_partial_result():
    c, calls = client([row(i, state="SC") for i in range(1, 2000)])
    with pytest.raises(sc.SenateCdsError, match="stopped at"):
        sc.fetch_florida(2027, client=c, sleep=lambda s: None, max_requests=2)
    assert len(calls) == 2


def test_unknown_year_and_unexpected_body_fail_clearly():
    with pytest.raises(sc.SenateCdsError):
        sc.fetch_florida(2031)
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"error": "x"})))
    with pytest.raises(sc.SenateCdsError):
        sc.fetch_florida(2027, client=c, sleep=lambda s: None)


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
