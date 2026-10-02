"""When a bill says it takes effect, read from its own text.

Florida acts end with an effective-date section ("This act shall take
effect July 1, 2026." / "... upon becoming a law."), and Jacksonville
ordinances with "... shall become effective upon signature by the Council
President ...". Checked 2026-09-30 against every stored text: those shapes
cover ~90% of state bills. This is what the bill says, not a legal
determination -- a vetoed bill never takes effect, and some sections can
carry their own dates ("Except as otherwise provided ...").
"""

from __future__ import annotations

import re

from datetime import datetime

from app.pipeline.bill_layers_text import law_as_amended, normalize_ws, section_at, statute_at, unit_scope

_CLAUSE = re.compile(
    r"(?P<sentence>[^.]*?\bthis (?:act|ordinance|resolution)\b[^.]{0,200}?"
    r"\b(?:takes?|becomes?|shall become) (?:effect|effective)\s+(?P<when>[^.]{3,200}?)\.)(?=\s|$)",
    re.IGNORECASE,
)
_VERB = re.compile(r"\b(?:takes?|becomes?|shall become) (?:effect|effective)\s+", re.IGNORECASE)
_TAIL_CHARS = 20_000  # the clause is the last section; don't scan a 1.6 MB budget


def effective_clause(text: str | None) -> tuple[str, bool] | None:
    """(when, has_exceptions) from the bill's last effective-date clause:
    ("July 1, 2026", False), ("upon becoming a law", True), or None."""
    if not text:
        return None
    tail = " ".join(law_as_amended(text[-_TAIL_CHARS:]).split())
    matches = list(_CLAUSE.finditer(tail))
    if not matches:
        return None
    last = matches[-1]
    # "..., except for this section, which shall take effect upon this act
    # becoming a law, this act shall take effect July 1, 2026." -- the act's
    # own date is the last one in the sentence.
    when = _VERB.split(last.group("sentence"))[-1].strip().rstrip(".").strip()
    return when, "except" in last.group("sentence").lower()


# R8 (HB 1389 validation): dates that apply to particular provisions, not
# the act -- a retroactive section, a first tax roll, a sunset, a deadline.
_DATE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
_PROVISION_DATES = [
    ("retroactive", re.compile(rf"\bretroactively\s+to\s+(?P<when>{_DATE})", re.IGNORECASE)),
    ("tax_roll", re.compile(r"\bfirst\s+appl(?:y|ies)\s+to\s+the\s+(?P<year>\d{4})\s+(?:property\s+)?tax\s+roll", re.IGNORECASE)),
    ("expires", re.compile(
        rf"\b(?:expires?|shall\s+expire|(?:is|stands|shall\s+stand)\s+repealed)(?:\s+on|\s+effective)?\s+(?P<when>{_DATE})",
        re.IGNORECASE,
    )),
    ("takes_effect", re.compile(rf"\b(?:takes?|shall\s+take)\s+effect\s+(?:on\s+)?(?P<when>{_DATE})", re.IGNORECASE)),
    ("deadline", re.compile(rf"\b(?:by|no\s+later\s+than|on\s+or\s+before)\s+(?P<when>{_DATE})", re.IGNORECASE)),
]
_FIRST_SECTION = re.compile(r"(?m)^\s*Section\s+1\.(?!\d)", re.IGNORECASE)
# A sentence's end; "s. 333.03" and "ss. 380.055" are citations.
_SENTENCE_END = re.compile(r"(?<!\bs)(?<!\bss)\.(?=\s|$)")
_THIS_UNIT = re.compile(r"^This\s+(section|subsection|paragraph|subparagraph)\b", re.IGNORECASE)
_TO_CITES = re.compile(r"\bto\s+ss?\.\s+(\d+\.\d+[\w()]*(?:,?\s+(?:and|or)\s+\d+\.\d+[\w()]*)*)", re.IGNORECASE)
_SECTION_SUBJECT = re.compile(r"^Section\s+(\d+)\s+shall\s+take\s+effect", re.IGNORECASE)
_ACT_DATE = re.compile(r"\bthis\s+act\s+shall\s+take\s+effect\b", re.IGNORECASE)


def _sentence(law: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in _SENTENCE_END.finditer(law, 0, pos):
        start = m.end()
    end = _SENTENCE_END.search(law, pos)
    return start, (end.end() if end else len(law))


def provision_dates(text: str | None) -> list[dict]:
    """Each dated provision in the bill's law (not its title, not the act's
    own effective date): {kind, when, date (ISO or None), section, scopes,
    quote}, in the bill's order."""
    if not text:
        return []
    law = law_as_amended(text)
    first = _FIRST_SECTION.search(law)
    if first:
        law = law[first.start():]
    found: dict[tuple[int, int], dict] = {}
    for kind, pattern in _PROVISION_DATES:
        for m in pattern.finditer(law):
            span = _sentence(law, m.start())
            sentence = normalize_ws(law[span[0]:span[1]])
            if span in found or (kind == "takes_effect" and _ACT_DATE.search(sentence)):
                continue
            if kind == "tax_roll":
                when, date = f"the {m.group('year')} tax roll", None
            else:
                when = normalize_ws(m.group("when"))
                date = datetime.strptime(when, "%B %d, %Y").date().isoformat()
            unit = _THIS_UNIT.match(sentence)
            cites = _TO_CITES.search(sentence)
            subject = _SECTION_SUBJECT.match(sentence)
            if subject:
                scopes = [f"Section {subject.group(1)}"]
            elif cites:
                scopes = ["s. " + c for c in re.findall(r"\d+\.\d+[\w()]*", cites.group(1))]
            elif unit:
                scopes = unit_scope(law, span[0], unit.group(1))
            else:
                at = statute_at(law, span[0]) or section_at(law, span[0])
                scopes = [at] if at else []
            found[span] = {
                "kind": kind, "when": when, "date": date, "section": section_at(law, span[0]),
                "scopes": scopes, "quote": sentence,
            }
    return [found[k] for k in sorted(found)]
