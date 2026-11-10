"""Florida House Community Project Funding rows from the Appropriations Committee's published table.

    python -m app.federal.earmarks FILE.xlsx|FILE.csv --fiscal-year 2027 --stage requested --source-url URL
    python -m app.federal.earmarks consolidated-awards.xlsx --fiscal-year 2027 --stage included --source-url URL
    python -m app.federal.earmarks bill-table.pdf --subcommittee "Energy and Water Development" --fiscal-year 2027 --stage included --source-url URL

Source (found 2026-11-10): appropriations.house.gov/fy27-information/fy27-community-project-funding, the
"Consolidated Table of Requests" workbook. Columns used: Member Lastname, Member Firstname, District,
Party, Subcommittee, Recipient, Project Description, Recipient Address, Amount Requested, Member URL.
The committee's pages state no reuse licence for the lists; they are published by Congress, but confirm
before showing them beyond a link-back. Not imported here: the Senate's Congressionally Directed Spending
chart (an HTML table whose rows were not retrieved) and the per-bill PDF tables (image-based).

Only rows for FLORIDA House districts are kept (district code "FL" + number). A request is stored as a
request: `stage="requested"` is never funding. Re-running is safe (rows are unique on the natural key).
"""

from __future__ import annotations

import argparse
import csv
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, FederalEarmark, OfficeTenure

STAGES = ("requested", "included", "enacted")
_DISTRICT = re.compile(r"^FL\s*-?\s*(\d{1,2})$", re.IGNORECASE)

# header names the committee uses, mapped to ours (matched case-insensitively, ignoring spaces)
_COLUMNS = {
    "memberlastname": "member_last", "memberfirstname": "member_first", "district": "district", "party": "party",
    "subcommittee": "subcommittee", "recipient": "recipient", "projectdescription": "description",
    "recipientaddress": "recipient_address", "amountrequested": "amount", "memberurl": "member_url",
}
REQUIRED = ("member_last", "district", "subcommittee", "recipient", "description")


class EarmarkImportError(ValueError):
    pass


def _norm(h: object) -> str:
    return re.sub(r"[^a-z]", "", str(h or "").lower())


def read_rows(path: Path) -> list[dict]:
    """Rows as dicts keyed by our column names, from a .xlsx or .csv file."""
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            raw = list(csv.reader(f))
    else:
        import openpyxl  # imported here: only the importer needs it

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        raw = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if not raw:
        raise EarmarkImportError("the file is empty")
    header = [_COLUMNS.get(_norm(h)) for h in raw[0]]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise EarmarkImportError(f"missing columns: {missing}")
    out = []
    for r in raw[1:]:
        row = {name: r[i] for i, name in enumerate(header) if name and i < len(r)}
        if any(v not in (None, "") for v in row.values()):
            out.append(row)
    return out


def florida_district(value: object) -> str | None:
    """'FL12' -> 'CD-012'; any other state or shape -> None."""
    m = _DISTRICT.match(str(value or "").strip())
    return f"CD-{int(m.group(1)):03d}" if m and 1 <= int(m.group(1)) <= 28 else None


def _amount(v: object) -> int | None:
    try:
        return int(round(float(str(v).replace(",", "").replace("$", ""))))
    except (TypeError, ValueError):
        return None


def _s(v: object) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def match_member(db: Session, district: str, last_name: str) -> uuid.UUID | None:
    """The one person who holds (or held) this US House seat and whose name carries the last name.
    Two candidates or none: unlinked. A name alone is never enough; the seat must match too."""
    number = int(district.split("-")[1])
    people = db.execute(
        select(Entity).join(OfficeTenure, OfficeTenure.person_entity_id == Entity.id)
        .where(OfficeTenure.office_type == "us_house", OfficeTenure.district == number)
    ).scalars().unique().all()
    wanted = last_name.strip().lower()
    hits = {p.id: p for p in people if wanted and wanted in (p.name or "").lower()}
    return next(iter(hits)) if len(hits) == 1 else None


