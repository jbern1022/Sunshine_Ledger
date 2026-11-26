from app.config import settings


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "read_only": False}


def test_health_reports_read_only_on_the_standby(client, monkeypatch):
    # The uptime check string-matches '"read_only":false', so a response from
    # the pilot-light standby (READ_ONLY=true) counts as "home is down" and the
    # failover automation does not stop the standby while it is the only origin.
    monkeypatch.setattr(settings, "read_only", True)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "read_only": True}


def test_health_body_is_compact_for_the_uptime_string_match(client):
    assert b'"read_only":false' in client.get("/health").content
