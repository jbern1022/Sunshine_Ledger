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

## Earmarks (not built; needs a data source)

Community Project Funding (House) and Congressionally Directed Spending
(Senate) are listed in the appropriations committees' reports and project
tables, with requester, recipient and place. Linking each to the requesting
member (a `sponsor`-like relationship plus the member's promises) needs that
table ingested. Open: pick the source (committee report tables, or the
committees' published project lists) and confirm its terms.

## Layer 2: nationwide categories (not built; needs decisions)

The mapper and matcher already do the work once a bill has a Who-it-affects
layer and the vocabulary has the category. What is missing:

1. **Vocabulary additions.** Proposed, none added yet: roles
   `flood_insurance_policyholder`, `medicare_beneficiary`, `small_employer`
   (or `employer` plus an employee-count number). `medicare_beneficiary`
   passes the forbidden-dimension filter by name but is an age/health proxy, so
   it needs an explicit owner decision under the Impact Lens privacy boundary
   (answers stay in the browser). Bump `VOCABULARY_VERSION` with any change.
2. **Layers for federal bills.** Text is now stored; the layer generator
   reads `Bill.full_text` and already skips non-delegation federal bills.
   Federal bills run long (the NDAA is 2.7 MB), so the generator's length
   limits need a federal strategy (by section) before it runs on them.
3. **Optional ACS context** (residents 65+, with margins of error): the
   district profile code already shows ACS with MOE; a statewide table is a
   small addition once the wording is approved.

## Layer 3: attributed estimates (not built, by design)

Only when CBO, an agency or CRS publishes a Florida figure, through phase 5
"May Affect You" (6hhJ73x37wFQhxPG). No in-house formula shares.

## Commands

```bash
python -m app.federal.texts --limit 50     # needs CONGRESS_API_KEY; the nightly runs it
```
