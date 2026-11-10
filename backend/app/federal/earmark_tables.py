"""Rows from the House Appropriations Committee's per-bill project tables (text PDFs).

The committee's "Posted/Final Table" PDFs list every Community Project Funding item in a House bill:
`Agency  Account  Project Name; Recipient  Budget Request  Additional Amount  Total Amount Provided  State
House Requestor(s)`. Requestors are last names only (a state in parentheses separates two members who
share one, e.g. "Kelly (IL)"). The layout differs a little between bills, so this does not rely on fixed
columns: a row starts on a line that has an amount followed by a two-letter state and then names, and
continues on the lines below until the next such line. The project text is APPROXIMATE: when a name wraps
inside the agency or account column, those words can land after the project name (the committee PDF is the
source of truth, so every stored row links to it). Words to the left of the amounts are the project
text; words at or beyond the requestor column on the following lines are more requestors.

What is kept: items where a requestor is a Florida House member (matched by last name against the
current Florida House tenures; "(FL)" breaks a tie), with that member's district. One row per matching
requestor. Rows it cannot attribute to exactly one Florida member are counted and not stored. The
amount stored is the Additional Amount (the Community Project Funding part), else the total.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

AMOUNT = re.compile(r"^\$?\d[\d,]*$|^\.{4,}$")
STATE = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True)
class TableRow:
    project: str  # everything left of the amounts: agency, account, project name; recipient
    recipient: str
    amount: int | None
    state: str
    requestors: tuple[str, ...]  # as printed, e.g. "Kelly (IL)"
    subcommittee: str = ""  # set when the source says it per row (the consolidated workbook does)


def _money(tok: str) -> int | None:
    return int(tok.replace("$", "").replace(",", "")) if re.match(r"^\$?\d[\d,]*$", tok) else None


def _lines(words: list[dict], tol: float = 2.5) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in out]


def _first_line(line: list[dict]) -> tuple[int, int] | None:
    """(index of the state word, index of the last amount-like word before it), when this line starts a row."""
    for i in range(len(line) - 2, 0, -1):
        if STATE.match(line[i]["text"]) and AMOUNT.match(line[i - 1]["text"]):
            return i, i - 1
    return None


def parse_page(words: list[dict]) -> list[TableRow]:
    rows: list[TableRow] = []
    cur: dict | None = None
    # Printer's marks sit in the left margin (job numbers, "Frm 00000"); they are not part of any row.
    words = [w for w in words if w["x0"] >= 60]
    for line in _lines(words):
        hit = _first_line(line)
        if hit:
            si, ai = hit
            if cur:
                rows.append(_finish(cur))
            amounts = [w for w in line[: si] if AMOUNT.match(w["text"])]
            first_amount_index = next(i for i, w in enumerate(line) if AMOUNT.match(w["text"]))
            nums = [w["text"] for w in amounts]
            cur = {
                "left": [w["text"] for w in line[:first_amount_index]],
                "amounts": nums,
                "state": line[si]["text"],
                "req": [w["text"] for w in line[si + 1:]],
                "req_x": line[si + 1]["x0"],
                "state_x": line[si]["x0"],
            }
        elif cur:
            for w in line:
                if w["x0"] >= cur["req_x"] - 3:
                    cur["req"].append(w["text"])
                elif w["x0"] < cur["state_x"] - 5 and not AMOUNT.match(w["text"]):
                    cur["left"].append(w["text"])
    if cur:
        rows.append(_finish(cur))
    return rows


def _finish(cur: dict) -> TableRow:
    nums = cur["amounts"]
    amount = _money(nums[-2]) if len(nums) >= 3 else _money(nums[-1])
    project = re.sub(r"\s+", " ", " ".join(cur["left"])).strip()
    recipient = project.rsplit(";", 1)[1].strip() if ";" in project else ""
    # requestors: "Budzinski, Graves (MO), Sorensen" -> three names; a "(ST)" belongs to the name before it
    text = " ".join(cur["req"])
    parts = [p.strip() for p in re.split(r",\s*(?![^()]*\))", text) if p.strip()]
    return TableRow(project, recipient, amount, cur["state"], tuple(parts))


def parse_pdf(path) -> list[TableRow]:
    import pdfplumber  # already a dependency (bill text extraction)

    rows: list[TableRow] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows.extend(parse_page(page.extract_words()))
    return rows


def split_requestor(name: str) -> tuple[str, str | None]:
    """'Kelly (IL)' -> ('Kelly', 'IL'); 'Gimenez' -> ('Gimenez', None)."""
    m = re.match(r"^(.*?)\s*\(([A-Z]{2})\)$", name.strip())
    return (m.group(1), m.group(2)) if m else (name.strip(), None)
