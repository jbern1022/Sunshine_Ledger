#!/usr/bin/env python3
"""Find which Florida counties and municipalities have a live Legistar client
(and, by DNS, an eSCRIBE tenant).

Legistar client tokens aren't guessable from the city name (see
docs/NATIONWIDE_COVERAGE.md), so this tries a handful of common patterns per
place and reports each hit with its body count and newest matter date. A miss
means "not found by guessing", NOT "not on Legistar": confirm a miss by hand
(https://<city>.legistar.com in a browser) before concluding anything. A hit
needs two checks before it counts: `likely_florida` (the token may be another
state's city of the same name) and a recent `newest_matter` (an old date is a stale client (Miami's `miamifl` is the
cautionary case) not coverage.

    python3 scripts/probe_legistar_tokens.py > legistar-probe.json
    python3 scripts/probe_legistar_tokens.py --only "Fort Lauderdale" Tampa

Standard library only. Polite by default: 4 workers, each pausing between
requests.
"""

from __future__ import annotations

import argparse
import http.client
import json
from concurrent.futures import ThreadPoolExecutor
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://webapi.legistar.com/v1/{token}"
DATA = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "fl_municipalities.json"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def candidates(name: str, kind: str) -> list[str]:
    s = slug(name)
    if kind == "county":
        pats = [f"{s}county", f"{s}countyfl", f"{s}co", f"{s}fl", f"{s}bocc", f"{s}"]
    else:
        pats = [s, f"{s}fl", f"cityof{s}", f"{s}city", f"{s}gov", f"{s}florida"]
    seen: list[str] = []
    for p in pats:
        if p not in seen:
            seen.append(p)
    return seen


def escribe_tenant(name: str, kind: str) -> str | None:
    """eSCRIBE (Orlando's platform) gives each tenant its own DNS name, and a
    bogus name does not resolve, so DNS alone detects a tenant. (Most other
    meeting platforms use wildcard DNS: every name resolves, so DNS says
    nothing.) A hit proves a tenant of that name exists, not that it is the
    Florida one: confirm by opening it."""
    s = slug(name)
    pats = [s, f"{s}fl", f"cityof{s}", f"{s}county", f"{s}countyfl"] if kind == "county" else [s, f"{s}fl", f"cityof{s}", f"{s}city"]
    for p in pats:
        host = f"pub-{p}.escribemeetings.com"
        try:
            socket.gethostbyname(host)
            return host
        except OSError:
            continue
    return None


def get_json(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "SunshineLedger-probe/1.0 (public records research)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, http.client.HTTPException, json.JSONDecodeError):
        # Connection resets and timeouts happen on a long run; one place's
        # failure must not lose the rest (a miss is reported as a miss).
        return None, None


def probe(token: str) -> dict | None:
    base = BASE.format(token=token)
    status, bodies = get_json(f"{base}/bodies")
    if status != 200 or not isinstance(bodies, list):
        return None  # a wrong token 500s with "LegistarConnectionString ... not set up"
    q = urllib.parse.quote("MatterLastModifiedUtc desc")
    status, matters = get_json(f"{base}/matters?$top=1&$orderby={q}")
    newest = None
    if status == 200 and isinstance(matters, list) and matters:
        newest = (matters[0].get("MatterLastModifiedUtc") or "")[:10] or None
    # A guessed token proves only that *a* Legistar client exists: "madison" is
    # Madison, WI, "oakland" is Oakland, CA. Florida legislation cites "Florida
    # Statutes" / "F.S."; out-of-state clients almost never do (0-1 matters
    # against 2-50 for real Florida clients on 2026-10-13).
    flt = urllib.parse.quote("substringof('Florida Statutes',MatterTitle) eq true or substringof('F.S.',MatterTitle) eq true")
    status, fl = get_json(f"{base}/matters?$filter={flt}&$top=50&$select=MatterId")
    fl_count = len(fl) if status == 200 and isinstance(fl, list) else None
    return {
        "token": token,
        "bodies": len(bodies),
        "body_names": [b.get("BodyName") for b in bodies][:5],
        "newest_matter": newest,
        "florida_statute_matters": fl_count,
        "likely_florida": bool(fl_count and fl_count >= 2),
    }


def places(only: list[str] | None) -> list[tuple[str, str, list[str]]]:
    munis = json.loads(DATA.read_text())["municipalities"]
    out: list[tuple[str, str, list[str]]] = []
    counties = sorted({c for m in munis for c in m["counties"]})
    for c in counties:
        out.append((c, "county", [c]))
    for m in munis:
        out.append((m["name"], "city", m["counties"]))
    if only:
        wanted = {o.lower() for o in only}
        out = [p for p in out if p[0].lower() in wanted]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", help="probe just these place names")
    ap.add_argument("--pause", type=float, default=0.2, help="seconds between requests")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    todo = places(args.only)

    def one(item: tuple[str, str, list[str]]) -> dict:
        name, kind, counties = item
        hit = None
        for token in candidates(name, kind):
            hit = probe(token)
            time.sleep(args.pause)
            if hit:
                break
        escribe = escribe_tenant(name, kind)
        print(f"{name} ({kind}): legistar={hit['token'] if hit else '-'} escribe={escribe or '-'}", file=sys.stderr)
        return {"name": name, "kind": kind, "counties": counties, "legistar": hit, "escribe_host": escribe}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, todo))
    json.dump({"probed_at": time.strftime("%Y-%m-%d"), "results": results}, sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
