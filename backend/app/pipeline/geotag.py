"""Geographic scope tagging (BRD 5.3): tag each bill with county/city scope
based on bill text, falling back to the jurisdiction's default (statewide
for state bills; the filing city for local bills).

Keyword-matching against a data-driven jurisdiction list rather than any
Florida-specific code, so a second state is a new JSON file, not new logic
(BRD 6 state-agnostic requirement). This is intentionally simple for MVP —
a state bill that names a specific county in its text (e.g. population
threshold bills that de facto target one county) gets narrowed from
statewide to that county; everything else keeps its ingestion-time default.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

JURISDICTIONS_PATH = Path(__file__).parent / "sample_data" / "fl_jurisdictions.json"


@dataclass
class GeoTag:
    scope_type: str  # statewide | county | city
    scope_names: list[str]


def _load_jurisdictions(path: Path = JURISDICTIONS_PATH) -> dict:
    return json.loads(path.read_text())


def tag_bill_geography(
    bill_text: str,
    *,
    default_scope_type: str,
    default_scope_names: list[str],
    jurisdictions_path: Path = JURISDICTIONS_PATH,
) -> GeoTag:
    """Narrow a bill's geographic scope by scanning its text for named
    counties/cities. Falls back to the ingestion-time default (e.g.
    statewide for a LegiScan bill, or the filing city for a Legistar bill)
    when no specific jurisdiction is mentioned.
    """
    data = _load_jurisdictions(jurisdictions_path)
    text = bill_text or ""

    matched_counties = [c for c in data["counties"] if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE)]
    if matched_counties:
        return GeoTag(scope_type="county", scope_names=matched_counties)

    matched_cities = [c for c in data["cities"] if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE)]
    if matched_cities:
        return GeoTag(scope_type="city", scope_names=matched_cities)

    return GeoTag(scope_type=default_scope_type, scope_names=default_scope_names)
