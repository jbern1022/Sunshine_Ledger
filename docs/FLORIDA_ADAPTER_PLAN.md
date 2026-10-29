# Florida adapter plan: which readers cover how many counties

Status: draft, 2026-10-29. Rolls up `docs/FLORIDA_COUNTY_PLATFORM_SWEEP.md` (search-level, no
county site opened) and `docs/FLORIDA_SOURCE_INVENTORY.md` (Legistar token probe). Every
grouping below inherits their caveat: **platform names are what a search result said**, so
confirm each source in a browser before writing its adapter. Terms of use are unchecked for
all of them (Todoist `6hm2FqXfHvxVR45G`), and iQM2 pacing is undecided (`6hrFq2mH5Pj68qgG`).

## Counties by how they can be read (67)

| Group | Counties | Count | Reader |
|---|---|---|---|
| Done: consolidated | Duval (Jacksonville) | 1 | Existing Legistar |
| Legistar, live or registered | Brevard, Broward, DeSoto, Hernando, Hillsborough (land use only), Marion, Martin, Orange (`occompt`), Pinellas, Polk, Seminole | 11 | Existing registry-driven Legistar; remaining work is the hand-run first ingest and kind rules |
| Hosted product, one adapter each | CivicClerk: Escambia, Citrus. OnBase Agenda Online: Osceola. NovusAgenda: Bay. iQM2 meetings: Okeechobee | 5 | One adapter per product; OnBase also serves Tampa, iQM2 also serves Miami |
| One predictable URL per meeting | Charlotte, Flagler, Columbia, Manatee, Leon, Baker, Bradford, Madison, Suwannee, Washington, Franklin, Hardee, Holmes, Dixie, Putnam | 15 | A document lister: build the URL from the date, fetch, record as a meeting document (not a legislation record) |
| Portal or archive page, mixed | Palm Beach, Volusia, Pasco, Sarasota, Sumter, St. Lucie, Indian River, Monroe, Miami-Dade, Lake, St. Johns, Highlands, Gadsden, Glades, Lafayette, Levy, Jackson, Jefferson, Liberty, Taylor | 20 | Custom per site; Sarasota and Sumter are Clerk portals that may need a browser |
| Not found, stale or unknown | Lee, Collier, Okaloosa, Clay, Nassau, Santa Rosa, Calhoun, Gilchrist, Union, Gulf, Hamilton, Hendry, Wakulla, Walton, Alachua (left Legistar) | 15 | Manual look first; Alachua and Walton show a stale registry row means re-sweep |

## What a "record" means in each group

Legistar and the hosted products give matter-level records (a file number, sponsor, status), which
is what the bill page and the Who-it-affects layer expect. The per-meeting URL and portal groups
give **documents** (an agenda PDF, minutes). Ingesting those is a different, smaller product:
a dated meeting entry with a link and extracted text, labelled as an agenda or minutes record,
not as legislation. Decide that scope before building (see the "Decisions" list).

## Suggested build order

1. **First ingests for what is already registered** (Orange, the county-Legistar branch, the six
   newest cities). Zero new code; the prod run is manual.
2. **Document lister** for the 15 predictable-URL counties. One module with a per-county URL
   template, a date walker and a text extractor. Cheapest per county, but a different record kind.
3. **CivicClerk adapter** (2 counties, plus any cities on the same product).
4. **OnBase Agenda Online adapter** (Osceola, Tampa; already verified to return JSON for Tampa).
5. **NovusAgenda** (Bay) and **iQM2 meetings reader** (Okeechobee; blocked on pacing).
6. The 20 mixed counties, ranked by population, after a browser check of each.

## Municipalities

Only about 21 of 412 municipalities answered on Legistar by guessing. The same grouping has not
been done for cities; it needs the same sweep (a Chrome-extension session is the efficient way).
Orlando (eSCRIBE) and Tampa (OnBase) wait on the terms ruling.

## Decisions this depends on

- Whether meeting documents (not matter records) count toward the 67-county gate.
- Terms-of-use policy (strict vs public-records posture), per `6hm2FqXfHvxVR45G`.
- iQM2 pacing, per `6hrFq2mH5Pj68qgG`.
