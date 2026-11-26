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


# Rosters print leadership titles after the name ("Boyd, Jim President",
# "DiCeglie, Nick Majority (Republican) Leader"); they are offices, not names.
_TRAILING_TITLE = re.compile(
    r"\s+(?:President(?:\s+Pro\s+Tempore)?|Speaker(?:\s+Pro\s+Tempore)?"
    r"|(?:Majority|Minority)(?:\s+\((?:Republican|Democratic)\))?\s+Leader(?:\s+Pro\s+Tempore)?)\s*$"
)


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
        name = _TRAILING_TITLE.sub("", " ".join(raw[needed["name"]].split()))
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


# A short, conservative nickname table: only names common among Florida legislators and their sources.
# Used together with the seat and the surname, never alone.
NICKNAMES = {
    "alex": {"alejandro", "alexander", "alexandra", "alexis"}, "andy": {"andrew"}, "bill": {"william"},
    "bob": {"robert"}, "rob": {"robert"}, "chris": {"christopher", "christine", "christina"},
    "chuck": {"charles"}, "dan": {"daniel"}, "dave": {"david"}, "ed": {"edward"}, "greg": {"gregory"},
    "jeff": {"jeffrey"}, "jim": {"james"}, "jimmy": {"james"}, "joe": {"joseph", "jose"},
    "jon": {"jonathan"}, "kathy": {"katherine", "kathleen"}, "larry": {"lawrence"}, "liz": {"elizabeth"},
    "matt": {"matthew"}, "mike": {"michael"}, "nick": {"nicholas"}, "pat": {"patrick", "patricia"},
    "rick": {"richard", "ricardo"}, "sam": {"samuel", "samantha"}, "steve": {"steven", "stephen"},
    "ted": {"edward", "theodore"}, "tom": {"thomas"}, "tony": {"anthony", "antonio"}, "will": {"william"},
}
ELECTION_DAY = {2026: datetime(2026, 11, 3, tzinfo=timezone.utc)}


def _ascii_lower(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def name_parts(name: str) -> tuple[set[str], list[str]]:
    """(first names incl. a quoted nickname, surname tokens). 'Maggard, Randall Scott "Randy"' gives
    ({randall, randy}, [maggard]); 'Demi Busatta Cabrera' gives ({demi}, [busatta, cabrera])."""
    s = _ascii_lower(name)
    firsts = {n.strip() for n in re.findall(r'"([^"]+)"', s) if n.strip()}
    s = re.sub(r'"[^"]*"', " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", " ", s)
    if "," in s:
        last, _, rest = s.partition(",")
        surname, given = re.findall(r"[a-z]+", last), re.findall(r"[a-z]+", rest)
    else:
        tokens = re.findall(r"[a-z]+", s)
        given, surname = tokens[:1], tokens[1:]
    if given:
        firsts.add(given[0])
    return firsts, [t for t in surname if len(t) > 1]  # drop middle initials


def _first_names_agree(a: set[str], b: set[str]) -> bool:
    for x in a:
        for y in b:
            if x == y or y in NICKNAMES.get(x, ()) or x in NICKNAMES.get(y, ()):
                return True
            short, long_ = sorted((x, y), key=len)
            if len(short) >= 3 and long_.startswith(short):
                return True
    return False


def variant_match(winner_name: str, person_name: str) -> bool:
    """Same person written differently: the surnames agree (one's tokens contain the other's) and the
    first names agree by nickname, prefix or the table above. Only ever applied within one seat."""
    wf, ws = name_parts(winner_name)
    pf, ps = name_parts(person_name)
    if not ws or not ps or not (set(ws) <= set(ps) or set(ps) <= set(ws)):
        return False
    return _first_names_agree(wf, pf)


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

    out = {"linked": 0, "linked_variant": 0, "no_match": 0, "ambiguous": 0}
    for w in db.execute(select(ElectionWinner).where(ElectionWinner.cycle == cycle)).scalars():
        if w.person_entity_id is not None:
            continue
        seat = by_seat.get((w.chamber, w.district), [])
        matches = [p for p in seat if name_key(p.name) == name_key(w.name)]
        key = "linked"
        if not matches:
            # Second pass, still seat-scoped: nicknames, shortened first names, compound surnames
            # (2026-11-26: six re-elected members were left unlinked this way).
            matches, key = [p for p in seat if variant_match(w.name, p.name)], "linked_variant"
        if len(matches) == 1:
            w.person_entity_id = matches[0].id
            out[key] += 1
        elif len(matches) > 1:
            out["ambiguous"] += 1
        else:
            out["no_match"] += 1
    db.flush()
    return out


def _seats_before(db: Session, cutoff: datetime) -> set[tuple[str, int]]:
    """Seats some FL person record already held before `cutoff` (the pre-election roster)."""
    seats = set()
    for p in db.execute(
        select(Entity).where(Entity.entity_type == "person", Entity.jurisdiction_name == "FL", Entity.created_at < cutoff)
    ).scalars():
        m = re.match(r"^(HD|SD)[-\s]?0*(\d+)$", str((p.attributes or {}).get("district", "")).strip(), re.IGNORECASE)
        if m and not (p.attributes or {}).get("committee"):
            seats.add(("house" if m.group(1).upper() == "HD" else "senate", int(m.group(2))))
    return seats


def mark_incumbents(db: Session, *, cycle: int) -> dict:
    """Fill `incumbent` where the source left it blank: True when the winner is linked to a person who
    already held this seat before election day; False when the seat was held by someone else; None
    when there is no record of the seat. A value the source stated is never changed."""
    cutoff = ELECTION_DAY[cycle]
    prior = _seats_before(db, cutoff)
    out = {"incumbent": 0, "new": 0, "unknown": 0}
    for w in db.execute(select(ElectionWinner).where(ElectionWinner.cycle == cycle)).scalars():
        if w.incumbent is not None:
            continue
        person = db.get(Entity, w.person_entity_id) if w.person_entity_id else None
        if person is not None and person.created_at is not None and person.created_at < cutoff:
            w.incumbent = True
        elif (w.chamber, w.district) in prior:
            w.incumbent = False
        else:
            w.incumbent = None
        out[{True: "incumbent", False: "new", None: "unknown"}[w.incumbent]] += 1
    db.flush()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("csv_path", nargs="?", help="omit to only re-link people and fill incumbency")
    parser.add_argument("--source-url", help="the results page the export came from (required with a CSV)")
    parser.add_argument("--certified", action="store_true", help="the file holds certified results")
    parser.add_argument("--cycle", type=int, default=2026)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.csv_path and not args.source_url:
        parser.error("--source-url is required with a CSV")
    with SessionLocal() as db:
        counts = {}
        if args.csv_path:
            with open(args.csv_path, encoding="utf-8") as fh:
                rows = parse_csv(fh.read())
            counts = import_winners(db, rows, cycle=args.cycle, source_url=args.source_url, certified=args.certified)
        linked = link_people(db, cycle=args.cycle)
        incumbency = mark_incumbents(db, cycle=args.cycle)
        db.commit()
    logger.info("winners: %s; people: %s; incumbency: %s", counts, linked, incumbency)


if __name__ == "__main__":
    main()
