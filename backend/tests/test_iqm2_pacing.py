import httpx
import pytest
from sqlalchemy import select

from app.models import CrawlCheckpoint, Entity, SourceCheck
from app.pipeline import miami_iqm2
from app.pipeline.iqm2_pacing import BudgetExhausted, Pacer
from app.pipeline.miami_iqm2 import IQM2Client, PolicyBlocked, ingest_miami_legislation


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def now(self):
        return self.t


def _pacer(clock, **kw):
    kw.setdefault("pace_seconds", 60)
    kw.setdefault("max_requests", 100)
    return Pacer(sleep=clock.sleep, clock=clock.now, **kw)


def test_pacer_spaces_requests_and_counts_them():
    c = Clock()
    p = _pacer(c)
    for _ in range(3):
        p.before_request()
    assert p.requests == 3 and c.sleeps == [60, 60]  # none before the first


def test_pacer_only_waits_for_the_time_not_already_spent():
    c = Clock()
    p = _pacer(c)
    p.before_request()
    c.t += 45  # the request itself took 45 s
    p.before_request()
    assert c.sleeps == [15]


def test_pacer_stops_at_the_request_cap_and_the_time_budget():
    c = Clock()
    p = _pacer(c, max_requests=2)
    p.before_request()
    p.before_request()
    with pytest.raises(BudgetExhausted, match="request cap"):
        p.before_request()
    c2 = Clock()
    p2 = _pacer(c2, max_seconds=100)
    p2.before_request()
    p2.before_request()  # waits 60, now 60 s in
    with pytest.raises(BudgetExhausted, match="time budget"):
        p2.before_request()  # would need to wait to 120 s
    assert p2.requests == 2


def test_the_portals_crawl_delay_is_a_floor_not_a_default():
    c = Clock()
    p = _pacer(c, pace_seconds=5)
    p.raise_floor(60)
    assert p.pace == 60
    p.raise_floor(10)
    assert p.pace == 60


def _client(handler, pacer):
    cl = IQM2Client(pacer=pacer)
    cl._client = httpx.Client(transport=httpx.MockTransport(handler))
    return cl


def test_client_reads_robots_once_and_honours_the_delay():
    c = Clock()
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 90\n")
        return httpx.Response(200, text="<p>nothing</p>")

    cl = _client(handler, _pacer(c, pace_seconds=10))
    cl.get_legislation(1)
    cl.get_legislation(2)
    assert seen == ["/robots.txt", "/Citizens/Detail_LegiFile.aspx", "/Citizens/Detail_LegiFile.aspx"]
    assert c.sleeps == [90, 90]


def test_client_stops_if_robots_disallows_our_pages():
    def handler(request):
        return httpx.Response(200, text="User-agent: *\nDisallow: /Citizens/\n")

    with pytest.raises(PolicyBlocked):
        _client(handler, _pacer(Clock())).get_legislation(1)


def test_retries_are_paced_and_counted(monkeypatch):
    monkeypatch.setattr("app.pipeline._retry.time.sleep", lambda s: None)
    c = Clock()
    calls = {"n": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, text="<p>x</p>")

    p = _pacer(c)
    _client(handler, p).get_legislation(7)
    assert p.requests == 3  # robots, the 503, the retry


def _record(i):
    return {"legi_file_id": i, "number": f"R-{i}", "type": "Resolution", "status": "Adopted",
            "date_text": "Jul 23, 2026", "title": f"Resolution {i}", "department": "Clerk", "sponsors": ""}


class FakeClient:
    """Pretends the portal holds records at these IDs."""

    base_url = "https://miamifl.iqm2.com/Citizens"

    def __init__(self, ids, pacer):
        self.ids, self.pacer, self.fetched = set(ids), pacer, []

    def get_legislation(self, i):
        self.pacer.before_request()
        self.fetched.append(i)
        return _record(i) if i in self.ids else None


@pytest.fixture(autouse=True)
def _no_ollama(monkeypatch):
    monkeypatch.setattr(miami_iqm2, "tag_local_bill", lambda *a, **k: None)


def test_a_cycle_resumes_across_runs_and_checks_only_when_complete(db_session):
    ids = {100, 101, 102}
    # run 1: 8 requests is not enough to see 25 misses
    c1 = FakeClient(ids, _pacer(Clock(), pace_seconds=0, max_requests=8))
    miami_iqm2._known_high_water_mark = lambda db, fallback: 105  # probe starts at 100
    first = ingest_miami_legislation(db_session, limit=2, client=c1)
    assert c1.fetched == list(range(100, 108)) and len(first) == 3
    state = db_session.execute(select(CrawlCheckpoint)).scalar_one().state
    assert state["phase"] == "probe" and state["probe_next"] == 108 and state["complete"] is False
    assert db_session.execute(select(SourceCheck)).scalars().all() == []  # not fully checked yet

    # run 2 carries on from 108, not from 100
    c2 = FakeClient(ids, _pacer(Clock(), pace_seconds=0, max_requests=500))
    ingest_miami_legislation(db_session, limit=2, client=c2)
    assert c2.fetched[0] == 108
    state = db_session.execute(select(CrawlCheckpoint)).scalar_one().state
    assert state["complete"] is True
    check = db_session.execute(select(SourceCheck)).scalar_one()
    assert check.source_key == "iqm2_miami" and "3 records" in check.last_result


def test_records_found_while_probing_are_not_fetched_again(db_session):
    miami_iqm2._known_high_water_mark = lambda db, fallback: 105
    c = FakeClient({100, 101, 102}, _pacer(Clock(), pace_seconds=0, max_requests=500))
    ingest_miami_legislation(db_session, limit=20, client=c)
    assert len([i for i in c.fetched if i in (100, 101, 102)]) == 3
    # the refresh phase only visits IDs below the frontier that probing did not
    assert c.fetched.count(99) <= 1


def test_a_completed_cycle_starts_a_new_one_next_time(db_session):
    miami_iqm2._known_high_water_mark = lambda db, fallback: 105
    ids = {100}
    ingest_miami_legislation(db_session, limit=1, client=FakeClient(ids, _pacer(Clock(), pace_seconds=0)))
    c = FakeClient(ids, _pacer(Clock(), pace_seconds=0))
    ingest_miami_legislation(db_session, limit=1, client=c)
    assert c.fetched[0] == 100  # the new cycle restarts at the high-water mark, not where the last one ended
    assert db_session.execute(select(Entity).where(Entity.entity_type == "bill")).scalars().all().__len__() == 1


def test_partial_run_does_not_touch_last_checked_at(db_session):
    from app.pipeline.source_checks import record_check

    record_check(db_session, "iqm2_miami", "old result")
    before = db_session.execute(select(SourceCheck)).scalar_one().last_checked_at
    miami_iqm2._known_high_water_mark = lambda db, fallback: 105
    ingest_miami_legislation(db_session, limit=2, client=FakeClient({100}, _pacer(Clock(), pace_seconds=0, max_requests=3)))
    row = db_session.execute(select(SourceCheck)).scalar_one()
    db_session.refresh(row)
    assert row.last_checked_at == before and row.last_result.startswith("incomplete")
