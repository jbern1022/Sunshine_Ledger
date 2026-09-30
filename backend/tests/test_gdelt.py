"""Weekly GDELT headlines: recent bills only, usable queries, real backoff, a time cap."""

from datetime import date

import httpx
import pytest

from app.pipeline import gdelt


@pytest.mark.parametrize(
    ("title", "query"),
    [
        ("Affordable Housing", "affordable housing"),
        ("Residential Swimming Pool Requirements", "residential swimming pool requirements"),
        ("Department of Financial Services", None),  # nothing distinctive
        ("Tax", None),
        ("An ordinance re: \"Sea-Level Rise\" & Flood (2026-0447)", "level rise flood"),
    ],
)
def test_build_query(title, query):
    assert gdelt.build_query(title) == query


def test_build_query_adds_the_place_and_drops_ordinance_shorthand():
    assert gdelt.build_query("ORD Approp $55,000 From the Multiyear Progs & Initiatives", "Jacksonville") is None
    assert (
        gdelt.build_query("ORD-Q Rezoning at 11713 Alta Dr, Btwn Port Jacksonville Pkwy", "Jacksonville")
        == "rezoning alta port jacksonville"
    )


def _client(responses, monkeypatch, sleeps):
    """A GDELTClient answering with `responses` in order."""
    monkeypatch.setattr(gdelt.time, "sleep", lambda s: sleeps.append(s))
    queue = list(responses)
    client = gdelt.GDELTClient()
    client._client = httpx.Client(transport=httpx.MockTransport(lambda request: queue.pop(0)))
    return client


def test_backs_off_on_429_honouring_retry_after(monkeypatch):
    sleeps = []
    client = _client(
        [httpx.Response(429, headers={"Retry-After": "5"}), httpx.Response(429), httpx.Response(200, json={"articles": [{"url": "u"}]})],
        monkeypatch,
        sleeps,
    )
    assert client.search_articles("affordable housing") == [{"url": "u"}]
    assert sleeps[-2:] == [5.0, 60.0]  # Retry-After, then the doubled default


def test_a_rejected_query_is_its_own_error(monkeypatch):
    client = _client([httpx.Response(200, text="Your search contained a keyword that was too short.")], monkeypatch, [])
    with pytest.raises(gdelt.GDELTQueryRejected):
        client.search_articles("ab")


def _bill(bill_factory, db_session, name, last_action):
    entity = bill_factory(bill_number=name[:10], name=name)
    entity.bill.last_action_date = last_action
    db_session.commit()
    return entity


class FakeClient:
    def __init__(self, reject=()):
        self.queries = []
        self.reject = set(reject)

    def search_articles(self, query, *, max_records=5, timespan="1month"):
        self.queries.append(query)
        if query in self.reject:
            raise gdelt.GDELTQueryRejected(query)
        return [{"url": f"https://news.example/{len(self.queries)}", "title": "Headline", "seendate": "20260920T120000Z"}]


def test_only_recent_bills_with_usable_queries(db_session, bill_factory):
    _bill(bill_factory, db_session, "Affordable Housing", date(2026, 9, 20))
    _bill(bill_factory, db_session, "Swimming Pool Requirements", date(2026, 6, 1))  # too old
    _bill(bill_factory, db_session, "Department of Financial Services", date(2026, 9, 21))  # no query
    _bill(bill_factory, db_session, "Coastal Flood Insurance", date(2026, 9, 22))
    client = FakeClient(reject={"coastal flood insurance florida"})

    written = gdelt.pull_headlines_for_all_bills(db_session, client=client, days=60, today=date(2026, 9, 30))

    # Most recent first, each with its place.
    assert client.queries == ["coastal flood insurance florida", "affordable housing florida"]
    assert written == 1
    from app.models import SourceCheck

    check = db_session.query(SourceCheck).filter_by(source_key="gdelt").one()
    assert check.last_result.startswith("1 headlines from 2 of 3 bills active in 60 days; 1 without a usable query, 1 rejected")


def test_stops_at_the_time_cap(db_session, bill_factory):
    _bill(bill_factory, db_session, "Affordable Housing", date(2026, 9, 20))
    client = FakeClient()
    gdelt.pull_headlines_for_all_bills(db_session, client=client, max_minutes=0, today=date(2026, 9, 30))
    assert client.queries == []
