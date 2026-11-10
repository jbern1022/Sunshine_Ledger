"""Federal bills in the Who-it-affects layer (Todoist 6hvxx9pcxPGM66Wp, layer 2).

A federal bill can run to millions of characters, so the layer reads only the
sections that mention one of the nationwide categories the Impact Lens has
roles for: flood insurance, Medicare, small employers/businesses. The block
says so ("Read 3 of 912 sections ..."), so it is never taken for the whole
bill. Each entry is still a group, what changes for it, and a verified quote;
the mapper and the reader's own answers (kept in the browser) do the rest.

Florida relevance comes from the reader's answers, not from geography.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pipeline import bill_layers as gen
from app.pipeline.summarize import MAX_BILL_TEXT_CHARS

# category -> (label for the scope note, pattern)
CATEGORIES: dict[str, tuple[str, re.Pattern]] = {
    "flood_insurance": ("flood insurance", re.compile(r"flood insurance|National Flood Insurance|\bNFIP\b", re.IGNORECASE)),
    "medicare": ("Medicare", re.compile(r"\bMedicare\b")),
    "small_employer": ("small employers", re.compile(r"\bsmall (?:employers?|business(?:es)?)\b", re.IGNORECASE)),
}
MAX_FEDERAL_WINDOWS = 6
_HEADING = re.compile(r"(?m)^[ \t]*(SEC(?:TION)?\.[ \t]+\d+[A-Za-z0-9]*\.)")

FEDERAL_WHO_PROMPT = """You are listing who a federal bill directly applies to, for a civic transparency website.

Bill: {bill_number} — {title}

The text below is part of the bill as printed (only the sections that mention flood insurance, Medicare or small employers).
\"\"\"
{text}
\"\"\"

List up to 8 entries. Each entry is one group and one thing the bill directly changes for that group. Rules:
- "group": the specific group the provision names or defines (e.g. "Medicare beneficiaries", "Flood insurance policyholders", "Small employers"). If the provision applies to any person, write "Anyone".
- "change": what changes for that group, in plain language: an obligation, eligibility, protection, cost, service, or prohibition. Keep the bill's modal strength: "shall"/"must" is a requirement, "may" is permission.
- "change_kind": one of "obligation", "permission", "eligibility", "protection", "cost", "service", "prohibition", "other".
- "quote": the one sentence or clause from the text above that creates this change, copied EXACTLY -- character for character, no ellipses.
- "conditions": limits the text states for this entry (deadlines, thresholds, eligibility requirements), each with the exact sentence that states it. Empty list if none.
- "exceptions": exclusions the text states for this entry, each with the exact sentence that states it. Empty list if none.
- Only direct applicability. Do not describe downstream consequences (prices, behavior, supply).
- Do not invent exceptions, limits, or safeguards the text does not state. Do not state or estimate any dollar amount or number of people affected.
- One entry per distinct provision.

Respond with JSON only: {{"items": [{{"group": "...", "change": "...", "change_kind": "obligation", "quote": "exact text", "conditions": [{{"text": "...", "quote": "exact text"}}], "exceptions": [{{"text": "...", "quote": "exact text"}}]}}]}}"""


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    heading: str
    categories: tuple[str, ...]


def sections(text: str) -> list[Section]:
    """Every "SEC. N." section with the categories it mentions. Text before
    the first heading (the preamble) is not a section."""
    heads = list(_HEADING.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.start():end]
        cats = tuple(k for k, (_, rx) in CATEGORIES.items() if rx.search(body))
        out.append(Section(m.start(), end, m.group(1).rstrip("."), cats))
    return out


def relevant(text: str) -> tuple[list[Section], int]:
    all_sections = sections(text)
    return [s for s in all_sections if s.categories], len(all_sections)


def windows(text: str, limit: int = MAX_BILL_TEXT_CHARS) -> list[tuple[int, str]]:
    """(offset, text) windows made only of relevant sections, packing
    neighbours up to `limit`; a section longer than `limit` is split at line
    breaks."""
    picked, _ = relevant(text)
    units: list[tuple[int, str]] = []
    for s in picked:
        body = text[s.start:s.end]
        if len(body) <= limit:
            units.append((s.start, body))
            continue
        pos, chunk, chunk_start = s.start, "", s.start
        for line in body.splitlines(keepends=True):
            if chunk and len(chunk) + len(line) > limit:
                units.append((chunk_start, chunk))
                chunk, chunk_start = "", pos
            chunk += line
            pos += len(line)
        if chunk:
            units.append((chunk_start, chunk))
    out: list[tuple[int, str]] = []
    for offset, body in units:
        if out and len(out[-1][1]) + len(body) + 2 <= limit:
            out[-1] = (out[-1][0], out[-1][1] + "\n\n" + body)
        else:
            out.append((offset, body))
    return out


def selected_text(text: str) -> str:
    """What the layer reads, as one string: the input the layer's hash is
    taken from, so it re-versions only when a relevant section changes."""
    return "\n\n".join(body for _, body in windows(text)[:MAX_FEDERAL_WINDOWS])


def scope_note(text: str, read: int, total_windows: int) -> str:
    picked, total = relevant(text)
    labels = sorted({CATEGORIES[c][0] for s in picked for c in s.categories})
    note = f"Read {len(picked)} of {total} sections: those that mention {', '.join(labels)}. Other provisions were not analyzed"
    if read < total_windows:
        note += f" · first {read} of {total_windows} passages"
    return note


def _heading_for(quote: str, window: str) -> str | None:
    at = window.find(quote)
    last = None
    for m in _HEADING.finditer(window):
        if at != -1 and m.start() > at:
            break
        last = m
    return last.group(1).rstrip(".") if last else None


def build_federal_who(bill_number: str, title: str, full_text: str, client) -> gen.LayerResult:
    wins = windows(full_text)
    read = min(len(wins), MAX_FEDERAL_WINDOWS)
    if not wins:
        return gen.LayerResult("insufficient_evidence", "No section mentions flood insurance, Medicare or small employers", [], [])
    per_window: list[list[dict]] = []
    dropped: list[dict] = []
    for offset, window in wins[:read]:
        raw = gen._parse_items(client.generate(
            FEDERAL_WHO_PROMPT.format(bill_number=bill_number, title=title, text=window), json_mode=True))
        kept, rejected = gen._filter_entries([gen._untagged(r) for r in raw], window)
        for item in kept:
            item["section_ref"] = _heading_for(item["quote"], window)
            item["statute_ref"] = None
            item["restates_existing_law"] = False
        per_window.append(kept)
        dropped += rejected
    merged = gen._round_robin(per_window)
    kept, dupes = gen._dedupe_quotes(merged)
    for e in kept + dupes:
        e.pop("_relabeled", None)
    dropped += dupes
    kept, repeats = gen._merge_parallel(kept)
    dropped += repeats
    scope = scope_note(full_text, read, len(wins))
    if not kept:
        return gen.LayerResult("insufficient_evidence", scope + " · no group could be tied to the text", [], dropped)
    if len(kept) > gen.MAX_WHO_ENTRIES:
        scope += f" · first {gen.MAX_WHO_ENTRIES} of {len(kept)} entries"
        dropped += [{**e, "reason": "over the entry cap"} for e in kept[gen.MAX_WHO_ENTRIES:]]
    return gen.LayerResult("supported", scope, kept[:gen.MAX_WHO_ENTRIES], dropped)
