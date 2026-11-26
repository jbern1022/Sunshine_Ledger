"""Privacy-safe usage counts (docs/USAGE_COUNTS_DESIGN.md).

Daily totals only: no identifiers, no bill or person ids, no IP or user agent
stored. Off by default because it changes a promise on /privacy.
"""

import datetime as dt

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import UsageCount

ORIGIN = "http://localhost:3000"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15"


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "usage_counts_enabled", True)
    monkeypatch.setattr(settings, "cors_allowed_origins", ORIGIN)


def _post(client, body, *, origin=ORIGIN, ua=BROWSER_UA):
    headers = {}
    if origin:
        headers["Origin"] = origin
    if ua is not None:
        headers["User-Agent"] = ua
    return client.post("/usage", json=body, headers=headers)


def _rows(db):
    return {(r.event, r.page_kind): r.count for r in db.execute(select(UsageCount)).scalars()}


def test_off_by_default_answers_404_and_writes_nothing(client, db_session):
    assert settings.usage_counts_enabled is False
    resp = _post(client, {"event": "page_view", "page_kind": "bill"})
    assert resp.status_code == 404
    assert _rows(db_session) == {}


def test_counts_a_page_view_as_a_daily_total(client, db_session, enabled):
    for _ in range(3):
        assert _post(client, {"event": "page_view", "page_kind": "bill"}).status_code == 204
    _post(client, {"event": "source_click", "page_kind": "bill"})

    rows = db_session.execute(select(UsageCount)).scalars().all()
    assert {(r.event, r.page_kind, r.count) for r in rows} == {("page_view", "bill", 3), ("source_click", "bill", 1)}
    assert all(r.day == dt.datetime.now(dt.timezone.utc).date() for r in rows)


def test_stores_nothing_but_day_event_kind_and_count(db_session):
    """The table itself is the privacy guarantee: no column could hold an
    identifier, a URL, an IP or a user agent."""
    assert set(UsageCount.__table__.columns.keys()) == {"day", "event", "page_kind", "count"}


@pytest.mark.parametrize(
    "body",
    [
        {"event": "page_view", "page_kind": "bill", "bill_id": "abc"},  # identifiers refused, not ignored
        {"event": "search", "page_kind": "browse"},  # unknown event
        {"event": "page_view", "page_kind": "/bills/0b3edc73"},  # a path is not a kind
        {"event": "page_view"},
    ],
)
def test_rejects_anything_outside_the_fixed_vocabulary(client, db_session, enabled, body):
    assert _post(client, body).status_code == 422
    assert _rows(db_session) == {}


@pytest.mark.parametrize(
    "ua",
    [
        "",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0 Safari/537.36",
        "python-requests/2.31",
        "curl/8.4.0",
    ],
)
def test_drops_crawlers_and_scripts_silently(client, db_session, enabled, ua):
    """Answered like a success so a crawler learns nothing, but not counted."""
    assert _post(client, {"event": "page_view", "page_kind": "home"}, ua=ua).status_code == 204
    assert _rows(db_session) == {}


@pytest.mark.parametrize("origin", [None, "https://evil.example"])
def test_drops_requests_not_from_the_site(client, db_session, enabled, origin):
    assert _post(client, {"event": "page_view", "page_kind": "home"}, origin=origin).status_code == 204
    assert _rows(db_session) == {}


def test_admin_readout_requires_auth(client, enabled):
    assert client.get("/usage/admin").status_code == 401


def test_admin_readout_lists_daily_rows(client, db_session, enabled, monkeypatch):
    _post(client, {"event": "bill_read", "page_kind": "bill"})
    resp = client.get("/usage/admin", auth=("testadmin", "testpass"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == [
        {"day": dt.datetime.now(dt.timezone.utc).date().isoformat(), "event": "bill_read", "page_kind": "bill", "count": 1}
    ]
