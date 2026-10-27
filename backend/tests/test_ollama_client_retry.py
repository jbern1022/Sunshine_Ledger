"""OllamaClient timeout/retry behaviour (bill-layers quality round, task 5).

The 2026-09-23 quality report hit one ReadTimeout on a long bill at the
default 120s timeout, and three ConnectErrors when Ollama restarted
mid-run. Layers callers use a longer timeout; `generate` retries exactly
once, after a short (patchable) sleep, on a connection-level error
(ConnectError, RemoteProtocolError, ReadError). It does not retry on a
timeout -- a request that timed out would most likely time out again --
nor on an HTTP error status, since retrying a 404/500 just repeats the
same failure.
"""

import httpx
import pytest

from app.pipeline import summarize
from app.pipeline.summarize import OllamaClient


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Record retry pauses instead of really sleeping."""
    slept: list[float] = []
    monkeypatch.setattr(summarize, "_sleep", slept.append)
    return slept


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


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.RemoteProtocolError("server disconnected without sending a response"),
        httpx.ReadError("connection reset by peer"),
    ],
)
def test_generate_retries_once_on_connection_error_then_succeeds(monkeypatch, no_sleep, error):
    client = OllamaClient()
    calls = {"n": 0}

    def flaky_post(url, json=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise error
        return _FakeResponse(200, {"response": "hello"})

    monkeypatch.setattr(client._client, "post", flaky_post)
    result = client.generate("prompt")
    assert result == "hello"
    assert calls["n"] == 2
    assert no_sleep == [summarize.RETRY_DELAY_SECONDS]
    assert summarize.RETRY_DELAY_SECONDS == 5.0


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ConnectTimeout("timed out"),
        httpx.WriteTimeout("timed out"),
        httpx.PoolTimeout("timed out"),
    ],
)
def test_generate_does_not_retry_on_timeout(monkeypatch, no_sleep, error):
    client = OllamaClient()
    calls = {"n": 0}

    def times_out(url, json=None):
        calls["n"] += 1
        raise error

    monkeypatch.setattr(client._client, "post", times_out)
    with pytest.raises(type(error)):
        client.generate("prompt")
    assert calls["n"] == 1
    assert no_sleep == []


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


# The bill layers run at temperature 0 (F2, 2026-10-02): at Ollama's default,
# two HB 1389 runs kept 4 and 14 Who it affects entries from the same text.
def test_temperature_is_sent_only_when_set(monkeypatch):
    bodies = []

    def post(url, json=None):
        bodies.append(json)
        return _FakeResponse(200, {"response": "ok"})

    default, fixed = OllamaClient(), OllamaClient(temperature=0)
    monkeypatch.setattr(default._client, "post", post)
    monkeypatch.setattr(fixed._client, "post", post)
    default.generate("p")
    fixed.generate("p", json_mode=True)
    assert "options" not in bodies[0]
    assert bodies[1]["options"] == {"temperature": 0}


def test_num_predict_caps_output_when_set(monkeypatch):
    bodies = []

    def post(url, json=None):
        bodies.append(json)
        return _FakeResponse(200, {"response": "ok"})

    client = OllamaClient(temperature=0, num_predict=3072)
    monkeypatch.setattr(client._client, "post", post)
    client.generate("p", json_mode=True)
    assert bodies[0]["options"] == {"temperature": 0, "num_predict": 3072}


# 2026-10-27: HB 1389's Who-it-affects layer came out 23, 24 and 26 entries on
# three runs of identical code, input and temperature 0, so the airport
# exception came and went. With a fixed seed two runs were identical.
def test_seed_is_sent_only_when_set(monkeypatch):
    bodies = []

    def post(url, json=None):
        bodies.append(json)
        return _FakeResponse(200, {"response": "ok"})

    plain, seeded = OllamaClient(temperature=0), OllamaClient(temperature=0, seed=42)
    monkeypatch.setattr(plain._client, "post", post)
    monkeypatch.setattr(seeded._client, "post", post)
    plain.generate("p")
    seeded.generate("p")
    assert "seed" not in bodies[0]["options"]
    assert bodies[1]["options"] == {"temperature": 0, "seed": 42}


def test_a_seed_of_zero_is_still_sent(monkeypatch):
    bodies = []
    client = OllamaClient(temperature=0, seed=0)
    monkeypatch.setattr(client._client, "post", lambda url, json=None: (bodies.append(json), _FakeResponse(200, {"response": "ok"}))[1])
    client.generate("p")
    assert bodies[0]["options"] == {"temperature": 0, "seed": 0}


def test_layer_and_lens_clients_share_one_seed_constant():
    import inspect

    from app.impact_lens import map_batch
    from app.pipeline import bill_layers_batch, review_bill_layers

    assert isinstance(summarize.LAYERS_SEED, int)
    for module in (bill_layers_batch, review_bill_layers, map_batch):
        assert "seed=LAYERS_SEED" in inspect.getsource(module), module.__name__
