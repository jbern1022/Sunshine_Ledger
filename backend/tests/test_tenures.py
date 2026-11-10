from datetime import date, datetime, timezone

import pytest

from app.models import ElectionWinner, Entity, OfficeTenure
from app.tenures import (
    LEFT_OFFICE_STATUS, TenureError, has_left_office, left_office_label, person_tenures, seat_changes,
    set_tenure_end, tenure_label,
)

TODAY = date(2027, 1, 10)


def _person(db, name="Pat Doe", **attrs):
    e = Entity(entity_type="person", name=name, jurisdiction_level="federal", jurisdiction_name="US",
               external_ids={}, attributes=attrs)
    db.add(e)
    db.flush()
    return e


def _tenure(db, person, *, office="us_house", district=12, start=date(2013, 1, 3), end=None, sched=date(2027, 1, 3)):
    t = OfficeTenure(person_entity_id=person.id, office_type=office, district=district, start_date=start,
                     scheduled_end=sched, end_date=end, source="test", attributes={})
    db.add(t)
    db.flush()
    return t


def test_ending_a_tenure_needs_reason_source_and_sane_dates(db_session):
    t = _tenure(db_session, _person(db_session))
    with pytest.raises(TenureError, match="reason"):
        set_tenure_end(db_session, t, end_date=date(2027, 1, 3), reason="fired", source_url="u")
    with pytest.raises(TenureError, match="source"):
        set_tenure_end(db_session, t, end_date=date(2027, 1, 3), reason="lost_general", source_url=" ")
    with pytest.raises(TenureError, match="before it starts"):
        set_tenure_end(db_session, t, end_date=date(2012, 1, 1), reason="lost_general", source_url="u")
    set_tenure_end(db_session, t, end_date=date(2027, 1, 3), reason="lost_general", source_url="https://doe.example/cert")
    assert tenure_label(t) == "Former U.S. Representative, District 12, 2013-2027, lost the general election"


def test_a_sitting_official_has_no_former_label(db_session):
    p = _person(db_session)
    t = _tenure(db_session, p)
    assert tenure_label(t) is None
    assert not has_left_office([t], today=TODAY)


def test_moving_chambers_is_not_leaving_office(db_session):
    p = _person(db_session)
    house = _tenure(db_session, p, end=date(2019, 1, 3), start=date(2013, 1, 3))
    sen = _tenure(db_session, p, office="us_senate", district=None, start=date(2019, 1, 3), end=None)
    assert not has_left_office([house, sen], today=TODAY)
    set_tenure_end(db_session, sen, end_date=date(2025, 1, 3), reason="did_not_run", source_url="u")
    assert has_left_office([house, sen], today=TODAY)
    assert left_office_label([house, sen], today=TODAY).startswith("Former U.S. Senator, 2019-2025")


def test_no_tenures_means_no_claim(db_session):
    assert not has_left_office([], today=TODAY)


def test_confirmed_same_person_shows_both_tenures(db_session):
    fed = _person(db_session, "Gus B")
    state = _person(db_session, "Gus Bilirakis")
    fed.attributes = {"same_person_as": str(state.id)}
    a = _tenure(db_session, fed)
    b = _tenure(db_session, state, office="fl_house", district=45, start=date(2000, 11, 7), end=date(2006, 11, 7))
    assert {t.id for t in person_tenures(db_session, fed.id)} == {a.id, b.id}


def test_person_api_shows_the_former_label(client, db_session):
    p = _person(db_session, "Pat Doe", role="Rep")
    t = _tenure(db_session, p, end=date(2025, 12, 1))
    set_tenure_end(db_session, t, end_date=date(2025, 12, 1), reason="lost_primary", source_url="https://x/cert")
    body = client.get(f"/people/{p.id}").json()
    assert body["former_label"] == "Former U.S. Representative, District 12, 2013-2025, lost the primary"
    assert body["tenures"][0]["end_reason_source_url"] == "https://x/cert"


def test_promise_api_marks_left_office_not_unfulfilled(client, db_session):
    from app.models import OfficialSite, PromiseItem, SiteSnapshot

    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    p = _person(db_session)
    t = _tenure(db_session, p, office="fl_house", district=3, end=date(2025, 12, 1))
    t.end_reason, t.end_reason_source_url = "lost_general", "u"
    w = ElectionWinner(cycle=2026, chamber="house", district=3, name="Pat Doe", result_status="certified",
                       source_url="u", source_retrieved_at=now, person_entity_id=p.id, change_log=[])
    db_session.add(w)
    db_session.flush()
    site = OfficialSite(winner_id=w.id, url="https://p.example/", site_kind="campaign", discovered_via="manual", discovered_at=now)
    db_session.add(site)
    db_session.flush()
    snap = SiteSnapshot(site_id=site.id, url=site.url, status="ok", fetched_at=now, content_hash="b" * 64)
    db_session.add(snap)
    db_session.flush()
    db_session.add(PromiseItem(snapshot_id=snap.id, winner_id=w.id, quote_text="I will fix the roads.", char_start=0,
                               char_end=21, source_url=site.url, captured_at=now, auto_labels={}))
    db_session.flush()
    item = client.get("/promises").json()["items"][0]
    assert item["official"]["office_status"] == LEFT_OFFICE_STATUS
    assert not any("unfulfilled" in str(v).lower() for v in item.values())


def test_seat_changes_reports_but_never_writes(db_session):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    old = _person(db_session, "Old Member")
    t = _tenure(db_session, old, office="fl_house", district=7)
    db_session.add(ElectionWinner(cycle=2026, chamber="house", district=7, name="New Member", result_status="certified",
                                  source_url="u", source_retrieved_at=now, change_log=[]))
    db_session.flush()
    out = seat_changes(db_session, cycle=2026)
    assert out[0]["new_winner"] == "New Member" and out[0]["tenure_id"] == t.id
    assert t.end_date is None and t.end_reason is None
