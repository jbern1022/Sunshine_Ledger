"""Deterministic checks on what the mapper proposed, from the first real run
(H1389, 2026-10-06: 16 of 19 mapped entries had a wrong part). They do not
trust the model:

- "anyone" only for a group the bill itself calls Anyone.
- A role is kept only if the group's own words name it (a county rule is not
  about developers).
- A requirement/exclusion value must actually appear in the condition or
  exception it cites (a date is not a property type).
- A condition with dates, numbers or amounts (statute citations aside), or one
  that is long or a list, is not mapped: the vocabulary cannot test it exactly,
  and a half-mapped condition silently loses its other half.

Pure functions. Unmapped is always the safe outcome.
"""

from __future__ import annotations

import re

ANYONE = re.compile(r"^\s*(anyone|any person|everyone|all persons)\s*\.?\s*$", re.IGNORECASE)

ROLE_WORDS = {
    "renter": r"\b(tenants?|renters?|lessees?)\b",
    "landlord": r"\b(landlords?|lessors?)\b",
    "homeowner": r"\b(home ?owners?|owner-occupants?)\b",
    "property_developer": r"\b(developers?|builders?)\b",
    "employer": r"\bemployers?\b",
    "employee": r"\b(employees?|workers?)\b",
    "business_owner": r"\bbusiness(es)? owners?\b",
    "local_government": r"\b(counties|county|municipalit(y|ies)|local governments?|cit(y|ies)|towns?|villages?)\b",
}

PROPERTY_WORDS = {
    "single_family": r"single[- ]family",
    "multifamily": r"multi[- ]?family",
    "commercial": r"\bcommercial\b",
}

MAX_CITED_CHARS = 250

# Statute references carry digits that say nothing about the condition.
_STATUTE = re.compile(r"\bss?\.\s*\d[\d.]*(\([\w]+\))*|\bart\.\s*[ivx]+|\bflorida statutes\b|\bsections?\s+\d[\d.]*(\([\w]+\))*|\b\d{2,3}\.\d{2,}[\d.]*(\([\w]+\))*", re.IGNORECASE)
_LIST_MARKERS = re.compile(r"(\(\s*a\s*\).*\(\s*b\s*\))|(\b1\.\s.*\b2\.\s)", re.DOTALL)


def is_anyone(group: str) -> bool:
    return bool(ANYONE.match(group or ""))


def supported_roles(group: str, roles: list[str]) -> list[str]:
    """The roles whose words the group itself contains."""
    return [r for r in roles if r in ROLE_WORDS and re.search(ROLE_WORDS[r], group or "", re.IGNORECASE)]


def too_complex(text: str, quote: str) -> str | None:
    """A reason the cited condition/exception cannot be mapped exactly, or None."""
    whole = f"{text} {quote}"
    if re.search(r"\d", _STATUTE.sub(" ", whole)):
        return "it mentions a date, number or amount the vocabulary cannot test"
    if max(len(text or ""), len(quote or "")) > MAX_CITED_CHARS or _LIST_MARKERS.search(whole):
        return "it is too long or compound to map exactly"
    return None


def evidenced_values(attr: str, values: list[str], cited: str) -> list[str]:
    """The values the cited text actually states."""
    kept = []
    for v in values:
        if attr == "jurisdiction":
            name = v.partition(":")[2]
            ok = bool(name) and re.search(rf"\b{re.escape(name)}\b", cited)
        elif attr == "property_type":
            ok = v in PROPERTY_WORDS and re.search(PROPERTY_WORDS[v], cited, re.IGNORECASE)
        else:
            ok = True  # no evidence rule for other attributes yet
        if ok:
            kept.append(v)
    return kept
