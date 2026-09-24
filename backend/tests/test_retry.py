"""Tests for app.pipeline._retry.with_retry."""

from unittest.mock import patch

import httpx
import pytest

from app.pipeline._retry import RETRY_DELAYS_SECONDS, _redact_query_string, with_retry


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


def test_redact_query_string_strips_it_from_http_status_error_message():
    # A LegiScan/Census-style URL carries its API key as a query param
    # (?key=...&op=...). str(exc) must never include it.
    exc = _status_error(503, "https://api.legiscan.com/?key=SECRETKEY&op=getMasterList")
    redacted = _redact_query_string(exc)
    assert redacted is exc  # mutated in place, not replaced
    rendered = str(redacted)
    assert "SECRETKEY" not in rendered
    assert "key=" not in rendered
    assert "503" in rendered
    # .request / .response (and so .response.status_code) are untouched --
    # callers that inspect the status code or catch HTTPStatusError by type
    # keep working.
    assert redacted.response.status_code == 503
    assert isinstance(redacted, httpx.HTTPStatusError)


def test_redact_query_string_leaves_plain_exceptions_alone():
    exc = httpx.TimeoutException("timed out")
    assert _redact_query_string(exc) is exc
    assert str(exc) == "timed out"


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
def test_propagated_exception_on_non_retryable_4xx_is_redacted(mock_sleep):
    # Immediate-raise path (not retryable): the exception the caller
    # actually catches -- not just with_retry's own log line -- must be
    # redacted, since callers like staff_analysis.py log str(exc) directly.
    def fn():
        raise _status_error(404, "https://api.legiscan.com/?key=SECRETKEY&op=getBill")

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        with_retry(fn, description="test")

    assert "SECRETKEY" not in str(excinfo.value)
    assert excinfo.value.response.status_code == 404


@patch("time.sleep")
def test_propagated_exception_after_exhausted_retries_is_redacted(mock_sleep):
    # Exhausted-retries path (retryable 5xx that never recovers): same
    # requirement on the exception that finally escapes with_retry.
    def fn():
        raise _status_error(503, "https://api.legiscan.com/?key=SECRETKEY&op=getMasterList")

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        with_retry(fn, description="test")

    assert "SECRETKEY" not in str(excinfo.value)
    assert excinfo.value.response.status_code == 503


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
