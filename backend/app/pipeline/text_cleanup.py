"""Remove page furniture from extracted bill text -- no model, no DB.

Shared by the bill-text extractors (so stored text is clean) and the bill
layers pipeline (which also cleans at generation time, for text stored
before this existed).
"""

from __future__ import annotations

import re

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
