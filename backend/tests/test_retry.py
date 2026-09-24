"""Tests for app.pipeline._retry.with_retry."""

from unittest.mock import patch

import httpx
import pytest

from app.pipeline._retry import RETRY_DELAYS_SECONDS, _safe_exc_str, with_retry


def _status_error(code: int, url: str = "https://example.test") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


@patch("time.sleep")
def test_succeeds_first_try_without_sleeping(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert with_retry(fn, description="test") == "ok"
    assert len(calls) == 1
    mock_sleep.assert_not_called()


@patch("time.sleep")
def test_retries_on_timeout_then_succeeds(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise httpx.TimeoutException("timed out")
        return "ok"

    assert with_retry(fn, description="test") == "ok"
    assert len(calls) == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(RETRY_DELAYS_SECONDS[0])
    mock_sleep.assert_any_call(RETRY_DELAYS_SECONDS[1])


@patch("time.sleep")
def test_retries_on_connect_error(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ConnectError("connection refused")
        return "ok"

    assert with_retry(fn, description="test") == "ok"
    assert len(calls) == 2


@patch("time.sleep")
def test_retries_on_5xx(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise _status_error(503)
        return "ok"

    assert with_retry(fn, description="test") == "ok"
    assert len(calls) == 2


@patch("time.sleep")
def test_exhausts_all_retries_then_raises(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise httpx.TimeoutException("still timing out")

    with pytest.raises(httpx.TimeoutException):
        with_retry(fn, description="test")

    # 1 initial attempt + len(delays) retries
    assert len(calls) == len(RETRY_DELAYS_SECONDS) + 1
    assert mock_sleep.call_count == len(RETRY_DELAYS_SECONDS)


@patch("time.sleep")
def test_does_not_retry_on_4xx(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise _status_error(404)

    with pytest.raises(httpx.HTTPStatusError):
        with_retry(fn, description="test")

    assert len(calls) == 1
    mock_sleep.assert_not_called()


def test_safe_exc_str_strips_query_string_from_http_status_error():
    # A LegiScan-style URL carries its API key as a query param
    # (?key=...&op=...). The retry log line must never include it.
    exc = _status_error(503, "https://api.legiscan.com/?key=SECRETKEY&op=getMasterList")
    rendered = _safe_exc_str(exc)
    assert "SECRETKEY" not in rendered
    assert "key=" not in rendered
    assert "503" in rendered


def test_safe_exc_str_leaves_plain_exceptions_alone():
    assert _safe_exc_str(httpx.TimeoutException("timed out")) == "timed out"


@patch("time.sleep")
def test_retry_log_line_never_includes_query_string_key(mock_sleep, caplog):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise _status_error(503, "https://api.legiscan.com/?key=SECRETKEY&op=getMasterList")
        return "ok"

    with caplog.at_level("WARNING"):
        with_retry(fn, description="LegiScan op=getMasterList")

    assert "SECRETKEY" not in caplog.text


@patch("time.sleep")
def test_does_not_retry_on_unrelated_exception(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("not a network problem")

    with pytest.raises(ValueError):
        with_retry(fn, description="test")

    assert len(calls) == 1
    mock_sleep.assert_not_called()