def import_rows(db: Session, rows: list[dict], *, fiscal_year: int, stage: str, source_url: str, chamber: str = "house") -> dict:
    if stage not in STAGES:
        raise EarmarkImportError(f"stage must be one of {STAGES}")
    stats = {"seen": len(rows), "florida": 0, "new": 0, "existing": 0, "linked": 0, "skipped": 0}
    seen: set[tuple] = set()  # the same project can be listed twice in one file
    for r in rows:
        district = florida_district(r.get("district"))
        if district is None:
            continue
        stats["florida"] += 1
        last, subc, rec, desc = _s(r.get("member_last")), _s(r.get("subcommittee")), _s(r.get("recipient")), _s(r.get("description"))
        if not (last and subc and rec and desc):
            stats["skipped"] += 1
            continue
        key = (fiscal_year, stage, last, district, subc, rec[:300], desc)
        existing = key in seen or db.execute(select(FederalEarmark.id).where(
            FederalEarmark.fiscal_year == fiscal_year, FederalEarmark.stage == stage, FederalEarmark.member_last == last,
            FederalEarmark.district == district, FederalEarmark.subcommittee == subc, FederalEarmark.recipient == rec[:300],
            FederalEarmark.description == desc,
        )).first() is not None
        if existing:
            stats["existing"] += 1
            continue
        seen.add(key)
        person = match_member(db, district, last)
        stats["linked"] += 1 if person else 0
        db.add(FederalEarmark(
            fiscal_year=fiscal_year, stage=stage, chamber=chamber, member_last=last, member_first=_s(r.get("member_first")),
            district=district, party=_s(r.get("party")), subcommittee=subc, recipient=rec[:300], description=desc,
            recipient_address=_s(r.get("recipient_address")), amount=_amount(r.get("amount")),
            member_url=_s(r.get("member_url")), source_url=source_url, person_entity_id=person,
        ))
        stats["new"] += 1
    db.commit()
    return stats


def read_award_rows(path: Path):
    """Rows of the committee's "Consolidated Table" of projects INCLUDED in the House bills (an .xlsx whose
    columns are Appropriations Bill, Agency, Account, State/Location, Project, Location/Recipient, House Amount,
    House Requestor(s), Party). Returns TableRow objects for import_table_rows."""
    import openpyxl

    from app.federal.earmark_tables import TableRow

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    raw = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if not raw:
        raise EarmarkImportError("the file is empty")
    col = {_norm(h): i for i, h in enumerate(raw[0])}
    need = ("appropriationsbill", "project", "locationrecipient", "houseamount", "houserequestors", "statelocation")
    if any(n not in col for n in need):
        raise EarmarkImportError(f"not a consolidated awards table; columns found: {[h for h in raw[0] if h]}")
    out = []
    for r in raw[1:]:
        if not r or r[col["houserequestors"]] in (None, ""):
            continue
        clean = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()  # noqa: E731
        names = tuple(p.strip() for p in re.split(r",\s*(?![^()]*\))", str(r[col["houserequestors"]])) if p.strip())
        location = clean(r[col["statelocation"]])
        out.append(TableRow(
            project=clean(r[col["project"]]), recipient=clean(r[col["locationrecipient"]]), amount=_amount(r[col["houseamount"]]),
            state=location.rsplit(",", 1)[-1].strip()[:2], requestors=names, subcommittee=clean(r[col["appropriationsbill"]]),
        ))
    return out


def florida_member_index(db: Session) -> dict[str, list[tuple[uuid.UUID, str, str]]]:
    """lower-case last name -> [(person id, display name, district code)] for people who hold or held a
    Florida US House seat. A person with two seats over time appears once per seat."""
    out: dict[str, list[tuple[uuid.UUID, str, str]]] = {}
    rows = db.execute(
        select(Entity, OfficeTenure.district).join(OfficeTenure, OfficeTenure.person_entity_id == Entity.id)
        .where(OfficeTenure.office_type == "us_house", OfficeTenure.district.is_not(None))
    ).all()
    for person, number in rows:
        code = f"CD-{number:03d}"
        full = (person.name or "").lower()
        for surname in {full.split()[-1]} | {" ".join(full.split()[-2:])}:
            out.setdefault(surname, []).append((person.id, person.name, code))
    return out


