"""Generate the Bill Says / Interpretation / Expected Effect blocks.

Model calls only, no DB access. Every rule the page depends on is enforced
in code after generation (see bill_layers_text.py), never trusted to the
prompt alone:

- Bill Says quotes must appear word for word in the text shown to the model.
- Sunshine Ledger expected effects must cite a bill section that exists and
  use conditional wording.
- Staff expected effects must use conditional wording or report staff's own
  "none" / "indeterminate" finding.

Design: docs/superpowers/specs/2026-09-23-bill-layers-design.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.pipeline.bill_layers_text import (
    bill_section_numbers,
    is_conditional,
    section_number,
    states_no_or_unknown_impact,
    verify_quotes,
)
from app.pipeline.summarize import MAX_BILL_TEXT_CHARS

# Bump a value when its prompt or guard changes in a way that should
# regenerate stored versions. Part of each block's input hash.
METHOD_VERSIONS: dict[tuple[str, str], str] = {
    ("bill_says", "bill_text"): "bill_says/bill_text/1",
    ("interpretation", "legislative_staff"): "interpretation/legislative_staff/1",
    ("interpretation", "sunshine_ledger_ai"): "interpretation/sunshine_ledger_ai/1",
    ("expected_effect", "legislative_staff"): "expected_effect/legislative_staff/1",
    ("expected_effect", "sunshine_ledger_ai"): "expected_effect/sunshine_ledger_ai/1",
}

MAX_STAFF_SECTION_CHARS = 8_000


class LayerGenerationError(RuntimeError):
    pass


@dataclass
class LayerResult:
    evidence_state: str
    scope_note: str
    items: list[dict]
    dropped: list[dict] = field(default_factory=list)


BILL_SAYS_PROMPT = """You are selecting the most important provisions of a bill, quoted exactly, for a civic transparency website.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

Pick the 2 to 4 provisions that most change what the law requires, allows, funds, or prohibits. For each, copy one sentence or clause EXACTLY as written above -- character for character, no paraphrasing, no ellipses, no added words. Give the bill section it comes from (e.g. "Section 2").

Respond with JSON only: {{"items": [{{"section_ref": "Section N", "quote": "exact text"}}]}}"""

AI_INTERPRETATION_PROMPT = """You are explaining what a bill changes, for a general public audience with no legal background.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

Write 2 to 5 plain-language statements of what this bill changes in the law. Rules:
- Each statement must be tied to the bill section it comes from (e.g. "Section 3").
- Only state what the text supports. Do not speculate about intent, motive, or politics.
- No words implying a value judgment (e.g. "harmful", "beneficial", "important").
- For each statement list the assumptions your reading depends on -- what would have to be true for the statement to hold. If there are none, use an empty list.
- List affected groups ONLY if the text names them; otherwise an empty list.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N", "assumptions": ["..."], "affected_groups": ["..."]}}]}}"""

AI_EXPECTED_EFFECT_PROMPT = """You are describing possible direct effects of a bill, for a civic transparency website.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

Describe up to 4 direct effects that follow from a specific mechanism in this bill (a requirement, prohibition, funding change, deadline, or penalty it creates or removes). Rules:
- Each effect MUST cite the bill section that creates the mechanism (e.g. "Section 3").
- Use conditional wording: "may", "could", or "is expected to". Never state an effect as certain.
- Do not predict wider economic, social, or behavioral consequences beyond the direct mechanism.
- For each effect list the assumptions it depends on.
- List affected groups ONLY if the text names them.
- If no effect can be tied to a specific section, return an empty list.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N", "assumptions": ["..."], "affected_groups": ["..."]}}]}}"""

STAFF_INTERPRETATION_PROMPT = """Below is the "effect of the bill" section of a nonpartisan Florida legislative staff analysis.

\"\"\"
{text}
\"\"\"

Condense it into 2 to 5 plain-language statements of what staff say the bill changes. Rules:
- Restate staff's reading only. Add nothing that is not in the text above.
- Tie each statement to the bill section staff refer to (e.g. "Section 3"), or null if staff don't name one.
- List affected groups only if staff name them.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N or null", "affected_groups": ["..."]}}]}}"""

