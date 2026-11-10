"""The 2026 Florida legislature winners list (Todoist 6hvxrjFpXCFP6xvp).

Input is a CSV exported from the Florida Division of Elections results site
(results.elections.myflorida.com serves a block page to scripts, so the file
comes from a browser download, not a fetch). Load it as `unofficial`, then
load the certified export with `--certified`: seats whose winner, party or
spelling changed are recorded in `change_log`, never overwritten silently.

Columns (case-insensitive; aliases in parentheses):
  chamber (office)  "house"/"senate", or an office name such as
                    "State Senator" / "Representative in the Legislature"
  district          number, or "SD-012" / "HD 45"
  name (candidate)  as printed by the source
  party             optional
  incumbent         optional: yes/no/true/false

Usage:
    python -m app.promises.winners winners.csv --source-url URL [--certified] [--cycle 2026]
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import unicodedata
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ElectionWinner, Entity

logger = logging.getLogger(__name__)

_ALIASES = {
    "chamber": ("chamber", "office", "office name", "race"),
    "district": ("district", "dist", "seat"),
    "name": ("name", "candidate", "candidate name", "winner"),
    "party": ("party", "party code"),
    "incumbent": ("incumbent", "inc"),
}


class WinnersError(ValueError):
    pass


def parse_chamber(value: str) -> str:
    v = value.strip().lower()
    if v in ("house", "h", "hd") or "representative" in v or v.startswith("house") or v.startswith("hd"):
        return "house"
    if v in ("senate", "s", "sd") or "senator" in v or v.startswith("senate") or v.startswith("sd"):
        return "senate"
    raise WinnersError(f"cannot tell the chamber from {value!r}")


def parse_district(value: str) -> int:
    m = re.search(r"(\d+)\s*$", value.strip())
    if not m:
        raise WinnersError(f"cannot read a district number from {value!r}")
    return int(m.group(1))


def _parse_bool(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    if v in ("yes", "y", "true", "1", "inc"):
        return True
    if v in ("no", "n", "false", "0"):
        return False
    return None


def name_key(name: str) -> str:
    """A comparison key: 'Smith, Jane A.' and 'Jane A. Smith' agree, case,
    accents, punctuation and suffixes ignored. Used only together with
    chamber and district, never alone."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    if "," in s:
        last, _, rest = s.partition(",")
        s = f"{rest} {last}"
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", " ", s)
    s = re.sub(r"[^a-z\s]", " ", s)
    parts = s.split()
    # first + last token only: middle names and initials differ between sources
    return " ".join([parts[0], parts[-1]]) if len(parts) > 1 else s.strip()


def parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise WinnersError("the file has no header row")
    header = {f.strip().lower(): f for f in reader.fieldnames}

    def col(field: str) -> str | None:
        for alias in _ALIASES[field]:
            if alias in header:
                return header[alias]
        return None

    needed = {f: col(f) for f in ("chamber", "district", "name")}
    missing = [f for f, c in needed.items() if c is None]
    if missing:
        raise WinnersError(f"missing column(s): {', '.join(missing)}")
    party_col, inc_col = col("party"), col("incumbent")

    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for n, raw in enumerate(reader, start=2):
        if not any((v or "").strip() for v in raw.values()):
            continue
        try:
            chamber = parse_chamber(raw[needed["chamber"]])
            district = parse_district(raw[needed["district"]])
        except WinnersError as exc:
            raise WinnersError(f"line {n}: {exc}") from exc
        name = " ".join(raw[needed["name"]].split())
        if not name:
            raise WinnersError(f"line {n}: no name")
        if (chamber, district) in seen:
            raise WinnersError(f"line {n}: {chamber} district {district} appears twice (one winner per seat)")
        seen.add((chamber, district))
        rows.append(
            {
                "chamber": chamber,
                "district": district,
                "name": name,
                "party": (raw.get(party_col) or "").strip() or None if party_col else None,
                "incumbent": _parse_bool(raw.get(inc_col)) if inc_col else None,
            }
        )
    return rows


