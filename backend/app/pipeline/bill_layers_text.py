"""Pure text helpers for the bill layers pipeline -- no model, no DB.

Everything the page must be able to trust is enforced here in code rather
than asked of the model in a prompt: a Bill Says quote must appear word for
word in the bill text, a Sunshine Ledger expected effect must cite a bill
section that exists and use conditional wording.

Staff-analysis heading strings were sampled from production on 2026-09-23:
4,203 of 4,308 analyses match either the Senate or the House format below.
"""

from __future__ import annotations

import difflib
import re

_WS = re.compile(r"\s+")
_NAV_LINE = re.compile(r"(?m)^\s*JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION\s*$\n?")
# `(?!\d)` keeps a statute citation like "Section 316.1895, F.S." from being
# read as a heading for section 316 -- a real heading's "Section N." is never
# followed immediately by another digit.
_BILL_SECTION = re.compile(r"(?m)^\s*Section\s+(\d+)\.(?!\d)", re.IGNORECASE)
_SECTION_REF = re.compile(r"\b(?:section|sec\.?)\s*(\d+)(?!\.\d)\b", re.IGNORECASE)
_CONDITIONAL = re.compile(
    # "May not <verb>" is ambiguous: "may not issue licenses" is how bills
    # state a prohibition (not conditional wording about an effect), but
    # "may not be able to complete the review on time" is a genuine forecast.
    # Treat "may not be/have/need (be able to)" as conditional; any other
    # "may not <verb>" is the prohibition form and doesn't count on its own.
    # Plain "may" (no "not" at all), and the other conditional cues, still do.
    r"\bmay\b(?!\s+\d{1,2}\b)(?!\s+not\b(?!\s+(?:be|have|need)\b))"
    r"|\b(?:might|could|would|(?:is|are) expected to)\b",
    re.IGNORECASE,
)
_BARE_FINDING_TOKENS = frozenset({"none", "n/a", "na", "indeterminate", "insignificant"})
# Which option of a fiscal statement's "None / Indeterminate / Insignificant"
# list a finding reports. A finding that also says "significant" (e.g. "an
# indeterminate, significant, negative fiscal impact") is a real finding,
# not a bare option, and matches nothing here.
_OPTION_KINDS = (
    ("none", re.compile(r"\bno\s+(?:[\w/-]+\s+){0,3}impact\b|\bnone\b", re.IGNORECASE)),
    ("indeterminate", re.compile(r"\bindeterminate\b", re.IGNORECASE)),
    ("insignificant", re.compile(r"\binsignificant\b", re.IGNORECASE)),
)
_SIGNIFICANT = re.compile(r"\bsignificant\b", re.IGNORECASE)

# Modal strength: a statement worded as a requirement, and bill wording that
# does / doesn't impose one.
# Negated forms ("is not required", "no longer required") state the absence
# of a requirement and don't count.
_REQUIREMENT_WORDING = re.compile(
    r"(?<!\bnot )(?<!\bno longer )\b(?:must|shall|required|requires?|requiring|mandates?|mandatory|obligated)\b",
    re.IGNORECASE,
)
# "may not" is how bills state a prohibition -- binding, not permissive.
_BILL_MANDATORY = re.compile(r"\b(?:shall|must|required|requires?|requiring|requirements?|may\s+not)\b", re.IGNORECASE)
# A weaker match than this is as likely to be the wrong sentence as the right
# one; 3-4 shared words produced false flags on H0091 and H1139 (2026-09-24).
_MODAL_MIN_OVERLAP = 5
_CLAUSE_SPLIT = re.compile(r";\s*|,\s*(?:after which|but|while|whereas|unless|except)\b|,?\s+and\s+(?=(?:any|all|each|the|a|an|can|may|must|shall|should|will|is|are|also)\b)", re.IGNORECASE)
_BILL_PERMISSIVE = re.compile(r"\b(?:should|may(?!\s+not\b))\b", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z']+|\d+")

_DEFINITIONS_LEAD_IN = re.compile(r"Definitions\.—")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CONTENT_WORD = re.compile(r"[A-Za-z']+")
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "been", "being", "by", "with", "as", "at", "that",
    "this", "these", "those", "it", "its", "shall", "will", "may", "not",
    "if", "than", "then", "which", "who", "whom", "from", "into", "such",
    "any", "all", "each", "other", "under", "upon", "about", "through",
    "must", "can", "have", "has", "had", "but", "also", "when", "while",
})

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


