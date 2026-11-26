import ipaddress

from slowapi import Limiter
from starlette.requests import Request


def client_key(request: Request) -> str:
    """Who to rate-limit: the visitor, not the tunnel.

    Every public request reaches the API from the cloudflared container, so the
    TCP peer is the same for everyone; keyed on it, all visitors shared one
    bucket (and one POST /flags bucket). Cloudflare sets CF-Connecting-IP at its
    edge and overwrites any value a client sends, so when the peer is a private
    address (the tunnel, on the compose network) that header is the visitor.

    A private peer WITHOUT the header is our own server traffic: the frontend's
    server-side renders and sitemap (~216 calls in one burst), the admin proxy,
    the smoke test. An empty key makes slowapi skip the limit for it.

    Any other peer is used as-is, so a public client can't pick its own bucket
    by sending the header. (Only relevant if BIND_ADDRESS exposes the API.)
    """
    peer = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer  # e.g. Starlette's TestClient ("testclient")
    if ip.is_private or ip.is_loopback:
        return request.headers.get("cf-connecting-ip", "").strip()
    return peer


# Generous default for normal browsing; individual write-capable routes
# (e.g. POST /flags) apply a stricter limit on top.
limiter = Limiter(key_func=client_key, default_limits=["120/minute"])