def import_winners(
    db: Session,
    rows: list[dict],
    *,
    cycle: int,
    source_url: str,
    certified: bool,
    now: datetime | None = None,
) -> dict:
    """Upsert one row per seat. Returns counts. A certified seat is never
    set back to unofficial."""
    now = now or datetime.now(timezone.utc)
    counts = {"created": 0, "unchanged": 0, "changed": 0, "skipped_certified": 0}
    for row in rows:
        existing = db.execute(
            select(ElectionWinner).where(
                ElectionWinner.cycle == cycle,
                ElectionWinner.chamber == row["chamber"],
                ElectionWinner.district == row["district"],
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ElectionWinner(
                    cycle=cycle,
                    chamber=row["chamber"],
                    district=row["district"],
                    name=row["name"],
                    party=row["party"],
                    incumbent=row["incumbent"],
                    result_status="certified" if certified else "unofficial",
                    source_url=source_url,
                    source_retrieved_at=now,
                    certified_at=now.date() if certified else None,
                    change_log=[],
                )
            )
            counts["created"] += 1
            continue
        if existing.result_status == "certified" and not certified:
            counts["skipped_certified"] += 1
            continue
        diffs = {}
        for field in ("name", "party", "incumbent"):
            new = row[field]
            old = getattr(existing, field)
            if new is not None and new != old:
                diffs[field] = {"from": old, "to": new}
        if diffs or (certified and existing.result_status != "certified"):
            existing.change_log = [
                *existing.change_log,
                {
                    "at": now.isoformat(),
                    "from_status": existing.result_status,
                    "to_status": "certified" if certified else "unofficial",
                    "changes": diffs,
                    "source_url": source_url,
                },
            ]
            for field, d in diffs.items():
                setattr(existing, field, d["to"])
            if "name" in diffs:
                existing.person_entity_id = None  # re-link against the new name
            counts["changed"] += 1
        else:
            counts["unchanged"] += 1
        if certified:
            existing.result_status = "certified"
            existing.certified_at = now.date()
        existing.source_url = source_url
        existing.source_retrieved_at = now
    db.flush()
    return counts


def link_people(db: Session, *, cycle: int) -> dict:
    """Link winners to existing person entities. A match needs the chamber
    AND district AND the name key; anything less stays unlinked (no name-only
    merges). Two candidates for one seat are left unlinked and reported."""
    people = db.execute(
        select(Entity).where(Entity.entity_type == "person", Entity.jurisdiction_name == "FL")
    ).scalars().all()
    by_seat: dict[tuple[str, int], list[Entity]] = {}
    for p in people:
        attrs = p.attributes or {}
        if attrs.get("committee"):
            continue
        m = re.match(r"^(HD|SD)[-\s]?0*(\d+)$", str(attrs.get("district", "")).strip(), re.IGNORECASE)
        if not m:
            continue
        chamber = "house" if m.group(1).upper() == "HD" else "senate"
        by_seat.setdefault((chamber, int(m.group(2))), []).append(p)

    out = {"linked": 0, "no_match": 0, "ambiguous": 0}
    for w in db.execute(select(ElectionWinner).where(ElectionWinner.cycle == cycle)).scalars():
        if w.person_entity_id is not None:
            continue
        matches = [p for p in by_seat.get((w.chamber, w.district), []) if name_key(p.name) == name_key(w.name)]
        if len(matches) == 1:
            w.person_entity_id = matches[0].id
            out["linked"] += 1
        elif len(matches) > 1:
            out["ambiguous"] += 1
        else:
            out["no_match"] += 1
    db.flush()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("csv_path")
    parser.add_argument("--source-url", required=True, help="the results page the export came from")
    parser.add_argument("--certified", action="store_true", help="the file holds certified results")
    parser.add_argument("--cycle", type=int, default=2026)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with open(args.csv_path, encoding="utf-8") as fh:
        rows = parse_csv(fh.read())
    with SessionLocal() as db:
        counts = import_winners(db, rows, cycle=args.cycle, source_url=args.source_url, certified=args.certified)
        linked = link_people(db, cycle=args.cycle)
        db.commit()
    logger.info("winners: %s; people: %s", counts, linked)


if __name__ == "__main__":
    main()
