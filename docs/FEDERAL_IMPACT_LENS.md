# Federal Impact Lens

Todoist 6hvxx9pcxPGM66Wp (decided 2026-11-03). Three layers; this is where each stands.

## Layer 1: Florida places the text names (built)

`app/federal/texts.py` keeps every printed text version of each bill the
Florida delegation sponsored or cosponsored (`federal_bill_texts`; the latest
is mirrored into `Bill.full_text`). `app/federal/places.py` finds the Florida
places by rule and stores each with its sentence, copied exactly, and offsets
(`federal_place_findings`). `GET /bills/{id}/florida-places` serves them; the
bill page shows them for federal bills, labelled automatic and unreviewed, with
a line saying what is not covered.

Found: "Florida", Florida counties, `<City>, Florida`, any other `<Name>, Florida`
(bases, ports, parks), a curated list of Florida places named without the state
(Everglades, Kennedy Space Center ...), and `DR-####-FL` declarations.

Checked on the real FY2026 NDAA (H.R. 3838, 2.7 MB): 31 findings in 2 s,
military-construction tables and the Fort Pierce and Key West provisions
included. That run found and fixed three defects (a list of states made
"Georgia" a place; sentences were cut at line ends; a 64 s scan). The
MilCon-VA bill (H.R. 3944) names no Florida place in its text: its projects
are in the committee report, which is the earmark source below.

Not covered, and said on the page: earmark tables, places without a state, images.

## Earmarks (House requests: deployed; owner chose published project lists, 2026-11-10)

Source found 2026-11-10: the House Appropriations Committee's FY27 Community Project Funding page
(`appropriations.house.gov/fy27-information/fy27-community-project-funding`) publishes a "Consolidated Table of
Requests" workbook (7,340 rows; columns Member Lastname/Firstname, District, Party, Subcommittee, Recipient, Project
Description, Recipient Address, Amount Requested, Member URL) and per-bill "Posted/Final Table" PDFs (image-based, not
parsed). `app/federal/earmarks.py` imports the workbook (or a CSV): only Florida districts are kept (483 rows in the
FY27 file, at most 20 per member), each row is stored with its stage (`requested`, `included`, `enacted`) and linked to
a member only when the seat and the last name both match exactly one tenure. `GET /earmarks` lists them with a label
per stage; a request is never shown as funding. Table `federal_earmarks`, migration `b6d9a2f4c1e7`. Deployed and loaded 2026-11-10 (482 Florida FY27 requests; 468 linked to a member; the 14 for CD-020 are unlinked because that seat is vacant in the roster). Shown on congressional district pages (`/districts/CD-###`).

Not done: person-page section, the Senate's Congressionally Directed Spending chart (an HTML table; its rows were not retrieved), the
"included" and "enacted" tables (PDF, image-based: need a table-extraction decision), a frontend, linking an earmark to
the member's promises, and a reuse statement (neither committee site states one; the lists are published by Congress,
but confirm before showing more than a link-back). Run: `python -m app.federal.earmarks FILE.xlsx --fiscal-year 2027
--stage requested --source-url URL`.

## Layer 2: nationwide categories (built, owner-approved 2026-11-10)

Three roles were added to the vocabulary (VOCABULARY_VERSION 3):
`flood_insurance_policyholder` (location: the insured property),
`medicare_beneficiary` (residence), `small_employer` (business). Answers stay in
the browser. Version 3 only adds values, so rows mapped at version 2 stay
served (`COMPATIBLE_VERSIONS`) until an entry is remapped; the mapper method is
now `impact_lens_criteria/10`, so the nightly mapping step remaps everything.

- **Guards.** A group names the role only by its own words ("Medicare
  beneficiaries", "flood insurance policyholders", "small employers"), and the
  specific role replaces the general one it also matches (small employer over
  employer, Medicare enrollee over insured). "Beneficiaries" alone is not Medicare.
- **Federal Who layer** (`app/federal/lens_text.py`). A federal bill is read
  only in the sections that mention flood insurance, Medicare or small
  employers/businesses; the block says "Read 3 of 912 sections ... Other
  provisions were not analyzed". Entries keep the verified-quote rules. Only the
  Who layer runs for federal bills (no Bill Says / Interpretation / Expected
  Effect), only for delegation bills, and its input hash covers only the
  relevant sections, so an unrelated change never regenerates it.
- The prompt forbids stating or estimating dollar amounts or people affected
  (layer 3 territory).
- Still off until `LAYERS_WHO_IT_AFFECTS` is on (it is on in prod), and a
  federal bill needs its text (needs CONGRESS_API_KEY).
- Not built: the optional ACS context line (residents 65+ with margins of
  error).

## Layer 3: attributed estimates (not built, by design)

Only when CBO, an agency or CRS publishes a Florida figure, through phase 5
"May Affect You" (6hhJ73x37wFQhxPG). No in-house formula shares.

## Commands

```bash
python -m app.federal.texts --limit 50     # needs CONGRESS_API_KEY; the nightly runs it
```
