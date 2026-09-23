"""Pure text helpers for the bill layers pipeline -- no model, no DB.

Everything the page must be able to trust is enforced here in code rather
than asked of the model in a prompt: a Bill Says quote must appear word for
word in the bill text, a Sunshine Ledger expected effect must cite a bill
section that exists and use conditional wording.

Staff-analysis heading strings were sampled from production on 2026-09-23:
4,203 of 4,308 analyses match either the Senate or the House format below.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_NAV_LINE = re.compile(r"(?m)^\s*JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION\s*$\n?")
_BILL_SECTION = re.compile(r"(?m)^\s*Section\s+(\d+)\.", re.IGNORECASE)
_SECTION_REF = re.compile(r"\b(?:section|sec\.?)\s*(\d+)(?!\.\d)\b", re.IGNORECASE)
_CONDITIONAL = re.compile(
    r"\bmay\b(?!\s+\d{1,2}\b)|\b(?:might|could|would|(?:is|are) expected to)\b", re.IGNORECASE
)
_NO_OR_UNKNOWN = re.compile(r"\b(none|no fiscal impact|no impact|indeterminate|insignificant)\b", re.IGNORECASE)

# (start, end) pairs, tried in order. Patterns are matched per line.
_EFFECT_PATTERNS = [
    (r"^\s*III\.\s*Effect of Proposed Changes:\s*$", r"^\s*IV\.\s*Constitutional Issues:"),
    (r"^\s*EFFECT OF THE BILL:\s*$", r"^\s*(?:FISCAL OR ECONOMIC IMPACT:|RELEVANT INFORMATION)\s*$"),
]
_FISCAL_PATTERNS = [
    (r"^\s*V\.\s*Fiscal Impact Statement:\s*$", r"^\s*VI\.\s*Technical Deficiencies:"),
    (r"^\s*FISCAL OR ECONOMIC IMPACT:\s*$", r"^\s*RELEVANT INFORMATION\s*$"),
    (r"^\s*Fiscal or Economic Impact:\s*$", r"^\s*(?:JUMP TO SUMMARY.*|ANALYSIS)\s*$"),
]


def normalize_ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


def verify_quotes(candidates: list[dict], text: str) -> tuple[list[dict], list[dict]]:
    """Keep only quotes that appear verbatim (modulo whitespace) in `text`.

    `text` must be exactly what the model was shown (the truncated text), so
    a quote from beyond the truncation point is dropped too.
    """
    haystack = normalize_ws(text)
    kept: list[dict] = []
    dropped: list[dict] = []
    for c in candidates:
        quote = normalize_ws(c.get("quote") or "")
        if quote and quote in haystack:
            kept.append({**c, "quote": quote})
        else:
            dropped.append(c)
    return kept, dropped


def bill_section_numbers(text: str) -> set[str]:
    return set(_BILL_SECTION.findall(text))


def section_number(ref: str | None) -> str | None:
    if not ref:
        return None
    m = _SECTION_REF.search(ref)
    return m.group(1) if m else None


def section_for_quote(quote: str, text: str) -> str | None:
    """The last bill section heading ("Section N.") before `quote` in `text`.

    The quote is located in `text` tolerating whitespace differences (as it
    was during verification), but the search runs against the original
    (non-normalized) text so the line-anchored `_BILL_SECTION` heading
    pattern still means what it says.
    """
    q = normalize_ws(quote)
    if not q:
        return None
    quote_pattern = re.compile(r"\s+".join(re.escape(word) for word in q.split()))
    m = quote_pattern.search(text)
    if not m:
        return None
    headings = _BILL_SECTION.findall(text[: m.start()])
    return f"Section {headings[-1]}" if headings else None


def is_conditional(statement: str) -> bool:
    return bool(_CONDITIONAL.search(statement))


def states_no_or_unknown_impact(statement: str) -> bool:
    return bool(_NO_OR_UNKNOWN.search(statement))


def _between(text: str, patterns: list[tuple[str, str]]) -> str | None:
    for start, end in patterns:
        m = re.search(start, text, re.MULTILINE)
        if not m:
            continue
        rest = text[m.end():]
        e = re.search(end, rest, re.MULTILINE)
        body = rest[: e.start()] if e else rest
        body = _NAV_LINE.sub("", body).strip()
        if body:
            return body
    return None


def extract_effect_section(analysis_text: str) -> str | None:
    """Staff's section-by-section account of what the bill changes."""
    return _between(analysis_text, _EFFECT_PATTERNS)


def extract_fiscal_section(analysis_text: str) -> str | None:
    """Staff's fiscal impact statement (state, local, private sector)."""
    return _between(analysis_text, _FISCAL_PATTERNS)