# Page furniture the PDF extractors leave in the text, one item per line:
# House page headers ("hb495-01-c1", "hb565 -02-er", "ENROLLED",
# "CS/CS/HB 565 2026 Legislature") and "- 3 -" page numbers. They land in
# the middle of sentences, so a model quoting the sentence (sensibly) leaves
# them out and the quote no longer matches word for word. Line shapes
# sampled from production on 2026-09-24.
_PAGE_FURNITURE_LINE = re.compile(
    r"^\s*(?:"
    r"[hs](?:b|jr|cr|m|r)\d+\s?-\d+-[a-z]+\d*"
    r"|ENROLLED"
    r"|(?:CS/)*H(?:B|JR|CR|M|R)\s\d+(?:,\s*Engrossed\s\d+)?\s\d{4}(?:\s+Legislature)?"
    r"|-\s*\d+\s*-"
    r")\s*$"
)
_TRAILING_LINE_NUMBER = re.compile(r"^(.*?)\s*(?<![\d.,$])\b(\d{1,3})\s*$")
# Jacksonville (Legistar) PDFs number every line at the right margin. A
# number only counts as a line number inside a run of at least this many
# lines numbered n, n+1, n+2, ... -- one stray trailing number is text.
_MIN_LINE_NUMBER_RUN = 3


def strip_page_artifacts(text: str) -> str:
    """`text` without page headers, page numbers, or margin line numbers.

    Only whole lines of known page furniture are removed, and a trailing
    number is only removed as a line number when it sits in a run of
    consecutively numbered lines, so ordinary text ending in a number
    ("... effective July 1, 2027", "subsection (2)") is left alone.
    """
    lines = [l for l in text.split("\n") if not _PAGE_FURNITURE_LINE.match(l)]
    numbers: list[int | None] = []
    for line in lines:
        m = _TRAILING_LINE_NUMBER.match(line)
        numbers.append(int(m.group(2)) if m else None)
    strip = [False] * len(lines)
    i = 0
    while i < len(lines):
        if numbers[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < len(lines) and numbers[j + 1] is not None and numbers[j + 1] == numbers[j] + 1:
            j += 1
        if j - i + 1 >= _MIN_LINE_NUMBER_RUN:
            for k in range(i, j + 1):
                strip[k] = True
        i = j + 1
    out = []
    for line, drop in zip(lines, strip):
        if drop:
            line = _TRAILING_LINE_NUMBER.match(line).group(1)
            if not line.strip():
                continue
        out.append(line)
    return "\n".join(out)


def normalize_ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


_DELETED_BEFORE_PUNCT = re.compile(r" ?\[deleted:[^\]]*\](?=[,.;:)])")
_DELETED = re.compile(r"\[deleted:[^\]]*\]")
_ADDED = re.compile(r"\[added:\s*([^\]]*)\]")
_DELETED_UNTERMINATED = re.compile(r"\s?\[deleted:[^\]]*$")
_ADDED_UNTERMINATED = re.compile(r"\[added:\s*([^\]]*)$")
_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")


def law_as_amended(text: str) -> str:
    """The text of the law as it will read once this bill takes effect.

    Drops `[deleted: ...]` spans entirely and unwraps `[added: ...]` spans to
    their contents. Line structure (including "Section N." headings at line
    start) is preserved; only the extra whitespace a deletion leaves behind
    is collapsed -- a run of double spaces, or a single space stranded right
    before a `, . ; : )` when the deleted marker sat directly against that
    punctuation. Ordinary spacing elsewhere in the text, not adjacent to a
    removed marker, is never touched.

    A marker cut off by truncation -- an opening `[deleted:` or `[added:`
    with no closing `]` -- never leaks its fragment: an unterminated deleted
    fragment is dropped, an unterminated added fragment is unwrapped.
    """
    text = _DELETED_BEFORE_PUNCT.sub("", text)
    text = _DELETED.sub("", text)
    text = _ADDED.sub(lambda m: m.group(1), text)
    text = _DELETED_UNTERMINATED.sub("", text)
    text = _ADDED_UNTERMINATED.sub(lambda m: m.group(1), text)
    return _DOUBLE_SPACE.sub(" ", text)


def _is_substantive_quote(quote: str) -> bool:
    """False for a quote that carries no substance on its own: anything
    that trails off with a colon, a "393.063 Definitions.—" lead-in (even
    without a trailing colon -- it only ever introduces a list of defined
    terms, never states one on its own), or a fragment too short to stand
    as a provision by itself.
    """
    if quote.endswith(":") or quote.endswith(":—"):
        return False
    # A statute catchline ("119.0712 Executive branch agency-specific
    # exemptions ... records.—") is a heading, not a provision.
    if quote.endswith(".—") or quote.endswith(".-"):
        return False
    if _DEFINITIONS_LEAD_IN.search(quote):
        return False
    if len(quote.split()) < 6:
        return False
    return True


# Curly quotes and dashes the model may swap for their plain forms (or the
# other way round). Every entry maps one character to one character, so an
# index into the folded text is an index into the original too.
_QUOTE_FOLD = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
                             "\u2014": "-", "\u2013": "-"})


