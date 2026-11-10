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