def import_table_rows(db: Session, rows, *, fiscal_year: int, stage: str, subcommittee: str, source_url: str) -> dict:
    """Store the rows of a per-bill project table whose requestors include a Florida House member.
    A requestor printed with another state, or a surname that is not exactly one Florida member, is not
    attributed. One row is stored per attributed Florida requestor (the project may be in any state)."""
    from app.federal.earmark_tables import split_requestor

    if stage not in STAGES:
        raise EarmarkImportError(f"stage must be one of {STAGES}")
    index = florida_member_index(db)
    stats = {"rows": len(rows), "florida_requestors": 0, "new": 0, "existing": 0, "ambiguous": 0}
    seen: set[tuple] = set()  # the same project can be listed twice in one file
    for r in rows:
        for name in r.requestors:
            last, st = split_requestor(name)
            if st and st != "FL":
                continue
            cands = {c[0]: c for c in index.get(last.lower(), [])}
            if not cands:
                continue
            if len(cands) != 1:
                stats["ambiguous"] += 1
                continue
            person_id, display, district = next(iter(cands.values()))
            stats["florida_requestors"] += 1
            desc = r.project[:2000]
            key = (fiscal_year, stage, last, district, r.subcommittee or subcommittee, (r.recipient or "(see table)")[:300], desc)
            exists = key in seen or db.execute(select(FederalEarmark.id).where(
                FederalEarmark.fiscal_year == fiscal_year, FederalEarmark.stage == stage, FederalEarmark.member_last == last,
                FederalEarmark.district == district, FederalEarmark.subcommittee == (r.subcommittee or subcommittee),
                FederalEarmark.recipient == (r.recipient or "(see table)")[:300], FederalEarmark.description == desc,
            )).first() is not None
            if exists:
                stats["existing"] += 1
                continue
            seen.add(key)
            db.add(FederalEarmark(
                fiscal_year=fiscal_year, stage=stage, chamber="house", member_last=last, member_first=None, district=district,
                subcommittee=(r.subcommittee or subcommittee), recipient=(r.recipient or "(see table)")[:300], description=desc,
                amount=r.amount, source_url=source_url, person_entity_id=person_id,
            ))
            stats["new"] += 1
    db.commit()
    return stats


def main() -> None:
    from app.db import SessionLocal

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path, help=".xlsx/.csv consolidated table, or a per-bill .pdf table with --subcommittee")
    p.add_argument("--subcommittee", help="required for a .pdf table, e.g. 'Energy and Water Development'")
    p.add_argument("--fiscal-year", type=int, required=True)
    p.add_argument("--stage", choices=STAGES, required=True)
    p.add_argument("--source-url", required=True)
    a = p.parse_args()
    db = SessionLocal()
    try:
        if a.file.suffix.lower() == ".xlsx" and a.stage != "requested":
            print(import_table_rows(db, read_award_rows(a.file), fiscal_year=a.fiscal_year, stage=a.stage,
                                    subcommittee="", source_url=a.source_url))
        elif a.file.suffix.lower() == ".pdf":
            if not a.subcommittee:
                p.error("--subcommittee is required for a PDF table")
            from app.federal.earmark_tables import parse_pdf

            print(import_table_rows(db, parse_pdf(a.file), fiscal_year=a.fiscal_year, stage=a.stage,
                                    subcommittee=a.subcommittee, source_url=a.source_url))
        else:
            print(import_rows(db, read_rows(a.file), fiscal_year=a.fiscal_year, stage=a.stage, source_url=a.source_url))
    finally:
        db.close()


if __name__ == "__main__":
    main()