def _repair_mojibake(s: str) -> str:
    """Undo UTF-8 read as Windows-1252 ("â€™" for "’"), which the model
    sometimes emits for curly quotes and dashes."""
    if "\u00e2\u20ac" not in s and "\u00c3" not in s:
        return s
    # Per character: bytes 0x81/0x8d/0x8f/0x90/0x9d have no Windows-1252
    # character, so those come through as the Latin-1 control character.
    raw = bytearray()
    for ch in s:
        try:
            raw += ch.encode("cp1252")
        except UnicodeError:
            try:
                raw += ch.encode("latin-1")
            except UnicodeError:
                return s  # a real non-Latin character: not mojibake
    try:
        return raw.decode("utf-8")
    except UnicodeError:
        return s


def verify_quotes(candidates: list[dict], text: str) -> tuple[list[dict], list[dict]]:
    """Keep only quotes that appear verbatim in `text` and that carry enough
    substance to stand as a provision on their own.

    "Verbatim" tolerates whitespace, curly-vs-straight quotes and dashes,
    and mojibake in the model's output -- nothing else. A kept quote is
    replaced by the text's own characters, so what's published is always
    exactly what the bill says.

    `text` must be exactly what the model was shown (the truncated text), so
    a quote from beyond the truncation point is dropped too.
    """
    haystack = normalize_ws(text)
    folded = haystack.translate(_QUOTE_FOLD)
    kept: list[dict] = []
    dropped: list[dict] = []
    for c in candidates:
        quote = normalize_ws(_repair_mojibake(c.get("quote") or ""))
        at = folded.find(quote.translate(_QUOTE_FOLD)) if quote else -1
        if at >= 0:
            quote = haystack[at:at + len(quote)]
        if at >= 0 and _is_substantive_quote(quote):
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


def _content_words(s: str) -> set[str]:
    return {
        w.lower() for w in _CONTENT_WORD.findall(s)
        if len(w) > 3 and w.lower() not in _STOPWORDS
    }


def _match_tokens(s: str) -> set[str]:
    """Content words plus numbers -- "6" vs "13 through 17" is often what
    tells two similar bill sentences apart."""
    return {
        t.lower() for t in _TOKEN.findall(s)
        if t.isdigit() or (len(t) > 3 and t.lower() not in _STOPWORDS)
    }


def overstates_modal(statement: str, text: str) -> bool:
    """True when `statement` describes as a requirement something the bill
    only recommends or permits.

    Each clause of the statement that uses requirement wording ("must",
    "requires", ...) is matched to the bill sentence sharing the most
    content words and numbers (at least 5 in common). Only the operative text (from the first
    "Section N." heading on) is searched: a bill's title summary paraphrases
    ("requiring a caregiver to ...") and isn't the law. A clause is flagged
    when that sentence says "should" or "may" without any
    "shall"/"must"/"required" of its own. Ties are resolved in the
    statement's favour: if any equally close sentence is mandatory, the
    clause isn't flagged. Found 2026-09-24: H0763's "Caregivers should
    provide ... beginning when the child attains 6 years of age, a weekly
    cash allowance" was restated as "Caregivers must provide a weekly cash
    allowance to children aged 6 and older".
    """
    amended = law_as_amended(text)
    first_section = _BILL_SECTION.search(amended)
    if first_section:
        amended = amended[first_section.start():]
    sentences = [normalize_ws(x) for x in _SENTENCE_SPLIT.split(amended)]
    sentences = [x for x in sentences if x]
    for clause in _CLAUSE_SPLIT.split(normalize_ws(statement)):
        if _REQUIREMENT_WORDING.search(clause) and _clause_overstates(clause, sentences):
            return True
    return False


