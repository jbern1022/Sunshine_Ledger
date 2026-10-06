"""Validate model-proposed criteria for one Who-it-affects entry.

The mapper (a later phase) proposes; this module decides what is kept. Rules:

- Unmapped beats guessed. Anything that fails validation, or that the mapper
  never addressed, is listed in `unmapped` with a reason. Nothing is dropped
  silently: every condition and exception of the entry ends up either behind
  a requirement/exclusion or in `unmapped`.
- Every requirement points (`from`) at the condition it came from, every
  exclusion at an exception, so the quote stays in the "why" chain.
- Attributes and values come only from the registry; excluded dimensions are
  refused.

Pure functions, no database.
"""

from __future__ import annotations

from typing import Any

from app.impact_lens import guards

from app.impact_lens.vocabulary import (
    OPS_BY_TYPE, NUMBER, REGISTRY, VOCABULARY_VERSION, Attribute, is_forbidden,
)

RELEVANCES = ("direct", "indirect")


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_test(raw: Any, registry: dict[str, Attribute]) -> tuple[dict | None, str | None]:
    """Validate {attr, op, values} -> (clean test, None) or (None, reason)."""
    if not isinstance(raw, dict):
        return None, "not an object"
    attr_key, op, values = raw.get("attr"), raw.get("op"), raw.get("values")
    if not isinstance(attr_key, str):
        return None, "missing attribute"
    if is_forbidden(attr_key):
        return None, f"'{attr_key}' is an excluded dimension"
    attr = registry.get(attr_key)
    if attr is None:
        return None, f"'{attr_key}' is not in the vocabulary"
    if op not in OPS_BY_TYPE[attr.type]:
        return None, f"operator '{op}' does not fit '{attr_key}'"
    if not isinstance(values, list) or not values:
        return None, "no values"
    if attr.type == NUMBER:
        if not all(_is_number(v) for v in values):
            return None, "numeric attribute needs numbers"
        if op == "between" and not (len(values) == 2 and values[0] <= values[1]):
            return None, "'between' needs [low, high]"
        if op in ("gte", "lte") and len(values) != 1:
            return None, f"'{op}' needs one value"
    else:
        bad = [v for v in values if v not in attr.values]
        if bad:
            return None, f"{bad[0]!r} is not an allowed value of '{attr_key}'"
    return {"attr": attr_key, "op": op, "values": list(values)}, None


def _check_from(raw: Any, kind: str, count: int) -> tuple[int | None, str | None]:
    ref = raw.get("from") if isinstance(raw, dict) else None
    if not isinstance(ref, dict) or ref.get("kind") != kind:
        return None, f"must point at a {kind}"
    idx = ref.get("index")
    if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < count:
        return None, f"points at {kind} {idx!r}, which the entry does not have"
    return idx, None


