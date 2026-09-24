"""OllamaClient timeout/retry behaviour (bill-layers quality round, task 5).

The 2026-09-23 quality report hit one ReadTimeout on a long bill at the
default 120s timeout, and three ConnectErrors when Ollama restarted
mid-run. Layers callers use a longer timeout; `generate` retries exactly
once on a transport-level error (connection refused, reset, etc.) and does
not retry on an HTTP error status, since retrying a 404/500 just repeats
the same failure.
"""

import httpx
import pytest

from app.pipeline.summarize import OllamaClient


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"response": "ok"}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://fake/api/generate")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._payload


def test_default_timeout_is_120(monkeypatch):
    captured = {}
    orig_client = httpx.Client

    def spy(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", spy)
    OllamaClient()
    assert captured["timeout"] == 120.0


def test_custom_timeout_is_passed_through(monkeypatch):
    captured = {}
    orig_client = httpx.Client

    def spy(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", spy)
    OllamaClient(timeout=300.0)
    assert captured["timeout"] == 300.0


def test_generate_retries_once_on_connect_error_then_succeeds(monkeypatch):
    client = OllamaClient()
    calls = {"n": 0}

    def flaky_post(url, json=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection refused")
        return _FakeResponse(200, {"response": "hello"})

    monkeypatch.setattr(client._client, "post", flaky_post)
    result = client.generate("prompt")
    assert result == "hello"
    assert calls["n"] == 2


def test_generate_raises_after_second_connect_error(monkeypatch):
    client = OllamaClient()

    def always_fails(url, json=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(client._client, "post", always_fails)
    with pytest.raises(httpx.ConnectError):
        client.generate("prompt")


def test_generate_does_not_retry_on_http_status_error(monkeypatch):
    client = OllamaClient()
    calls = {"n": 0}

    def not_found(url, json=None):
        calls["n"] += 1
        return _FakeResponse(404)

    monkeypatch.setattr(client._client, "post", not_found)
    with pytest.raises(httpx.HTTPStatusError):
        client.generate("prompt")
    assert calls["n"] == 1
