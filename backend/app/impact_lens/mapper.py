"""Phase 2: the mapper. Turns one verified Who-it-affects entry into criteria.

The model sees only the entry (group, change, quote, numbered conditions and
exceptions) and the vocabulary, never the bill text, so it cannot invent a
condition the bill does not state. Everything it answers goes through
validate_criteria, which keeps what is valid and lists the rest as unmapped.

A failed model call (bad JSON, timeout) raises MapperError and stores nothing,
so a retry is possible; a model that answers badly is stored as unmapped.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.impact_lens.criteria import validate_criteria
from app.impact_lens.vocabulary import (
    FLORIDA_COUNTIES, MUNICIPALITY_COUNTIES, REGISTRY, VOCABULARY_VERSION, Attribute,
    county_value, municipality_value,
)
from app.models import BillLayer, BillLayerCriteria

# Bump when the prompt or its guards change in a way that should remap.
METHOD_VERSION = "impact_lens_criteria/2"

PROMPT = """You map one entry from a bill analysis onto a fixed vocabulary, so a reader's answers about themselves can be tested against it. You do not judge the bill and you do not add anything the entry does not state.

Entry
- Group: {group}
- What changes: {change}
- Quote: "{quote}"

Conditions (limits the bill states):
{conditions}

Exceptions (exclusions the bill states):
{exceptions}

Vocabulary
- role (who the entry is about): {roles}
- jurisdiction: "county:<Name>" for a Florida county, "municipality:<Name>" for an incorporated city, town or village. Names found in the entry text: {names}
- property_type: {property_types}

Rules
- "audience": {{"kind": "attr", "attr": "role", "any_of": [...]}} when the group is one of the roles. {{"kind": "anyone"}} when the group is "Anyone" / any person. null when no role fits. Never force a fit.
- "requires": one item per condition you can express with the vocabulary: {{"attr": "...", "op": "in", "values": [...], "from": {{"kind": "condition", "index": N}}}}.
- "excludes": the same for exceptions, with "from": {{"kind": "exception", "index": N}}.
- Anything you cannot express exactly (dates, dollar amounts, unit counts, anything outside the vocabulary): do not approximate. List it in "unmapped": {{"kind": "condition" or "exception", "index": N, "reason": "..."}}.
- "ambiguous": only when the quote itself supports two reasonable readings that would change who is affected. Give {{"question": "...", "quote": "<one quote above, copied exactly>"}}. Otherwise null.

Respond with JSON only: {{"audience": ..., "requires": [], "excludes": [], "unmapped": [], "ambiguous": null}}"""


class MapperError(RuntimeError):
    pass


def _numbered(items: list[dict]) -> str:
    if not items:
        return "(none)"
    return "\n".join(f'{i}. {it.get("text", "")}  Quote: "{it.get("quote", "")}"' for i, it in enumerate(items))


def names_in(text: str) -> list[str]:
    """Registry jurisdictions the entry's own text names (whole-word, case-sensitive)."""
    found: list[str] = []
    for county in FLORIDA_COUNTIES:
        if re.search(rf"\b{re.escape(county)}\b", text):
            found.append(county_value(county))
    for place in MUNICIPALITY_COUNTIES:
        if re.search(rf"\b{re.escape(place)}\b", text):
            found.append(municipality_value(place))
    return found


def entry_change(entry: dict) -> str:
    """Who entries store their plain-language change under "text" (the prompt
    asks for "change"; storage normalizes it). The first real run sent the
    model an empty line because this read the wrong key."""
    return str(entry.get("text") or entry.get("change") or "")


def entry_text(entry: dict) -> str:
    parts = [entry.get("group", ""), entry_change(entry), entry.get("quote", "")]
    for field in ("conditions", "exceptions"):
        for it in entry.get(field) or []:
            parts += [it.get("text", ""), it.get("quote", "")]
    return " ".join(str(p) for p in parts)


def build_prompt(entry: dict, registry: dict[str, Attribute] = REGISTRY) -> str:
    names = names_in(entry_text(entry))
    return PROMPT.format(
        group=entry.get("group", ""),
        change=entry_change(entry),
        quote=entry.get("quote", ""),
        conditions=_numbered(entry.get("conditions") or []),
        exceptions=_numbered(entry.get("exceptions") or []),
        roles=", ".join(registry["role"].values),
        names=", ".join(names) if names else "(none)",
        property_types=", ".join(registry["property_type"].values),
    )


def entry_quotes(entry: dict) -> set[str]:
    quotes = {entry.get("quote")}
    for field in ("conditions", "exceptions"):
        quotes |= {it.get("quote") for it in entry.get(field) or []}
    return {q for q in quotes if isinstance(q, str) and q}


def map_entry(entry: dict, entry_index: int, client, *, registry: dict[str, Attribute] = REGISTRY) -> dict:
    """Criteria for one entry. Raises MapperError if the model call fails or
    does not return a JSON object."""
    try:
        raw_text = client.generate(build_prompt(entry, registry), json_mode=True)
        raw = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MapperError(f"model returned invalid JSON for entry {entry_index}") from exc
    except Exception as exc:  # noqa: BLE001 -- connection, timeout, HTTP status
        raise MapperError(f"model call failed for entry {entry_index}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MapperError(f"model returned {type(raw).__name__}, not an object, for entry {entry_index}")
    return validate_criteria(
        raw,
        entry_index=entry_index,
        n_conditions=len(entry.get("conditions") or []),
        n_exceptions=len(entry.get("exceptions") or []),
        entry_quotes=entry_quotes(entry),
        entry=entry,
        relevance="direct",
        registry=registry,
    )


def map_layer(db: Session, layer: BillLayer, client, *, generated_by: str, registry: dict[str, Attribute] = REGISTRY) -> tuple[int, int, int]:
    """Map every entry of one who_it_affects layer version that is not yet
    mapped at this vocabulary and method version. Returns (stored, skipped, failed)."""
    if layer.layer != "who_it_affects":
        raise ValueError("only who_it_affects layers have criteria")
    done = set(db.execute(
        select(BillLayerCriteria.entry_index).where(
            BillLayerCriteria.bill_layer_id == layer.id,
            BillLayerCriteria.vocabulary_version == VOCABULARY_VERSION,
            BillLayerCriteria.method_version == METHOD_VERSION,
        )
    ).scalars())
    stored = skipped = failed = 0
    for i, entry in enumerate(layer.items):
        if i in done:
            skipped += 1
            continue
        try:
            criteria = map_entry(entry, i, client, registry=registry)
        except MapperError:
            failed += 1
            continue
        db.add(BillLayerCriteria(
            bill_layer_id=layer.id, entry_index=i, vocabulary_version=VOCABULARY_VERSION,
            method_version=METHOD_VERSION, generated_by=generated_by, criteria=criteria,
        ))
        stored += 1
    db.commit()
    return stored, skipped, failed
