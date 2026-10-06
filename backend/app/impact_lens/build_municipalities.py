"""Rebuild app/data/fl_municipalities.json from the Census place-by-county file.

    curl -O https://www2.census.gov/geo/docs/reference/codes2020/national_place_by_county2020.txt
    python -m app.impact_lens.build_municipalities national_place_by_county2020.txt

Keeps Florida INCORPORATED PLACEs only (not census-designated places). A place
that spans counties lists each. The vintage is recorded in the output.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "fl_municipalities.json"


def build(lines: list[str]) -> dict:
    places: dict[str, dict] = {}
    for line in lines[1:]:
        f = line.rstrip("\n").split("|")
        if len(f) < 10 or f[0] != "FL" or f[7] != "INCORPORATED PLACE":
            continue
        name = re.sub(r" (city|town|village)$", "", f[6])
        county = re.sub(r" County$", "", f[3])
        place = places.setdefault(f[4], {"name": name, "place_fips": f[4], "counties": []})
        if county not in place["counties"]:
            place["counties"].append(county)
    rows = sorted(places.values(), key=lambda p: p["name"])
    return {
        "source": "U.S. Census Bureau, 2020 place-by-county relationship file (national_place_by_county2020.txt)",
        "vintage": 2020,
        "note": "Incorporated places only. Municipal boundaries change; rebuild when a newer vintage is available.",
        "municipalities": rows,
    }


if __name__ == "__main__":
    data = build(Path(sys.argv[1]).read_text().splitlines(keepends=True))
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(data['municipalities'])} municipalities -> {OUT}")