STAFF_EXPECTED_EFFECT_PROMPT = """Below is the fiscal impact section of a nonpartisan Florida legislative staff analysis.

\"\"\"
{text}
\"\"\"

Restate each fiscal finding (tax/fee, private sector, state government, local government) as one plain-language statement. Rules:
- Use conditional wording ("may", "could", "is expected to") for any projected effect.
- If staff say "None", "Indeterminate", or "Insignificant", say so literally, e.g. "Staff found the private sector impact indeterminate." Do not guess.
- List any assumptions staff state. Add nothing that is not in the text above.

Respond with JSON only: {{"items": [{{"text": "...", "assumptions": ["..."]}}]}}"""


def _parse_items(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LayerGenerationError(f"model returned invalid JSON: {raw[:200]!r}") from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LayerGenerationError(f"model JSON has no items list: {raw[:200]!r}")
    return [i for i in items if isinstance(i, dict)]


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _item(raw: dict, *, quote: str | None = None, assumptions_required: bool = False) -> dict:
    assumptions = _str_list(raw.get("assumptions"))
    if assumptions_required and not assumptions:
        assumptions = ["None identified"]
    ref = raw.get("section_ref")
    return {
        "text": str(raw.get("text") or quote or "").strip(),
        "section_ref": str(ref).strip() if ref not in (None, "", "null") else None,
        "quote": quote,
        "assumptions": assumptions,
        "affected_groups": _str_list(raw.get("affected_groups")),
    }


def _truncate(full_text: str) -> tuple[str, bool]:
    return full_text[:MAX_BILL_TEXT_CHARS], len(full_text) > MAX_BILL_TEXT_CHARS


def build_bill_says(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        BILL_SAYS_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    kept, dropped = verify_quotes(raw, text)
    if not kept:
        return LayerResult("insufficient_evidence", "Quotes could not be verified against the bill text", [], dropped)
    items = [_item(k, quote=k["quote"]) for k in kept[:4]]
    for i in items:
        i["text"] = i["quote"]
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    return LayerResult("supported", scope, items, dropped)


def build_ai_interpretation(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        AI_INTERPRETATION_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    items = [_item(r, assumptions_required=True) for r in raw if str(r.get("text") or "").strip()][:5]
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    if not items:
        return LayerResult("insufficient_evidence", "No interpretation could be drawn from the bill text", [], raw)
    return LayerResult("supported", scope, items)


def build_ai_expected_effect(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        AI_EXPECTED_EFFECT_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    sections = bill_section_numbers(text)
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        item = _item(r, assumptions_required=True)
        if item["text"] and section_number(item["section_ref"]) in sections and is_conditional(item["text"]):
            kept.append(item)
        else:
            dropped.append(r)
    if not kept:
        return LayerResult("insufficient_evidence", "No effects traceable to a specific bill section", [], dropped)
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    return LayerResult("supported", scope, kept[:4], dropped)


def build_staff_interpretation(effect_section: str | None, staff_label: str, client) -> LayerResult:
    if not effect_section:
        return LayerResult("insufficient_evidence", f"{staff_label} has no Effect of Proposed Changes section", [])
    raw = _parse_items(client.generate(
        STAFF_INTERPRETATION_PROMPT.format(text=effect_section[:MAX_STAFF_SECTION_CHARS]), json_mode=True
    ))
    items = [_item(r) for r in raw if str(r.get("text") or "").strip()][:5]
    if not items:
        return LayerResult("insufficient_evidence", f"{staff_label}: nothing could be condensed", [], raw)
    return LayerResult("supported", staff_label, items)


def build_staff_expected_effect(fiscal_section: str | None, staff_label: str, client) -> LayerResult:
    if not fiscal_section:
        return LayerResult("insufficient_evidence", f"{staff_label} has no fiscal impact section", [])
    raw = _parse_items(client.generate(
        STAFF_EXPECTED_EFFECT_PROMPT.format(text=fiscal_section[:MAX_STAFF_SECTION_CHARS]), json_mode=True
    ))
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        item = _item(r)
        if item["text"] and (is_conditional(item["text"]) or states_no_or_unknown_impact(item["text"])):
            kept.append(item)
        else:
            dropped.append(r)
    if not kept:
        return LayerResult("insufficient_evidence", f"{staff_label}: no fiscal finding could be restated", [], dropped)
    return LayerResult("supported", staff_label, kept, dropped)
