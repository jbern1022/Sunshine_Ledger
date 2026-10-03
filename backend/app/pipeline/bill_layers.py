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
- Who it affects entries must rest on a verified quote, state no condition
  or exception the bill doesn't, and describe direct applicability only.

Design: docs/superpowers/specs/2026-09-23-bill-layers-design.md
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.pipeline.bill_layers_text import (
    applicability_exclusions,
    change_regions,
    bill_section_numbers,
    fiscal_option_kind,
    is_conditional,
    is_substantive_finding,
    law_as_amended,
    normalize_ws,
    overstates_modal,
    quote_position,
    restates_bill,
    restates_existing_law,
    section_for_quote,
    section_number,
    statute_at,
    strip_page_artifacts,
    verify_quotes,
    within,
)
from app.pipeline.effective_date import provision_dates
from app.pipeline.summarize import MAX_BILL_TEXT_CHARS

_BILL_SECTION_HEADING = re.compile(r"(?m)^\s*Section\s+\d+\.(?!\d)", re.IGNORECASE)

# Bump a value when its prompt or guard changes in a way that should
# regenerate stored versions. Part of each block's input hash.
METHOD_VERSIONS: dict[tuple[str, str], str] = {
    ("bill_says", "bill_text"): "bill_says/bill_text/4",
    ("interpretation", "legislative_staff"): "interpretation/legislative_staff/1",
    ("interpretation", "sunshine_ledger_ai"): "interpretation/sunshine_ledger_ai/6",
    ("expected_effect", "legislative_staff"): "expected_effect/legislative_staff/4",
    ("expected_effect", "sunshine_ledger_ai"): "expected_effect/sunshine_ledger_ai/5",
    ("who_it_affects", "sunshine_ledger_ai"): "who_it_affects/sunshine_ledger_ai/5",
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


WHO_IT_AFFECTS_PROMPT = """You are listing who a bill directly applies to, for a civic transparency website.

Bill: {bill_number} — {title}

The text below is the law as it will read once this bill takes effect (struck language already removed, inserted language already merged in).{changes}
\"\"\"
{text}
\"\"\"

List up to 8 entries. Each entry is one group and one thing the bill directly changes for that group. Rules:
- "group": the specific group the provision names or defines (e.g. "Landlords", "County tax collectors"). If the provision applies to any person (as most criminal offenses do), write "Anyone" -- that broad coverage is what the text says.
- "change": what changes for that group, in plain language: an obligation, eligibility, protection, cost, service, or prohibition. Keep the bill's modal strength: "shall"/"must" is a requirement, "may" is permission.
- "change_kind": one of "obligation", "permission", "eligibility", "protection", "cost", "service", "prohibition", "other". A "may" provision is a permission, not an obligation.
- "quote": the one sentence or clause from the text above that creates this change, copied EXACTLY -- character for character, no ellipses. Quote the law itself (from "Section 1." on), never the bill's title or summary paragraph.
- "conditions": limits the text states for this entry (geography, deadlines, thresholds, eligibility requirements), each with the exact sentence that states it. Not the bill's effective date -- that is shown separately. Empty list if none.
- "exceptions": exclusions the text states for this entry, each with the exact sentence that states it. Empty list if none.
- Only direct applicability. Do not describe downstream consequences (prices, behavior, supply) -- those are not what the provision changes.
- Do not invent exceptions, limits, or safeguards the text does not state, even if they seem likely or intended.
- The same group may appear in more than one entry if the bill affects it in different roles.

Respond with JSON only: {{"items": [{{"group": "...", "change": "...", "change_kind": "obligation", "quote": "exact text", "conditions": [{{"text": "...", "quote": "exact text"}}], "exceptions": [{{"text": "...", "quote": "exact text"}}]}}]}}"""


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


def _law_text(full_text: str) -> str:
    """The bill from its first "Section N." heading on. A Florida bill opens
    with a title paragraph paraphrasing every change ("amending s. 641.26,
    F.S.; revising requirements ..."): quoting it is quoting a summary, and
    it can fill most of the window (HB 1389: 2,540 of 12,000 chars; H1141:
    all of it). The bill's name reaches the prompt separately. Text with no
    section headings (a resolution, an agenda item) is used whole."""
    # Page headers and margin line numbers go first: they split sentences
    # (so verbatim quotes fail) and waste the model's character budget.
    text = strip_page_artifacts(full_text)
    first = _BILL_SECTION_HEADING.search(text)
    return text[first.start():].lstrip() if first else text


def _truncate(full_text: str) -> tuple[str, bool]:
    text = _law_text(full_text)
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


_CHANGE_KINDS = {"obligation", "permission", "eligibility", "protection", "cost", "service", "prohibition", "other"}

# The page shows the effective date on its own (effective_date.py); as a
# "condition" it only repeats it, so it is never one.
_EFFECTIVE_DATE_CLAUSE = re.compile(
    r"\b(?:this|the) (?:act|ordinance|resolution)\b[^.]{0,120}?\b(?:takes?|becomes?|shall become) (?:effect|effective)\b",
    re.IGNORECASE,
)
# A requirement in the entry must rest on a mandatory quote. Found
# 2026-10-01: H1279 "a county may not impose any requirement ... other than
# requiring proof" was restated as "must require proof".
_REQUIRES = re.compile(r"\b(?:must(?! not)|shall(?! not)|(?:is|are) required to)\b", re.IGNORECASE)
_MANDATORY = re.compile(r"\b(?:shall|must|(?:is|are) required)\b", re.IGNORECASE)
_PERMITS = re.compile(r"\bmay\b(?!\s+not\b)", re.IGNORECASE)


# Who it affects reads the whole bill, a window of whole sections at a time
# (HB 1389 validation, 2026-10-02: one 12,000-char window showed the model
# Section 1 of 13). Each window is one model call on the nightly GPU, so a
# very long bill is read up to this many windows, and the block says which
# sections that covered.
MAX_WHO_WINDOWS = 4
# Entries kept per bill; the page shows the first 6 and folds the rest.
MAX_WHO_ENTRIES = 12
_SECTION_NUMBER = re.compile(r"Section\s+(\d+)\.", re.IGNORECASE)


def _windows(law: str, limit: int = MAX_BILL_TEXT_CHARS) -> list[tuple[int, str]]:
    """(offset, text) windows of at most `limit` chars, packing consecutive
    "Section N." sections; a section longer than that is split at line
    breaks (and a single line longer still, at `limit`)."""
    starts = [m.start() for m in _BILL_SECTION_HEADING.finditer(law)]
    if not starts or starts[0] != 0:
        starts.insert(0, 0)
    units: list[tuple[int, str]] = []
    for a, b in zip(starts, starts[1:] + [len(law)]):
        if b - a <= limit:
            units.append((a, law[a:b]))
            continue
        pos = a
        for line in law[a:b].splitlines(keepends=True):
            for i in range(0, len(line), limit):
                units.append((pos + i, line[i:i + limit]))
            pos += len(line)
    windows: list[tuple[int, str]] = []
    for offset, text in units:
        if windows and len(windows[-1][1]) + len(text) <= limit:
            windows[-1] = (windows[-1][0], windows[-1][1] + text)
        else:
            windows.append((offset, text))
    return [w for w in windows if w[1].strip()]


def _section_at(law: str, offset: int) -> str | None:
    """The number of the section in force at `offset` in `law`: the last
    heading at or before it."""
    last = None
    for m in _BILL_SECTION_HEADING.finditer(law):
        if m.start() > offset:
            break
        last = m
    return _SECTION_NUMBER.search(law, last.start()).group(1) if last else None


def _sections_read(law: str, windows: list[tuple[int, str]], read: int) -> str:
    """'Sections 1-4 of 8' for the first `read` windows of `law`."""
    first = _section_at(law, windows[0][0])
    last = _section_at(law, windows[read - 1][0] + len(windows[read - 1][1]) - 1)
    total = _section_at(law, len(law))
    if not (first and last and total):
        return "the first part of a long bill"
    return f"Sections {first}-{last} of {total}"


# F2 (HB 1389 re-validation, 2026-10-02): shown the law with no sign of
# what changed, the model spent 7 of 11 entries on existing law.
_CHANGES_NOTE = (
    " Text between <new> and </new> is what this bill adds; <removed/> marks where it deletes text."
    " List what this bill changes first: new or altered obligations, permissions, eligibility, protections,"
    " prohibitions. Include a provision the bill leaves unchanged only when it is needed to understand a change,"
    " and no more than 2 of those. Copy quotes without the <new>, </new> and <removed/> tags."
)
_TAG = re.compile(r"</?new>|<removed/>")


def _marked(window: str, offset: int, regions: list[tuple[int, int]]) -> str:
    """The window with inserted spans wrapped in <new>...</new> and deletion
    points marked <removed/> (regions are positions in the whole law)."""
    inserts: list[tuple[int, int, str]] = []  # (position, order, tag)
    end = offset + len(window)
    for a, b in regions:
        if a == b:
            if offset <= a <= end:
                inserts.append((a - offset, 1, "<removed/>"))
        elif a < end and b > offset:
            inserts.append((max(a, offset) - offset, 2, "<new>"))
            inserts.append((min(b, end) - offset, 0, "</new>"))
    out, last = [], 0
    for pos, _, tag in sorted(inserts):
        out.append(window[last:pos])
        out.append(tag)
        last = pos
    out.append(window[last:])
    return "".join(out)


def _untagged(raw: dict) -> dict:
    """The model's entry with any copied tags taken out of its quotes."""
    def clean(s):
        return _DOUBLE_SPACE.sub(" ", _TAG.sub("", s)) if isinstance(s, str) else s

    out = {**raw, "quote": clean(raw.get("quote"))}
    for key in ("conditions", "exceptions"):
        if isinstance(raw.get(key), list):
            out[key] = [{**c, "quote": clean(c.get("quote"))} if isinstance(c, dict) else c for c in raw[key]]
    return out


_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")


def _round_robin(groups: list[list[dict]]) -> list[dict]:
    """Interleave per-window entries so the cap can't fill from Section 1 alone."""
    merged: list[dict] = []
    for i in range(max((len(g) for g in groups), default=0)):
        merged.extend(g[i] for g in groups if i < len(g))
    return merged


# Title-paragraph phrasing, should one slip past _law_text (no headings).
_TITLE_STYLE = re.compile(r"\bamending s(?:s)?\.\s*[\d.]+,\s*F\.S\.;|^(?:requiring|prohibiting|authorizing|revising|providing|creating|removing|specifying)\b", re.IGNORECASE)
_NEGATED_MODAL = re.compile(r"\b(?:may|shall|must|can)\s+not\b|\bcannot\b", re.IGNORECASE)
# What a quote needs to back a "may not" entry. A bare "not" isn't enough:
# "... not to exceed 10 stories" is a limit on a permission.
_PROHIBITS = re.compile(
    r"\b(?:may|shall|must|can)\s+not\b|\bcannot\b|\bunlawful\b|\bprohibit\w*|\bno\s+(?:\w+\s+){0,3}(?:may|shall)\b"
    # A criminal offense prohibits by penalty: "A person who ... commits a
    # misdemeanor of the first degree".
    r"|\bcommits\s+(?:a|an)\b|\bis\s+guilty\s+of\b|\bis\s+subject\s+to\s+a\s+(?:civil\s+)?(?:penalty|fine)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(?:not|no|never|unlawful|prohibit\w*|may not|shall not)\b", re.IGNORECASE)

# Who it affects is direct applicability only. A consequence -- rents rising,
# fewer permits -- needs its own evidence and belongs in Expected Effect.
# Plain "may" is not here: "may apply for a grant" is eligibility.
_DOWNSTREAM = re.compile(
    r"\b(?:could|might|would|likely|(?:is|are) expected to|may (?:lead|result|cause|increase|decrease|reduce|rise|fall|raise|lower))\b",
    re.IGNORECASE,
)


def _verified_clauses(raw, amended: str) -> tuple[list[dict], list[dict]]:
    """Conditions or exceptions whose quote is in the bill, and the ones
    dropped. An unquoted or unverifiable one is dropped: the page never
    states a limit or exception the bill doesn't."""
    if not isinstance(raw, list):
        return [], []
    candidates = [c for c in raw if isinstance(c, dict) and str(c.get("text") or "").strip()]
    kept, dropped = verify_quotes(candidates, amended)
    return [
        {"text": str(c["text"]).strip(), "quote": c["quote"]}
        for c in kept
        if not _EFFECTIVE_DATE_CLAUSE.search(c["quote"])
    ], dropped


_IS_RULE = re.compile(r"\b(?:must|shall|may|is\s+required|are\s+required)\b", re.IGNORECASE)
_CONDITION_LEAD = re.compile(r"^\W*(?:if|unless|when|where|provided|only|so\s+long\s+as|on\s+condition)\b", re.IGNORECASE)


# A condition the entry's own quote states (R3, HB 1389 validation): "...
# regardless of the underlying zoning, if at least 40 percent of the
# residential units ... are affordable" came back with conditions: [].
_CONDITION_MARKER = re.compile(
    r"\b(?:only if|only when|if|unless|provided that|so long as|on condition that)\b", re.IGNORECASE
)


def _quoted_condition(quote: str, conditions: list[dict]) -> dict | None:
    """The clause from the quote's first condition marker to the next
    semicolon or the end, unless a listed condition already covers it. A
    quote that opens with the marker ("If the proposed development is
    adjacent to ...") is conditional as a whole and already shown; where its
    condition ends can't be told from commas, so nothing is added."""
    m = _CONDITION_MARKER.search(quote)
    if not m or not quote[:m.start()].strip():
        return None
    clause = re.split(r";\s", quote[m.start():], maxsplit=1)[0].rstrip(" .,")
    norm = normalize_ws(clause).lower()
    for c in conditions:
        listed = normalize_ws(c["quote"]).lower()
        if listed in norm or norm in listed:
            return None
    return {"text": clause[0].upper() + clause[1:], "quote": clause}


def build_who_it_affects(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    """Who the bill directly applies to: group, what changes, the provision
    that changes it (verified quote), and the conditions and exceptions the
    text states. Status-dependent wording ("would apply" / "applies") is the
    page's job, from the bill's current status, so it can't go stale here.
    Agreed rules: Data Model v1, "Scope and Affected Population"."""
    law, regions = change_regions(_law_text(full_text))
    if law != law_as_amended(_law_text(full_text)):
        regions = []  # never label from a text the model didn't see
    windows = _windows(law)
    read = min(len(windows), MAX_WHO_WINDOWS)
    per_window: list[list[dict]] = []
    dropped: list[dict] = []
    for offset, window in windows[:read]:
        shown = _marked(window, offset, regions) if regions else window
        kept, rejected = _who_entries(bill_number, title, window, client, shown=shown, marked=bool(regions))
        for item in kept:
            item["section_ref"] = _section_ref(item["quote"], window, law, offset)
            at = quote_position(item["quote"], window)
            item["statute_ref"] = statute_at(law, None if at is None else offset + at)
            item["restates_existing_law"] = restates_existing_law(law, regions, item["quote"])
        per_window.append(kept)
        dropped += rejected
    kept, dupes = _dedupe_quotes(_round_robin(per_window))
    dropped += dupes
    _attach_exclusions(kept, applicability_exclusions(law))
    _attach_dates(kept, provision_dates(_law_text(full_text)))
    kept = _merge_parallel(kept)
    # What the bill changes first, so the cap never keeps restated law over
    # a change (F2); the order is otherwise kept.
    kept.sort(key=lambda e: bool(e.get("restates_existing_law")))
    partial = read < len(windows)
    if not kept:
        note = "No group the bill directly applies to could be tied to its text"
        if partial:
            note += f" in {_sections_read(law, windows, read)}"
        return LayerResult("insufficient_evidence", note, [], dropped)
    scope = _sections_read(law, windows, read) if partial else "Bill text"
    if len(kept) > MAX_WHO_ENTRIES:
        scope += f" · first {MAX_WHO_ENTRIES} of {len(kept)} entries"
    return LayerResult("supported", scope, kept[:MAX_WHO_ENTRIES], dropped)


# Florida's county (ch. 125) and municipal (ch. 166) statutes often carry the
# same rule word for word; one entry names both (R9, HB 1389 validation).
_LOCAL_GOVERNMENT = re.compile(r"\b(?:count(?:y|ies)|municipalit(?:y|ies))(?:'s)?\b", re.IGNORECASE)


def _merge_parallel(entries: list[dict]) -> list[dict]:
    """Fold an entry into an earlier one whose quote is the same once
    "county"/"municipality" are set aside: one entry, both groups, the
    second citation kept under also_in, conditions and exceptions merged."""
    merged: list[dict] = []
    by_key: dict[str, dict] = {}
    for entry in entries:
        entry.setdefault("also_in", [])
        quote = normalize_ws(entry["quote"]).lower()
        key = _LOCAL_GOVERNMENT.sub("<local>", quote)
        # The model may quote one version further than the other: a key
        # inside the other counts as the same rule.
        first = next((e for k, e in by_key.items() if key in k or k in key), None) if key != quote else None
        if first is None or first["also_in"] or first["group"] == entry["group"]:
            by_key.setdefault(key, entry)
            merged.append(entry)
            continue
        first["also_in"].append({k: entry.get(k) for k in ("quote", "section_ref", "statute_ref")})
        first["affected_groups"] = first["affected_groups"] + [entry["group"]]
        pair = sorted(g.lower().rstrip("s").replace("countie", "county").replace("municipalitie", "municipality")
                      for g in first["affected_groups"])
        first["group"] = (
            "Counties and municipalities" if pair == ["county", "municipality"]
            else f"{first['group']} and {entry['group'][:1].lower()}{entry['group'][1:]}"
        )
        for field_name in ("conditions", "exceptions"):
            seen = [normalize_ws(x["quote"]).lower() for x in first[field_name]]
            for x in entry[field_name]:
                q = normalize_ws(x["quote"]).lower()
                if not any(q in kept for kept in seen):  # already said, or inside a kept block
                    first[field_name].append(x)
                    seen.append(q)
        first["restates_existing_law"] = bool(first.get("restates_existing_law") and entry.get("restates_existing_law"))
    return merged


# F4 (HB 1389 re-validation): the group must be who the quote names. 760.35(4)
# "If the court finds ... it must issue an order" came back as "Person";
# 760.26 "It is unlawful to discriminate in land use decisions" as "Landlord".
_GENERIC_GROUP = re.compile(r"^(?:anyone|any\s+person|persons?|people|everyone|individuals?)$", re.IGNORECASE)
_ANYONE_QUOTE = re.compile(
    r"^\W*(?:it\s+is\s+unlawful|(?:a|any|no)\s+person\b|anyone|whoever|every\s+person)", re.IGNORECASE
)
_PREPOSITIONS = {"of", "in", "on", "by", "for", "to", "with", "under", "from", "at", "as", "or", "and"}
_SUBJECT = re.compile(
    r"\b(?:a|an|the|each|any|every)\s+(?P<noun>(?:[a-z-]+\s+)?[a-z-]+)\s+(?:may|shall|must|is\s+required|are\s+required)\b",
    re.IGNORECASE,
)
_PRONOUN_SUBJECT = re.compile(r"\b(?:it|they)\s+(?:may|shall|must)\b", re.IGNORECASE)
_DEFINITE = re.compile(r"\bthe\s+(?P<noun>[a-z-]+)\b", re.IGNORECASE)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", text.lower())}


def _plural(noun: str) -> str:
    words = noun.split()
    last = words[-1]
    if last.endswith("y") and last[-2:-1] not in "aeiou":
        last = last[:-1] + "ies"
    elif last.endswith(("s", "x", "ch", "sh")):
        last += "es"
    else:
        last += "s"
    out = " ".join(words[:-1] + [last])
    return out[:1].upper() + out[1:]


def _quote_subject(quote: str) -> str | None:
    """Who the quote's main clause binds: "A county must ..." -> "Counties";
    "If the court finds ... it must ..." -> "Courts"; "It is unlawful to ..."
    or "A person who ..." -> "Anyone"; None when it can't be told."""
    if _ANYONE_QUOTE.search(quote):
        return "Anyone"
    for m in _SUBJECT.finditer(quote):
        noun = m.group("noun").lower()
        if not set(noun.split()) & _PREPOSITIONS and noun.split()[-1] not in {"person", "persons"}:
            return _plural(noun)
        if noun.split()[-1] in {"person", "persons"}:
            return "Anyone"
    pronoun = _PRONOUN_SUBJECT.search(quote)
    if pronoun:
        antecedent = _DEFINITE.search(quote, 0, pronoun.start())
        if antecedent:
            return _plural(antecedent.group("noun").lower())
    return None


# A sentence's end; "s. 333.03" and "ss. 380.055" are citations.
_SENTENCE_END = re.compile(r"(?<!\bs)(?<!\bss)\.(?=\s|$)")
# Where a sentence can start: after one ends, after a statute catchline
# ("760.26 Prohibited discrimination ...—It is unlawful"), or after a
# "... amended to read:" lead-in.
_SENTENCE_BREAK = re.compile(r"(?<!\bs)(?<!\bss)\.(?=\s|$)|—|:\s*\n")


def _sentence_around(quote: str, window: str) -> str:
    """The whole sentence a (possibly fragmentary) quote sits in, so a
    fragment like "may notify the county ... by July 1, 2026" is read with
    its subject ("An applicant ... may notify")."""
    at = quote_position(quote, window)
    if at is None:
        return quote
    start = 0
    for m in _SENTENCE_BREAK.finditer(window, 0, at):
        start = m.end()
    end = _SENTENCE_END.search(window, at + len(quote) - 1)
    return normalize_ws(window[start:end.end() if end else len(window)])


def _grounded_group(group: str, quote: str, window: str) -> str | None:
    """The entry's group if its sentence supports it, else the sentence's own
    subject, else None (the entry can't be tied to anyone the bill names)."""
    sentence = _sentence_around(quote, window)
    sentence = re.sub(r"^Section\s+\d+\.\s*", "", sentence)
    subject = _quote_subject(sentence)
    if _GENERIC_GROUP.match(group.strip()):
        return subject or group
    if _stems(group) & _stems(sentence):
        return group
    return subject


def _attach_exclusions(entries: list[dict], exclusions: list[dict]) -> None:
    """Add each "does not apply to" provision to the entries it governs,
    unless the entry already lists it (R4, HB 1389 validation)."""
    for entry in entries:
        ref = entry.get("statute_ref") or entry.get("section_ref")
        for exclusion in exclusions:
            if not any(within(ref, scope) for scope in exclusion["scopes"]):
                continue
            quote = normalize_ws(exclusion["quote"]).lower()
            listed = [normalize_ws(x["quote"]).lower() for x in entry["exceptions"]]
            if any(quote in q for q in listed):
                continue
            # The whole block replaces any of its items listed one by one (F5).
            entry["exceptions"] = [x for x, q in zip(entry["exceptions"], listed) if q not in quote]
            entry["exceptions"].append({"text": normalize_ws(exclusion["quote"]), "quote": exclusion["quote"]})


_DATE_LABEL = {
    "retroactive": "Applies retroactively to {when}",
    "tax_roll": "First applies to {when}",
    "expires": "Expires {when}",
    "takes_effect": "Takes effect {when}",
    "deadline": "Deadline: {when}",
}


def _attach_dates(entries: list[dict], dates: list[dict]) -> None:
    """A provision's own date (R8, HB 1389 validation) becomes a condition
    of the entries it governs, unless the entry's quote already states it."""
    for entry in entries:
        ref = entry.get("statute_ref") or entry.get("section_ref")
        for d in dates:
            if not any(within(ref, scope) or ref == scope for scope in d["scopes"]):
                continue
            quote = normalize_ws(d["quote"]).lower()
            own = [normalize_ws(entry["quote"]).lower()] + [normalize_ws(c["quote"]).lower() for c in entry["conditions"]]
            if any(q in quote or quote in q for q in own):
                continue
            entry["conditions"].append({"text": _DATE_LABEL[d["kind"]].format(when=d["when"]), "quote": d["quote"]})


def _section_ref(quote: str, window: str, law: str, offset: int) -> str | None:
    """The section a quote sits in, located in the window it came from (the
    same sentence can recur in another section); a window that opens
    mid-section takes the heading in force where it starts."""
    ref = section_for_quote(quote, window)
    if ref:
        return ref
    number = _section_at(law, offset)
    return f"Section {number}" if number else None


def _who_entries(
    bill_number: str, title: str, window: str, client, *, shown: str | None = None, marked: bool = False
) -> tuple[list[dict], list[dict]]:
    """One model call on one window of the law (`shown`: with change tags);
    every guard runs against the untagged window, so an entry can only cite
    text the model was shown."""
    raw = _parse_items(client.generate(
        WHO_IT_AFFECTS_PROMPT.format(
            bill_number=bill_number, title=title, text=shown or window, changes=_CHANGES_NOTE if marked else "",
        ),
        json_mode=True,
    ))
    raw = [_untagged(r) for r in raw]
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        group = str(r.get("group") or "").strip()
        change = str(r.get("change") or "").strip()
        if not group or not change:
            continue
        verified, _ = verify_quotes([r], window)
        if (
            not verified
            or _EFFECTIVE_DATE_CLAUSE.search(verified[0]["quote"])
            or _DOWNSTREAM.search(change)
            or overstates_modal(change, window)
            or (_REQUIRES.search(change) and not _MANDATORY.search(verified[0]["quote"]))
            or _TITLE_STYLE.search(verified[0]["quote"])
            # A "prohibition" worded as a bare permission is a misreading
            # (S0814: "Anyone [prohibition]: may possess any firearm ...").
            or (str(r.get("change_kind") or "").lower() == "prohibition" and not _NEGATION.search(change))
            # The reverse: a bare permission restated as a prohibition (HB 1389,
            # 2026-10-02: "the county may restrict the height ... to 150
            # percent" became "may not restrict the height ...").
            or (_NEGATED_MODAL.search(change) and not _PROHIBITS.search(verified[0]["quote"]))
        ):
            dropped.append(r)
            continue
        quote = verified[0]["quote"]
        grounded = _grounded_group(group, quote, window)
        if grounded is None:
            dropped.append(r)
            continue
        group = grounded
        conditions, bad_conditions = _verified_clauses(r.get("conditions"), window)
        # A "condition" that is itself a rule ("... at least 65 percent ...
        # must be used for residential purposes") is a separate provision,
        # not a limit on this one (F5, HB 1389).
        rules = [c for c in conditions if _IS_RULE.search(c["quote"]) and not _CONDITION_LEAD.match(c["quote"])]
        conditions = [c for c in conditions if c not in rules]
        bad_conditions = bad_conditions + rules
        exceptions, bad_exceptions = _verified_clauses(r.get("exceptions"), window)
        dropped += [{"dropped": "condition", "group": group, **c} for c in bad_conditions]
        dropped += [{"dropped": "exception", "group": group, **c} for c in bad_exceptions]
        stated = _quoted_condition(quote, conditions)
        if stated:
            conditions.append(stated)
        kind = str(r.get("change_kind") or "").strip().lower()
        kind = kind if kind in _CHANGE_KINDS else "other"
        if kind == "obligation" and not _REQUIRES.search(change) and _PERMITS.search(change):
            kind = "permission"
        kept.append({
            "text": change,
            "group": group,
            "change_kind": kind,
            "quote": quote,
            "section_ref": None,
            "statute_ref": None,
            "conditions": conditions,
            "exceptions": exceptions,
            "assumptions": [],
            "affected_groups": [group],
        })
    return kept, dropped


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
