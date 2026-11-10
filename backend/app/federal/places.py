"""Florida places named in a federal bill's text (Todoist 6hvxx9pcxPGM66Wp,
layer 1: direct Florida geography).

Rule-based, not a model: a place is found only if its name is in the text,
and the finding carries the sentence it is in, copied exactly, with its
offsets. Findings are labelled automatically found and not reviewed.

What counts:
- Florida itself ("Florida", "State of Florida"), except the Washington
  street ("Florida Avenue").
- A Florida county: "<Name> County, Florida", or "<Name> County" when the
  same sentence also says Florida.
- A Florida city, town or village written as "<Name>, Florida" (or ", FL").
- Any other "<Proper Name>, Florida" (bases, ports, parks), kept as a named
  place.
- Well-known Florida places that bills name without the state (Everglades,
  Kennedy Space Center, ...), from the curated list below.
- Federal disaster declarations for Florida (DR-4673-FL).

Not covered: earmark tables in appropriations reports (a separate data
source), places that appear only as a bare city name with no state, and
anything in an image. Every one of those is a missed place, never a wrong one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.impact_lens.vocabulary import FLORIDA_COUNTIES, MUNICIPALITY_COUNTIES

METHOD_VERSION = "fl-places-v1"
MAX_FINDINGS = 300

# Curated: names that identify a Florida place without saying "Florida".
NAMED_PLACES = (
    "Everglades National Park", "Everglades", "Florida Keys", "Biscayne National Park", "Biscayne Bay",
    "Big Cypress National Preserve", "Dry Tortugas", "Lake Okeechobee", "Indian River Lagoon", "Kennedy Space Center",
    "Cape Canaveral", "Eglin Air Force Base", "MacDill Air Force Base", "Tyndall Air Force Base", "Patrick Space Force Base",
    "Naval Air Station Pensacola", "Naval Air Station Jacksonville", "Naval Air Station Whiting Field", "Naval Station Mayport",
    "Hurlburt Field", "Homestead Air Reserve Base", "PortMiami", "Port Everglades", "Port Tampa Bay", "JAXPORT",
    "Apalachicola Bay", "Apalachicola River", "Choctawhatchee Bay", "Tampa Bay", "St. Johns River", "Caloosahatchee River",
    "Kissimmee River", "Florida Everglades",
)

_DISASTER = re.compile(r"\b(?:DR|EM|FM)-\d{3,5}-FL\b")
_STATE = re.compile(r"\bFlorida\b(?!\s+Ave(?:nue)?\b)")
_STATE_SUFFIX = re.compile(r",\s+(?:Florida|FL)\b")
_PHRASE_AT_END = re.compile(
    r"((?:[A-Z][A-Za-z.'’\-]*|St\.)(?:\s+(?:(?:of|the|and|de|la|del)\s+)?(?:[A-Z][A-Za-z.'’\-]*|St\.))*)\s*$"
)
US_STATES = frozenset(
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Georgia Hawaii Idaho Illinois Indiana Iowa "
    "Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada "
    "Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming Guam Samoa "
    "Carolina Dakota Mexico Hampshire Jersey York Island Rico".split()
)
_ABBREV = r"(?<!U\.S)(?<!St)(?<!Sec)(?<!No)(?<!Mr)(?<!Mrs)(?<!Dr)(?<!Inc)(?<!Co)(?<!Jr)(?<!Sr)"
_SENTENCE_END = re.compile(_ABBREV + r"\.\s+(?=[A-Z(\"“`])")
_TABLE_LINE = re.compile(r"\.{4,}|\S\s{3,}[$\d(]")  # dot leaders, or a gap before a number column
_SECTION = re.compile(r"^\s*(SEC(?:TION)?\.?\s+\d+[A-Za-z]?\.?[^\n]{0,120})", re.MULTILINE)
_COUNTY_RES = {
    c: re.compile(rf"\b{re.escape(c)} County\b(?:\s*,\s*(?:Florida|FL)\b)?") for c in FLORIDA_COUNTIES
}
_NAMED_RES = [(n, re.compile(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])")) for n in NAMED_PLACES]


@dataclass(frozen=True)
class Finding:
    kind: str
    matched_term: str
    counties: tuple[str, ...]
    section: str | None
    quote_text: str
    char_start: int
    char_end: int


_PREFIX = re.compile(r"^(?:(?:City|Town|Village|Port)\s+of\s+|The\s+)", re.IGNORECASE)


def _as_place(phrase: str) -> tuple[str, int]:
    """The place a "<Words>, Florida" phrase names, and where in the phrase it
    starts: 'City of Tampa' is Tampa, 'for Fort Lauderdale' is Fort Lauderdale.
    The longest tail that is a known municipality wins; otherwise the phrase
    itself, minus a leading 'City of' / 'The'."""
    spans = [(m.start(), m.group(0)) for m in re.finditer(r"\S+", phrase)]
    for i, (start, _) in enumerate(spans):
        tail = " ".join(w for _, w in spans[i:])  # a line break inside the phrase reads as a space
        if tail in MUNICIPALITY_COUNTIES:
            return tail, start
    flat = " ".join(w for _, w in spans)
    cleaned = _PREFIX.sub("", flat)
    # the offset only matters for choosing the sentence, so the leading
    # words dropped are a good enough measure of where the name starts
    return cleaned, max(len(flat) - len(cleaned), 0)


def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    """The sentence around `pos`, or the table row when the line is part of a
    table. Sentences run across line breaks (the text is printed wrapped)."""
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    line_end = len(text) if line_end == -1 else line_end
    if _TABLE_LINE.search(text[line_start:line_end]):
        start, end = line_start, line_end
    else:
        p_start = text.rfind("\n\n", 0, pos)
        p_start = 0 if p_start == -1 else p_start + 2
        p_end = text.find("\n\n", pos)
        p_end = len(text) if p_end == -1 else p_end
        start = p_start
        for m in _SENTENCE_END.finditer(text, max(p_start, pos - 700), pos):
            start = m.end()
        m = _SENTENCE_END.search(text, pos, min(p_end, pos + 700))
        end = m.start() + 1 if m else p_end
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end - start > 600:  # a run-on: keep a window around the match
        start, end = max(start, pos - 250), min(end, pos + 350)
    return start, end


def _section_for(text: str, pos: int, sections: list[tuple[int, str]]) -> str | None:
    label = None
    for start, name in sections:
        if start > pos:
            break
        label = name
    return label


def find_places(text: str) -> list[Finding]:
    """Every Florida place the text names, once per sentence and term, in
    reading order."""
    sections = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip()[:200]) for m in _SECTION.finditer(text)]
    raw: list[tuple[int, str, str, tuple[str, ...]]] = []  # pos, kind, term, counties

    for m in _DISASTER.finditer(text):
        raw.append((m.start(), "disaster", m.group(0), ()))
    for county, rx in _COUNTY_RES.items():
        for m in rx.finditer(text):
            with_state = bool(re.search(r"(?:Florida|FL)\s*$", m.group(0)))
            if not with_state:
                s, e = _sentence_bounds(text, m.start())
                if not re.search(r"\bFlorida\b|\bFL\b", text[s:e]):
                    continue  # "Orange County" with no sign it is Florida's
            raw.append((m.start(), "county", f"{county} County", (county,)))
    for m in _STATE_SUFFIX.finditer(text):
        window = text[max(0, m.start() - 120):m.start()]
        pm = _PHRASE_AT_END.search(window)
        if not pm:
            continue
        name, offset = _as_place(pm.group(1).strip())
        if not name or name in US_STATES or name.split()[-1] in US_STATES or name in FLORIDA_COUNTIES or name.endswith(" County"):
            continue  # a list of states, or already a county finding
        kind = "municipality" if name in MUNICIPALITY_COUNTIES else "named_place"
        raw.append((max(0, m.start() - 120) + pm.start(1) + offset, kind, name, MUNICIPALITY_COUNTIES.get(name, ())))
    for term, rx in _NAMED_RES:
        for m in rx.finditer(text):
            raw.append((m.start(), "named_place", term, ()))
    for m in _STATE.finditer(text):
        raw.append((m.start(), "state", "Florida", ()))

    raw.sort(key=lambda r: r[0])
    out: list[Finding] = []
    seen: set[tuple[int, int, str]] = set()
    state_sentences: set[tuple[int, int]] = set()
    state_sections: set[str | None] = set()
    for pos, kind, term, counties in raw:
        s, e = _sentence_bounds(text, pos)
        if kind == "state":
            # a bare "Florida" is only worth a finding when no more specific
            # place already names this sentence, and once per section (table
            # headings repeat it on every page)
            if any(f.char_start == s and f.char_end == e for f in out):
                continue
            section_key = _section_for(text, pos, sections)
            if (s, e) in state_sentences or section_key in state_sections:
                continue
            state_sentences.add((s, e))
            state_sections.add(section_key)
        key = (s, e, term)
        if key in seen:
            continue
        seen.add(key)
        out.append(Finding(kind, term, tuple(counties), _section_for(text, pos, sections), text[s:e], s, e))
        if len(out) >= MAX_FINDINGS:
            break
    # a specific place found after a bare "Florida" in the same sentence replaces it
    specific = {(f.char_start, f.char_end) for f in out if f.kind != "state"}
    return [f for f in out if not (f.kind == "state" and (f.char_start, f.char_end) in specific)]
