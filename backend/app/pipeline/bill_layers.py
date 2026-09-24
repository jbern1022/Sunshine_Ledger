"""Generate the Bill Says / Interpretation / Expected Effect blocks.

Model calls only, no DB access. Every rule the page depends on is enforced
in code after generation (see bill_layers_text.py), never trusted to the
prompt alone:

- Bill Says quotes must appear word for word in the text shown to the model.
- Sunshine Ledger expected effects must cite a bill section that exists and
  use conditional wording.
- Sunshine Ledger interpretations must not turn a "should"/"may" provision
  into a requirement.
- Staff expected effects must be a real finding -- not a bare "None" /
  "Indeterminate" / "N/A" token left over from a fiscal statement's
  category list.

Design: docs/superpowers/specs/2026-09-23-bill-layers-design.md
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.pipeline.bill_layers_text import (
    bill_section_numbers,
    fiscal_option_kind,
    is_conditional,
    is_substantive_finding,
    law_as_amended,
    overstates_modal,
    restates_bill,
    section_for_quote,
    section_number,
    strip_page_artifacts,
    verify_quotes,
)
from app.pipeline.summarize import MAX_BILL_TEXT_CHARS

# Bump a value when its prompt or guard changes in a way that should
# regenerate stored versions. Part of each block's input hash.
METHOD_VERSIONS: dict[tuple[str, str], str] = {
    ("bill_says", "bill_text"): "bill_says/bill_text/4",
    ("interpretation", "legislative_staff"): "interpretation/legislative_staff/1",
    ("interpretation", "sunshine_ledger_ai"): "interpretation/sunshine_ledger_ai/6",
    ("expected_effect", "legislative_staff"): "expected_effect/legislative_staff/4",
    ("expected_effect", "sunshine_ledger_ai"): "expected_effect/sunshine_ledger_ai/5",
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

The text below is the law as it will read once this bill takes effect (struck language already removed, inserted language already merged in):
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

In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds.

Write 2 to 5 plain-language statements of what this bill changes in the law. Rules:
- Each statement must be tied to the bill section it comes from (e.g. "Section 3").
- Only state what the text supports. Do not speculate about intent, motive, or politics.
- No words implying a value judgment (e.g. "harmful", "beneficial", "important").
- For each statement list the assumptions your reading depends on -- what would have to be true for the statement to hold. If there are none, use an empty list.
- List affected groups ONLY if the text names them; otherwise an empty list.
- Keep the bill's modal strength: "shall"/"must" is a requirement, "should"/"may" is not -- never describe a "should" or "may" provision as a requirement.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N", "assumptions": ["..."], "affected_groups": ["..."]}}]}}"""

AI_EXPECTED_EFFECT_PROMPT = """You are describing the likely consequences of a bill for the people, businesses, or institutions it affects, for a civic transparency website.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds.

Describe up to 4 consequences that follow from a specific mechanism in this bill (a requirement, prohibition, funding change, deadline, or penalty it creates or removes). A consequence is something that happens to people or institutions BECAUSE of the mechanism -- it is not the mechanism itself. Do not restate what the bill says or requires, and do not just take the bill's own sentence and insert "may" into it. Rules:
- Each effect MUST cite the bill section that creates the mechanism (e.g. "Section 3").
- Use conditional wording: "may", "could", or "is expected to". Never state an effect as certain. A bare "may not" copied from the bill's own prohibition does not count as conditional wording.
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

Restate each fiscal finding as one plain-language statement. For each, give the category it belongs to: "tax_fee", "state_government", "local_government", "private_sector", or "other" for anything that does not fit those. Rules:
- These are staff's own findings, not predictions -- state them plainly, without conditional wording, even a significant negative impact.
- The fiscal text may print a list of options for a category (e.g. "None / Indeterminate / Insignificant"). Report ONLY the option staff actually selected for that category -- never restate the whole list.
- If staff say "None", "Indeterminate", or "Insignificant" for a category, write it as a full sentence naming the category, e.g. "Staff found no fiscal impact on local governments." or "Staff found the private sector impact indeterminate." Never report a bare "None" or "Indeterminate" on its own.
- List any assumptions staff state. Add nothing that is not in the text above.

Respond with JSON only: {{"items": [{{"category": "tax_fee", "text": "...", "assumptions": ["..."]}}]}}"""


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


# Assumptions that hold for every bill and so say nothing about this one, and
# the model's own ways of saying it has none.
_FILLER_ASSUMPTION = re.compile(
    r"implemented as written|without any modifications or challenges|language is clear and unambiguous"
    r"|^(?:none|n/a|none identified)\.?$",
    re.IGNORECASE,
)


def _item(raw: dict, *, quote: str | None = None, assumptions_required: bool = False) -> dict:
    assumptions = [a for a in _str_list(raw.get("assumptions")) if not _FILLER_ASSUMPTION.search(a)]
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
    # Page headers and margin line numbers go first: they split sentences
    # (so verbatim quotes fail) and waste the model's character budget.
    text = strip_page_artifacts(full_text)
    return text[:MAX_BILL_TEXT_CHARS], len(text) > MAX_BILL_TEXT_CHARS


