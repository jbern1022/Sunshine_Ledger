"""LegiScan calls are counted per operation (including retries), since
HTTP request logging is silenced and the free tier is 10,000 calls/month."""

import httpx

from app.pipeline import legiscan
from app.pipeline.legiscan import API_CALLS, LegiScanClient


def client_answering(responses: list[httpx.Response]) -> LegiScanClient:
    client = LegiScanClient(api_key="test-key")
    queue = iter(responses)
    client._client = httpx.Client(
        base_url="https://api.legiscan.com/", transport=httpx.MockTransport(lambda request: next(queue))
    )
    return client


def test_counts_each_call_by_operation(monkeypatch):
    monkeypatch.setattr(legiscan, "API_CALLS", API_CALLS.__class__())
    ok = {"status": "OK", "bill": {"bill_id": 1}}
    client = client_answering([httpx.Response(200, json=ok), httpx.Response(200, json=ok),
                               httpx.Response(200, json={"status": "OK", "roll_call": {}})])

    client.get_bill(1)
    client.get_bill(2)
    client.get_roll_call(3)

    assert dict(legiscan.API_CALLS) == {"getBill": 2, "getRollCall": 1}
    assert legiscan.api_usage_summary() == "LegiScan API calls this run: 3 (getBill 2, getRollCall 1)"


def test_summary_with_no_calls(monkeypatch):
    monkeypatch.setattr(legiscan, "API_CALLS", API_CALLS.__class__())
    assert legiscan.api_usage_summary() == "LegiScan API calls this run: 0"
