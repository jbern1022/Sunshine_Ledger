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
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.impact_lens import guards
from app.impact_lens.criteria import validate_criteria
from app.impact_lens.vocabulary import (
    FLORIDA_COUNTIES, MUNICIPALITY_COUNTIES, REGISTRY, VOCABULARY_VERSION, Attribute,
    county_value, municipality_value,
)
from app.models import BillLayer, BillLayerCriteria

logger = logging.getLogger(__name__)

# Two tries when the model's answer is not a JSON object. The model's failures
# are intermittent (H1389 entries 6 and 19 failed in different runs); a connection
# or timeout error is not retried here (the client already retries connections).
MAX_ATTEMPTS = 2

# Bump when the prompt or its guards change in a way that should remap.
METHOD_VERSION = "impact_lens_criteria/11"  # 11: ambiguity reasons (2026-11-27)

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
- jurisdiction: a value is "county:" or "municipality:" followed by the name, for example "county:Duval" or "municipality:Miami". Use only names that appear in the entry text. Names found there: {names}
- property_type: {property_types}

Rules
- "audience": the group ONLY, never the people it protects (those go in "affected"). {{"kind": "attr", "attr": "role", "any_of": [...]}} when the group is one of the roles. {{"kind": "anyone"}} when the group is "Anyone" / any person. null when no role fits. Never force a fit.
- "affected": the roles of the people the provision protects, benefits or burdens, other than the group itself, when the entry names them (for example an insurer that "shall disclose to every insured" affects "insured"). {{"kind": "attr", "attr": "role", "any_of": [...]}} or null. Never guess: only roles the entry's own words mention.
- "requires": one item per condition you can express with the vocabulary: {{"attr": "...", "op": "in", "values": [...], "from": {{"kind": "condition", "index": N}}}}.
- "excludes": the same for exceptions, with "from": {{"kind": "exception", "index": N}}.
- Anything you cannot express exactly (dates, dollar amounts, unit counts, anything outside the vocabulary): do not approximate. List it in "unmapped": {{"kind": "condition" or "exception", "index": N, "reason": "..."}}.
- "ambiguous": only when the entry's own words leave open who is affected, for one of these reasons:
  "undefined_term" (a key word the bill does not define), "agency_rules" (the details are left to rules an agency will adopt), "future_event" (it depends on a future date or event), "local_option" (counties, cities or school districts decide), "cross_reference" (it depends on another law the bill points to), "two_readings" (the wording supports two reasonable readings).
  Give {{"reason": "<one of those>", "question": "<the open question, naming the agency, term, date or law>", "quote": "<the one quote above that shows it, copied exactly>"}}. Otherwise null.

Respond with JSON only: {{"audience": ..., "affected": null, "requires": [], "excludes": [], "unmapped": [], "ambiguous": null}}"""


class MapperError(RuntimeError):
    pass


SALVAGE_NOTE = "salvaged: the model's answer was cut off inside 'unmapped'; ambiguity was not assessed"


def salvage(raw_text: str | None) -> dict | None:
    """Recover an answer that ran away inside its "unmapped" list.

    qwen2.5:14b sometimes keeps inventing unmapped conditions (index 0, 1, ... 113, for an entry that has
    none) until the output cap cuts it off (2026-11-26: 21-30 entries a night, retried forever). Only that
    shape is recovered: everything before "unmapped" must parse on its own, then the complete unmapped
    items are kept and the cut one dropped. "ambiguous" comes after the list, so it is unknown: the caller
    marks the result for review. A cut anywhere earlier returns None (the answer stays a failure)."""
    if not raw_text:
        return None
    m = re.search(r'"unmapped"\s*:\s*\[', raw_text)
    if not m:
        return None
    head = raw_text[:m.start()].rstrip().rstrip(",")
    try:
        obj = json.loads(head + "}")
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    items, pos, decoder = [], m.end(), json.JSONDecoder()
    while True:
        while pos < len(raw_text) and raw_text[pos] in " \t\r\n,":
            pos += 1
        try:
            item, pos = decoder.raw_decode(raw_text, pos)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            items.append(item)
    obj["unmapped"], obj["ambiguous"] = items, None
    return obj


def _numbered(items: list[dict]) -> str:
    if not items:
        return "(none)"
    lines = []
    for i, it in enumerate(items):
        # What the guards would refuse anyway is not shown: H1389 entry 19 has four
        # very long exceptions and the model answered each at length, until it was cut off.
        if guards.too_complex(str(it.get("text") or ""), str(it.get("quote") or "")):
            lines.append(f"{i}. (not shown: too long or compound to map. Leave it out.)")
        else:
            lines.append(f'{i}. {it.get("text", "")}  Quote: "{it.get("quote", "")}"')
    return "\n".join(lines)


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
    prompt = build_prompt(entry, registry)
    problem = ""
    salvaged: dict | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw_text = client.generate(prompt, json_mode=True)
        except Exception as exc:  # noqa: BLE001 -- connection, timeout, HTTP status
            raise MapperError(f"model call failed for entry {entry_index}: {exc}") from exc
        try:
            raw = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            problem = f"invalid JSON ({len(raw_text or '')} chars, starts {str(raw_text)[:80]!r}, ends {str(raw_text)[-40:]!r})"
            salvaged = salvage(raw_text) or salvaged
            continue
        if isinstance(raw, dict):
            salvaged = None  # a clean answer always wins
            break
        problem = f"{type(raw).__name__}, not an object"
    else:
        if salvaged is None:
            raise MapperError(f"model returned {problem} for entry {entry_index} after {MAX_ATTEMPTS} attempts")
        raw = salvaged
    criteria = validate_criteria(
        raw,
        entry_index=entry_index,
        n_conditions=len(entry.get("conditions") or []),
        n_exceptions=len(entry.get("exceptions") or []),
        entry_quotes=entry_quotes(entry),
        entry=entry,
        relevance="direct",
        registry=registry,
    )
    if salvaged is not None:
        criteria["notes"].append(SALVAGE_NOTE)
    return criteria


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
        except MapperError as exc:
            logger.warning("entry %d not mapped: %s", i, exc)
            failed += 1
            continue
        db.add(BillLayerCriteria(
            bill_layer_id=layer.id, entry_index=i, vocabulary_version=VOCABULARY_VERSION,
            method_version=METHOD_VERSION, generated_by=generated_by, criteria=criteria,
        ))
        stored += 1
    db.commit()
    return stored, skipped, failed
