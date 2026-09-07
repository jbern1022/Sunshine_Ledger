"""Tests for app.pipeline._retry.with_retry."""

from unittest.mock import patch

import httpx
import pytest

from app.pipeline._retry import RETRY_DELAYS_SECONDS, with_retry


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test")
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
