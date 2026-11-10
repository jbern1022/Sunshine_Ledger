"""Florida House Community Project Funding rows from the Appropriations Committee's published table.

    python -m app.federal.earmarks FILE.xlsx|FILE.csv --fiscal-year 2027 --stage requested --source-url URL

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
    for r in rows:
        district = florida_district(r.get("district"))
        if district is None:
            continue
        stats["florida"] += 1
        last, subc, rec, desc = _s(r.get("member_last")), _s(r.get("subcommittee")), _s(r.get("recipient")), _s(r.get("description"))
        if not (last and subc and rec and desc):
            stats["skipped"] += 1
            continue
        existing = db.execute(select(FederalEarmark).where(
            FederalEarmark.fiscal_year == fiscal_year, FederalEarmark.stage == stage, FederalEarmark.member_last == last,
            FederalEarmark.district == district, FederalEarmark.subcommittee == subc, FederalEarmark.recipient == rec,
            FederalEarmark.description == desc,
        )).scalar_one_or_none()
        if existing is not None:
            stats["existing"] += 1
            continue
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


def main() -> None:
    from app.db import SessionLocal

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path)
    p.add_argument("--fiscal-year", type=int, required=True)
    p.add_argument("--stage", choices=STAGES, required=True)
    p.add_argument("--source-url", required=True)
    a = p.parse_args()
    db = SessionLocal()
    try:
        print(import_rows(db, read_rows(a.file), fiscal_year=a.fiscal_year, stage=a.stage, source_url=a.source_url))
    finally:
        db.close()


if __name__ == "__main__":
    main()
