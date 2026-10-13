#!/usr/bin/env python3
"""Find which Florida counties and municipalities have a live Legistar client.

Legistar client tokens aren't guessable from the city name (see
docs/NATIONWIDE_COVERAGE.md), so this tries a handful of common patterns per
place and reports each hit with its body count and newest matter date. A miss
means "not found by guessing", NOT "not on Legistar": confirm a miss by hand
(https://<city>.legistar.com in a browser) before concluding anything. A hit
with an old newest-matter date is a stale client (Miami's `miamifl` is the
cautionary case), not coverage.

    python3 scripts/probe_legistar_tokens.py > legistar-probe.json
    python3 scripts/probe_legistar_tokens.py --only "Fort Lauderdale" Tampa

Standard library only. Polite by default: one request at a time, a pause
between requests.
"""

from __future__ import annotations

import argparse
import json
import re
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


def get_json(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "SunshineLedger-probe/1.0 (public records research)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
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
    return {"token": token, "bodies": len(bodies), "body_names": [b.get("BodyName") for b in bodies][:5], "newest_matter": newest}


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
    ap.add_argument("--pause", type=float, default=0.25, help="seconds between requests")
    args = ap.parse_args()

    results = []
    todo = places(args.only)
    for i, (name, kind, counties) in enumerate(todo, 1):
        hit = None
        for token in candidates(name, kind):
            hit = probe(token)
            time.sleep(args.pause)
            if hit:
                break
        results.append({"name": name, "kind": kind, "counties": counties, "legistar": hit})
        print(f"[{i}/{len(todo)}] {name} ({kind}): {hit['token'] if hit else '-'}", file=sys.stderr)
    json.dump({"probed_at": time.strftime("%Y-%m-%d"), "results": results}, sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
