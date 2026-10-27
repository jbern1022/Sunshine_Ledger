"""Count the verdicts on a hand-labeled Impact Lens sheet.

    python -m app.impact_lens.tally h1389.md [s1166.md ...]

Reads sheets written by `map_batch --export` after a person has filled each
entry's "Verdict:" line with one of correct, wrong, missed or unsure, and
prints the counts per sheet and overall, then lists every `wrong` entry with
its note. A wrong mapping (a mapped part says something the bill does not) is
the serious one: the design says any wrong mapping that would flip a result
blocks that bill's lens, and the review-by-risk step waits on this baseline.
Entries with no verdict yet, and entries that were never mapped, are counted
separately so a half-finished sheet is not mistaken for a clean one.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

VERDICTS = ("correct", "wrong", "missed", "unsure")

_BILL = re.compile(r"^## (.+)$")
_ENTRY = re.compile(r"^### Entry (\d+): (.*)$")
_VERDICT = re.compile(r"^- \*\*Verdict:\*\*\s*(.*)$")
_NOTE = re.compile(r"^- \*\*Note:\*\*\s*(.*)$")
_NOT_MAPPED = "- **Not mapped yet.**"
_PART = re.compile(r"^- \*\*(Requires|Excludes|Affected party|Ambiguous|Unmapped):\*\*")

# What an entry's mapping contains beyond its audience. A verdict on an entry
# is a verdict on every part it has, so these are the denominators for "how
# well was this part tested": an entry with no Requires line says nothing
# about requirement accuracy, however many were labeled correct.
PARTS = ("requires", "excludes", "affected", "ambiguous", "unmapped")
_PART_KEY = {"Requires": "requires", "Excludes": "excludes", "Affected party": "affected", "Ambiguous": "ambiguous", "Unmapped": "unmapped"}


@dataclass
class Entry:
    bill: str
    index: int
    group: str
    mapped: bool = True
    verdict: str = ""
    note: str = ""
    parts: set[str] = field(default_factory=set)


@dataclass
class Tally:
    entries: list[Entry] = field(default_factory=list)

    def counts(self) -> Counter:
        c: Counter = Counter()
        for e in self.entries:
            if not e.mapped:
                c["not mapped"] += 1
            elif e.verdict in VERDICTS:
                c[e.verdict] += 1
            elif e.verdict:
                c["unrecognized"] += 1
            else:
                c["no verdict yet"] += 1
        return c

    def part_coverage(self) -> dict[str, Counter]:
        """Per part, how many mapped entries have it and what the labels say."""
        out: dict[str, Counter] = {p: Counter() for p in PARTS}
        for e in self.entries:
            if not e.mapped:
                continue
            for p in e.parts:
                out[p]["entries"] += 1
                if e.verdict in VERDICTS:
                    out[p][e.verdict] += 1
        return out

    def wrong(self) -> list[Entry]:
        return [e for e in self.entries if e.mapped and e.verdict == "wrong"]


def parse_sheet(text: str) -> Tally:
    """Parse a sheet. The first word of the verdict line counts, case-insensitive,
    so "wrong - date mapped as a property type" is read as `wrong`."""
    tally = Tally()
    bill = ""
    current: Entry | None = None
    for line in text.splitlines():
        if m := _ENTRY.match(line):
            current = Entry(bill=bill, index=int(m.group(1)), group=m.group(2).strip())
            tally.entries.append(current)
        elif m := _BILL.match(line):
            bill = m.group(1).strip()
            current = None
        elif current is None:
            continue
        elif line.strip() == _NOT_MAPPED:
            current.mapped = False
        elif m := _PART.match(line):
            current.parts.add(_PART_KEY[m.group(1)])
        elif m := _VERDICT.match(line):
            words = m.group(1).strip().lower().replace("`", "").split()
            current.verdict = words[0].strip(".,:;") if words else ""
        elif m := _NOTE.match(line):
            current.note = m.group(1).strip()
    return tally


def format_report(name: str, tally: Tally) -> str:
    counts = tally.counts()
    total = len(tally.entries)
    order = [*VERDICTS, "no verdict yet", "not mapped", "unrecognized"]
    parts = [f"{k}: {counts[k]}" for k in order if counts[k]]
    out = [f"{name}: {total} entries ({', '.join(parts) if parts else 'none'})"]
    labeled = sum(counts[v] for v in VERDICTS)
    if labeled:
        out.append(f"  wrong-mapping rate: {counts['wrong']} of {labeled} labeled ({counts['wrong'] / labeled:.0%})")
    for part, c in tally.part_coverage().items():
        if part in ("requires", "excludes"):
            labeled = sum(c[v] for v in VERDICTS)
            if not c["entries"]:
                out.append(f"  {part}: NOT TESTED (no mapped entry has one)")
            else:
                out.append(f"  {part}: {c['entries']} entries, {labeled} labeled, {c['wrong']} wrong")
        elif c["entries"]:
            out.append(f"  {part}: {c['entries']} entries, {c['wrong']} wrong")
    for e in tally.wrong():
        out.append(f"  WRONG  {e.bill} entry {e.index} ({e.group}): {e.note or 'no note'}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    overall = Tally()
    for path in sys.argv[1:]:
        t = parse_sheet(Path(path).read_text())
        overall.entries += t.entries
        print(format_report(path, t))
    if len(sys.argv) > 2:
        print()
        print(format_report("All sheets", overall))