def _clause_overstates(clause: str, sentences: list[str]) -> bool:
    tokens = _match_tokens(clause)
    best_score = 0
    best: list[str] = []
    for sentence in sentences:
        score = len(tokens & _match_tokens(sentence))
        if score > best_score:
            best_score, best = score, [sentence]
        elif score == best_score and score:
            best.append(sentence)
    if best_score < _MODAL_MIN_OVERLAP:
        return False
    if any(_BILL_MANDATORY.search(s) for s in best):
        return False
    return any(_BILL_PERMISSIVE.search(s) for s in best)


def restates_bill(statement: str, text: str) -> bool:
    """True when `statement` is a near-paraphrase of a sentence the bill
    already contains (often the bill's own wording with "may" inserted),
    rather than a description of a consequence. Compared against the law as
    amended, since that is the wording a genuine consequence must not just
    echo back.

    Candidate sentences are prefiltered before the O(n*m) `SequenceMatcher`
    comparison, so this stays fast even on a long (~12,000 char) bill:
    they must share >= 3 content words; their lengths must be close enough
    that a 0.6 ratio is possible at all (`ratio()` is at most
    2*min(len)/(len_a+len_b)); and the cheap `quick_ratio()` upper bound
    must reach 0.6 before the real `ratio()` runs.
    """
    stmt = normalize_ws(statement)
    stmt_words = _content_words(stmt)
    if len(stmt_words) < 3:
        return False
    stmt_lower = stmt.lower()
    for sentence in _SENTENCE_SPLIT.split(law_as_amended(text)):
        sentence = normalize_ws(sentence)
        if not sentence:
            continue
        if len(stmt_words & _content_words(sentence)) < 3:
            continue
        # autojunk=False: SequenceMatcher's default autojunk heuristic
        # treats any character making up >1% of a sequence >= 200 chars as
        # "popular" and excludes it from matching blocks. Ordinary English
        # prose easily crosses that threshold (spaces, common letters), which
        # collapses the ratio for exactly the long, near-identical sentences
        # this guard exists to catch.
        len_a, len_b = len(stmt_lower), len(sentence)
        if 2 * min(len_a, len_b) / (len_a + len_b) < 0.6:
            continue  # lengths alone rule out a 0.6 ratio
        matcher = difflib.SequenceMatcher(None, stmt_lower, sentence.lower(), autojunk=False)
        if matcher.quick_ratio() < 0.6:
            continue  # upper bound on ratio() -- cheap, and usually decisive
        if matcher.ratio() >= 0.6:
            return True
    return False


def is_substantive_finding(statement: str) -> bool:
    """True when `statement` is a real staff finding rather than a bare token.

    Staff findings (unlike Sunshine Ledger's own effects) are attributed to
    legislative staff, so they don't need conditional wording -- a plain
    "The bill will have a significant, negative fiscal impact ..." is a real
    finding worth keeping. What isn't worth keeping is a template artifact
    like a bare "None." or "Indeterminate." left over from a fiscal
    statement's category list. A finding counts as substantive when it has
    at least 4 words and isn't just one of those bare tokens.
    """
    if not statement:
        return False
    text = normalize_ws(statement)
    if not text:
        return False
    if len(text.split()) < 4:
        return False
    if text.rstrip(".").strip().lower() in _BARE_FINDING_TOKENS:
        return False
    return True


def fiscal_option_kind(statement: str) -> str | None:
    """Which "None / Indeterminate / Insignificant" option a staff finding
    reports, or None for a real finding that isn't just a category status."""
    if not statement or _SIGNIFICANT.search(statement):
        return None
    for kind, pattern in _OPTION_KINDS:
        if pattern.search(statement):
            return kind
    return None


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
