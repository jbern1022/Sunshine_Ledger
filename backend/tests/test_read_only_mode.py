"""READ_ONLY mode for the AWS pilot-light standby (Todoist 6j59grWMFJW7gFCp).

The standby restores the last S3 dump; anything written to it is lost on
failback, so every write is refused with 503 while reads keep working."""

import pytest

from app.config import settings
from app.main import app


def _write_routes():
    out = []
    for r in app.routes:
        for m in getattr(r, "methods", set()) or set():
            if m in {"POST", "PUT", "PATCH", "DELETE"}:
                out.append((m, r.path))
    return sorted(out)


@pytest.fixture()
def read_only(monkeypatch):
    monkeypatch.setattr(settings, "read_only", True)
    monkeypatch.setattr(settings, "usage_counts_enabled", True)
    monkeypatch.setattr(settings, "auth_enabled", True)


def test_off_by_default():
    assert settings.read_only is False


def test_every_write_route_answers_503(client, read_only):
    routes = _write_routes()
    assert len(routes) >= 20  # flags, corrections, admin reviews, accounts, watchlists, usage
    for method, path in routes:
        url = path.replace("{", "").replace("}", "")  # placeholders become literal segments
        resp = client.request(method, url, json={}, auth=("testadmin", "testpass"))
        assert resp.status_code == 503, f"{method} {path} -> {resp.status_code}"
        assert resp.json()["read_only"] is True
        assert resp.headers["retry-after"]


def test_reads_still_work(client, read_only):
    assert client.get("/health").status_code == 200
    assert client.get("/bills").status_code == 200
    assert client.get("/sources/status").status_code == 200


def test_the_refusal_is_readable_cross_origin(client, read_only):
    """Raised inside the app, so CORS headers are still added and the site
    can show the message instead of a network error. (The test app allows
    the origin http://testserver; see conftest.)"""
    resp = client.post("/flags", json={}, headers={"Origin": "http://testserver"})
    assert resp.status_code == 503
    assert resp.headers.get("access-control-allow-origin") == "http://testserver"


def test_writes_work_normally_when_off(client):
    # A malformed flag is a validation error, not a read-only refusal.
    assert client.post("/flags", json={}).status_code == 422