def validate_criteria(
    raw: Any,
    *,
    entry_index: int,
    n_conditions: int,
    n_exceptions: int,
    entry_quotes: set[str] | None = None,
    entry: dict | None = None,
    relevance: str = "direct",
    registry: dict[str, Attribute] | None = None,
    vocabulary_version: int = VOCABULARY_VERSION,
) -> dict:
    """Return the sanitized criteria for one entry. `raw` is the mapper's
    output (any shape; garbage in gives an all-unmapped result, never an error).

    `n_conditions` / `n_exceptions` are the entry's own counts, so pointers
    can be checked. `entry_quotes` are the verified quotes an ambiguity may cite.
    When the entry itself is given, the deterministic guards in guards.py apply too.
    """
    registry = REGISTRY if registry is None else registry
    if relevance not in RELEVANCES:
        raise ValueError(f"relevance must be one of {RELEVANCES}")
    raw = raw if isinstance(raw, dict) else {}

    unmapped: list[dict] = []
    notes: list[str] = []
    # Why an item was unmapped; the first reason recorded for an index wins.
    reasons: dict[tuple[str, int], str] = {}

    def note(kind: str, idx: int | None, reason: str) -> None:
        if idx is not None:
            reasons.setdefault((kind, idx), reason)

    # --- audience: {"kind": "anyone"} or {"kind": "attr", "attr", "any_of"}
    audience: dict | None = None
    audience_unmapped: str | None = None
    a = raw.get("audience")
    if isinstance(a, dict) and a.get("kind") == "anyone":
        audience = {"kind": "anyone"}
    elif isinstance(a, dict) and a.get("kind") == "attr":
        key = a.get("attr")
        test, why = _check_test({"attr": key, "op": "in", "values": a.get("any_of")}, registry)
        if test is None:
            audience_unmapped = why
        elif not registry[test["attr"]].audience:
            audience_unmapped = f"'{test['attr']}' cannot be an audience"
        else:
            audience = {"kind": "attr", "attr": test["attr"], "any_of": test["values"]}
    else:
        audience_unmapped = "the group was not mapped"
    if audience is not None and entry is not None:
        group = str(entry.get("group") or "")
        if audience["kind"] == "anyone" and not guards.is_anyone(group):
            audience, audience_unmapped = None, f"'anyone' is only for a group the bill calls Anyone; this group is '{group}'"
        elif audience["kind"] == "attr":
            keep = guards.supported_roles(group, audience["any_of"])
            for dropped in [r for r in audience["any_of"] if r not in keep]:
                notes.append(f"audience: dropped '{dropped}' (the group '{group}' does not name it)")
            if keep:
                audience = {**audience, "any_of": keep}
            else:
                audience, audience_unmapped = None, f"the group '{group}' names none of the proposed roles"
    if audience is None and entry is not None:
        # The model's audience was missing or rejected; the group's own words
        # may still name a role outright ("County", "Landlords").
        group = str(entry.get("group") or "")
        roles = guards.supported_roles(group, list(registry["role"].values)) if "role" in registry else []
        if roles:
            audience = {"kind": "attr", "attr": "role", "any_of": roles}
            notes.append(f"audience: taken from the group's own words ('{group}'), not from the model")
    if audience is None:
        unmapped.append({"kind": "audience", "index": None, "reason": audience_unmapped})

    # --- requirements (from conditions) and exclusions (from exceptions)
    def collect(field: str, kind: str, count: int) -> list[dict]:
        kept: list[dict] = []
        items = raw.get(field)
        for item in items if isinstance(items, list) else []:
            idx, why = _check_from(item, kind, count)
            test, why2 = _check_test(item, registry)
            if idx is None or test is None:
                # A bad pointer leaves nothing to attribute the reason to.
                note(kind, idx, why or why2 or "invalid")
                continue
            if entry is not None:
                cited_item = (entry.get("conditions" if kind == "condition" else "exceptions") or [])[idx]
                text, quote = str(cited_item.get("text") or ""), str(cited_item.get("quote") or "")
                why3 = guards.too_complex(text, quote)
                if why3:
                    note(kind, idx, why3)
                    continue
                values = guards.evidenced_values(test["attr"], test["values"], f"{text} {quote}")
                for dropped in [v for v in test["values"] if v not in values]:
                    notes.append(f"{kind} {idx}: dropped '{dropped}' (the {kind} does not state it)")
                if not values:
                    note(kind, idx, f"the {kind} does not state any of the proposed values")
                    continue
                test = {**test, "values": values}
            kept.append({**test, "from": {"kind": kind, "index": idx}})
        return kept

    requires = collect("requires", "condition", n_conditions)
    excludes = collect("excludes", "exception", n_exceptions)

    # --- the mapper's own unmapped items, kept with its reasons
    given = raw.get("unmapped")
    for item in given if isinstance(given, list) else []:
        if isinstance(item, dict) and item.get("kind") in ("condition", "exception"):
            count = n_conditions if item["kind"] == "condition" else n_exceptions
            idx = item.get("index")
            if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < count:
                note(item["kind"], idx, str(item.get("reason") or "not mapped"))

    # --- completeness: every condition/exception is mapped or listed
    covered = {("condition", r["from"]["index"]) for r in requires} | {
        ("exception", r["from"]["index"]) for r in excludes
    }
    for kind, count in (("condition", n_conditions), ("exception", n_exceptions)):
        for idx in range(count):
            if (kind, idx) not in covered:
                unmapped.append({
                    "kind": kind, "index": idx,
                    "reason": reasons.get((kind, idx), "the mapper did not address it"),
                })

    # --- ambiguity: must cite one of the entry's verified quotes
    ambiguous: dict | None = None
    amb = raw.get("ambiguous")
    if amb is not None:
        question = amb.get("question") if isinstance(amb, dict) else None
        quote = amb.get("quote") if isinstance(amb, dict) else None
        if isinstance(question, str) and question.strip() and isinstance(quote, str) and quote in (entry_quotes or set()):
            ambiguous = {"question": question.strip(), "quote": quote}
        else:
            unmapped.append({"kind": "ambiguity", "index": None,
                             "reason": "an ambiguity was proposed without a verified quote"})

    return {
        "entry_index": entry_index,
        "vocabulary_version": vocabulary_version,
        "relevance": relevance,
        "audience": audience,
        "requires": requires,
        "excludes": excludes,
        "unmapped": unmapped,
        "ambiguous": ambiguous,
        "notes": notes,
    }


def is_fully_mapped(criteria: dict) -> bool:
    """True when the lens can give a definite answer from these criteria
    alone: audience mapped, nothing unmapped, no ambiguity."""
    return criteria["audience"] is not None and not criteria["unmapped"] and criteria["ambiguous"] is None


def review_tier(criteria: dict, registry: dict[str, Attribute] | None = None) -> str:
    """"simple" or "needs_review".

    Rollout (decision 4): first every mapping is shown with an "automatically
    mapped, not yet reviewed" label (option 5). The next step is to show
    "simple" mappings that way and hold the rest until a person approves
    them (option 4). A mapping is simple only when a wrong reading is unlikely
    to flip a result unnoticed: a mapped audience, only plain "is one of"
    tests, no exclusions, no unmapped items, no ambiguity, and a direct entry.
    """
    registry = REGISTRY if registry is None else registry
    if criteria["relevance"] != "direct" or criteria["ambiguous"] is not None:
        return "needs_review"
    if criteria["audience"] is None or criteria["unmapped"] or criteria["excludes"]:
        return "needs_review"
    for r in criteria["requires"]:
        if r["op"] != "in" or registry[r["attr"]].type == NUMBER:
            return "needs_review"
    return "simple"
