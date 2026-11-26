"""Rate-limit key behind the Cloudflare tunnel.

Every public request reaches the API from the cloudflared container, so
keying on the TCP peer put all visitors in ONE 120/minute bucket (and one
POST /flags bucket), and all server-side page renders in another, which also
capped the sitemap's ~216 API calls."""

import pytest
from starlette.requests import Request

from app.rate_limit import client_key


def req(peer: str, **headers) -> Request:
    raw = [(k.replace("_", "-").lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "client": (peer, 1234), "headers": raw})


def test_visitor_ip_from_cloudflare_when_the_peer_is_the_tunnel():
    assert client_key(req("172.18.0.5", cf_connecting_ip="203.0.113.9")) == "203.0.113.9"


def test_two_visitors_through_the_tunnel_get_separate_buckets():
    a = client_key(req("172.18.0.5", cf_connecting_ip="203.0.113.9"))
    b = client_key(req("172.18.0.5", cf_connecting_ip="198.51.100.7"))
    assert a != b


@pytest.mark.parametrize("peer", ["172.18.0.4", "127.0.0.1", "10.0.0.3", "::1"])
def test_internal_server_traffic_is_not_rate_limited(peer):
    # Frontend server renders, the admin proxy, the smoke test: no Cloudflare
    # header and a private peer. An empty key makes slowapi skip the limit.
    assert client_key(req(peer)) == ""


def test_a_public_peer_cannot_choose_its_bucket():
    # Only private peers (the tunnel) are trusted to carry CF-Connecting-IP.
    assert client_key(req("8.8.8.8", cf_connecting_ip="1.2.3.4")) == "8.8.8.8"


def test_non_ip_peer_is_used_as_is():
    # Starlette's TestClient reports "testclient": existing limit tests keep working.
    assert client_key(req("testclient")) == "testclient"
