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
# pypdf splits the first word of Jacksonville ordinances across two lines
# ("In" / "troduced by Council Member ...").
_SPLIT_INTRODUCED = re.compile(r"^(In?t?r?)\n(n?t?r?oduced)\b", re.MULTILINE)


def _line_number_at_end(line: str, expected: int) -> int | None:
    """Length of margin line number `expected` at the end of `line`, or None.

    Within a run the number also counts when pypdf glued it to the text
    ("EFFECTIVE DATE.18", or "GENERAL -212" for line 12): mid-run, text
    ending in exactly the next line number is a negligible coincidence.
    """
    m = _TRAILING_LINE_NUMBER.match(line)
    if m and int(m.group(2)) == expected:
        return len(line) - len(m.group(1))
    stripped = line.rstrip()
    if stripped.endswith(str(expected)):
        return len(line) - len(stripped) + len(str(expected))
    return None


def strip_page_artifacts(text: str) -> str:
    """`text` without page headers, page numbers, or margin line numbers.

    Only whole lines of known page furniture are removed, and a trailing
    number is only removed as a line number when it sits in a run of
    consecutively numbered lines, so ordinary text ending in a number
    ("... effective July 1, 2027", "subsection (2)") is left alone.
    Whitespace-only lines, which pypdf puts between Jacksonville's
    numbered lines, don't break a run.
    """
    text = _SPLIT_INTRODUCED.sub(
        lambda m: "Introduced" if m.group(1) + m.group(2) == "Introduced" else m.group(0), text
    )
    lines = [l for l in text.split("\n") if not _PAGE_FURNITURE_LINE.match(l)]
    cut = [0] * len(lines)  # characters to drop from the end of each line
    i = 0
    while i < len(lines):
        m = _TRAILING_LINE_NUMBER.match(lines[i])
        if not m:
            i += 1
            continue
        run = [(i, len(lines[i]) - len(m.group(1)))]
        n = int(m.group(2))
        j = i + 1
        while j < len(lines):
            if not lines[j].strip():
                j += 1
                continue
            length = _line_number_at_end(lines[j], n + 1)
            if length is None:
                break
            run.append((j, length))
            n += 1
            j += 1
        if len(run) >= _MIN_LINE_NUMBER_RUN:
            for k, length in run:
                cut[k] = length
            i = run[-1][0] + 1
        else:
            i += 1
    out = []
    for line, length in zip(lines, cut):
        if length:
            line = line[: len(line) - length].rstrip()
            if not line.strip():
                continue
        out.append(line)
    return "\n".join(out)


# Form furniture on Florida amendment documents (sampled from the 1,185
# stored amendments on 2026-09-25): the Senate's barcode line
# ("Ì877368ZÎ877368"), its LEGISLATIVE ACTION box (a "Senate . House"
# header, lone dots, em-dash rules) and the House committee form's Y/N
# checkboxes. The floor-action codes and timestamps inside the Senate box
# ("Floor: 1/AD/RM") are kept: they record what happened to the amendment.
_AMENDMENT_FURNITURE_LINE = re.compile(
    r"^\s*(?:\[added:\s*)?(?:"
    r"Ì\w+Î\w+"
    r"|LEGISLATIVE ACTION"
    r"|(?:Senate|House)?\s*\.\s*(?:Senate|House)?"
    r"|—{5,}"
    r"|(?:ADOPTED|ADOPTED AS AMENDED|ADOPTED W/O OBJECTION|FAILED TO ADOPT|WITHDRAWN) \(Y/N\)"
    r"|OTHER"
    r"|COMMITTEE/SUBCOMMITTEE ACTION"
    r")\]?\s*$"
)


def strip_amendment_furniture(text: str) -> str:
    """`text` without the form furniture of a Florida amendment document."""
    return "\n".join(l for l in text.split("\n") if not _AMENDMENT_FURNITURE_LINE.match(l))