def _dedupe_quotes(kept: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop later items whose (already-normalized) quote text repeats an earlier one."""
    seen: set[str] = set()
    unique: list[dict] = []
    dupes: list[dict] = []
    for item in kept:
        quote = item["quote"]
        if quote in seen:
            dupes.append(item)
        else:
            seen.add(quote)
            unique.append(item)
    return unique, dupes


def build_bill_says(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    amended = law_as_amended(text)
    raw = _parse_items(client.generate(
        BILL_SAYS_PROMPT.format(bill_number=bill_number, title=title, text=amended), json_mode=True
    ))
    kept, verify_dropped = verify_quotes(raw, amended)
    kept, dupe_dropped = _dedupe_quotes(kept)
    dropped = verify_dropped + dupe_dropped
    if not kept:
        note = "Quotes could not be verified against the bill text"
        if truncated:
            note += " in the first part of a long bill"
        return LayerResult("insufficient_evidence", note, [], dropped)
    items = [_item(k, quote=k["quote"]) for k in kept[:4]]
    for i in items:
        # _item() would use the model's own "text" field if it supplied one
        # instead of the quote; force it back to the verified quote. The
        # model's section_ref is unverified too, so derive it from where the
        # (now-verified) quote actually sits in the amended text.
        i["text"] = i["quote"]
        i["section_ref"] = section_for_quote(i["quote"], amended)
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    return LayerResult("supported", scope, items, dropped)


def build_ai_interpretation(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        AI_INTERPRETATION_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    sections = bill_section_numbers(law_as_amended(text))
    items: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        if not str(r.get("text") or "").strip():
            continue
        item = _item(r, assumptions_required=True)
        # The prompt asks the model to keep "should"/"may" non-binding, but
        # that's enforced here too: a statement turning a recommendation into
        # a requirement is dropped rather than published.
        if overstates_modal(item["text"], text):
            dropped.append(r)
            continue
        # A section_ref that doesn't resolve to a section this bill actually
        # has -- unparseable, or a number not present -- is cleared rather
        # than trusted; the statement itself is kept.
        if section_number(item["section_ref"]) not in sections:
            item["section_ref"] = None
        items.append(item)
    items = items[:5]
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    if not items:
        note = "No interpretation could be drawn from the bill text"
        if truncated:
            note += " in the first part of a long bill"
        return LayerResult("insufficient_evidence", note, [], raw)
    return LayerResult("supported", scope, items, dropped)


def build_ai_expected_effect(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        AI_EXPECTED_EFFECT_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    sections = bill_section_numbers(law_as_amended(text))
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        item = _item(r, assumptions_required=True)
        if (
            item["text"]
            and section_number(item["section_ref"]) in sections
            and is_conditional(item["text"])
            and not restates_bill(item["text"], text)
        ):
            kept.append(item)
        else:
            dropped.append(r)
    if not kept:
        note = "No effects traceable to a specific bill section"
        if truncated:
            note += " in the first part of a long bill"
        return LayerResult("insufficient_evidence", note, [], dropped)
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


_STAFF_FISCAL_CATEGORIES = {"tax_fee", "state_government", "local_government", "private_sector"}
_REAL_FINDING = "finding"


def build_staff_expected_effect(fiscal_section: str | None, staff_label: str, client) -> LayerResult:
    if not fiscal_section:
        return LayerResult("insufficient_evidence", f"{staff_label} has no fiscal impact section", [])
    raw = _parse_items(client.generate(
        STAFF_EXPECTED_EFFECT_PROMPT.format(text=fiscal_section[:MAX_STAFF_SECTION_CHARS]), json_mode=True
    ))
    kept: list[dict] = []
    dropped: list[dict] = []
    category_state: dict[str, str] = {}
    for r in raw:
        item = _item(r)
        if not is_substantive_finding(item["text"]):
            dropped.append(r)
            continue
        # When the fiscal analysis template prints every option for a
        # category ("None / Indeterminate / Insignificant") the model can
        # restate more than one. Real findings are always kept -- H0565 lost
        # two significant negative state findings to a keep-one-per-category
        # rule (2026-09-24). A bare option finding is dropped only when it
        # contradicts what the category already reports: a different option,
        # or a real finding ("no impact" after "a significant, negative
        # impact"). Further findings of the same option on another subject
        # are kept. "other" items are never deduped this way.
        category = str(r.get("category") or "").strip().lower()
        if category in _STAFF_FISCAL_CATEGORIES:
            kind = fiscal_option_kind(item["text"]) or _REAL_FINDING
            first = category_state.setdefault(category, kind)
            if kind != _REAL_FINDING and kind != first:
                dropped.append(r)
                continue
            if kind == _REAL_FINDING:
                category_state[category] = _REAL_FINDING
        kept.append(item)
    if not kept:
        return LayerResult("insufficient_evidence", f"{staff_label}: no fiscal finding could be restated", [], dropped)
    return LayerResult("supported", staff_label, kept, dropped)
