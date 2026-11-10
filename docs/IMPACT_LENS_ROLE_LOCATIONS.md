# Impact Lens: role-specific location matching (design note)

Todoist `6hr2PW6M6HVFhh3p`. Status: **draft for review. No code written.**
Owner approval, 2026-10-29: separate residence, relevant property location and
relevant business location; each criterion uses the location of the role it
regulates; evaluate each applicable role/location separately; unknown stays
unknown; ask only for the detail a criterion needs; keep matching in the
browser and keep the existing uncertainty and privacy rules.

## The defect

`jurisdiction` is one attribute whose question is "Which Florida county do you
live in, and which city, town or village (if any)?"
(`backend/app/impact_lens/vocabulary.py`). The matcher
(`frontend/lib/impactLens.ts`, `jurisdictionIn`) tests every
`county:` / `municipality:` criterion against that residence answer.

A bill provision such as "a landlord of rental property in Broward County must
..." is mapped to `role in [landlord]` plus `jurisdiction in [county:Broward]`.
A reader who lives in Miami-Dade and rents out a Broward property answers
role = landlord, county = Miami-Dade. The jurisdiction test fails, the entry
becomes `no`, and the bill can read **"Does Not Appear to Apply"** when it does.
That is a false negative, the costly direction for this tool.

Not a confirmed live result: it needs a bill whose provision names a place AND
a role whose relevant place is not the residence. It is the acceptance case
below.

## Design

### 1. Which location a criterion uses is derived from the role it regulates

No change to stored criteria and no remapping. The place names a criterion tests
(`county:Broward`) already come from the bill's own text. What changes is which
of the reader's locations they are compared with.

Single source of truth, in the backend vocabulary, served to the browser in the
`/bills/{id}/impact-lens` response (so the matcher does not duplicate it):

| Role | Location it regulates |
|---|---|
| renter | residence |
| insured | residence |
| landlord | property |
| homeowner | property |
| property_developer | property |
| employer | business |
| business_owner | business |
| employee | business |
| healthcare_provider | business |
| local_government | residence (unchanged for now; see open questions) |

The kind used for an entry is the kind of its **bound** role (the audience).
An entry whose audience is unmapped or `anyone` keeps today's behavior for its
jurisdiction tests (residence).

Why derive rather than let the mapper tag each criterion: the model-written
mapping is the part with unproven accuracy (0 wrong of 40 audience mappings, none
with requirements or exclusions). A deterministic table is testable and cannot be
mislabeled by the model. An optional per-criterion `location` override can be
added later if a real bill needs one.

### 2. Answers

Today: `role`, `county`, `municipality`, `property_type`. Add, county and
municipality only (never an address; the privacy boundary already forbids it):

- `property_county`, `property_municipality`
- `business_county`, `business_municipality`

`county` / `municipality` keep meaning residence. Session storage key moves to
`impactLens.answers.v2`; `cleanAnswers` ignores v1 and unknown keys. The privacy
page text lists the stored fields and must be updated in the same change.

### 3. Matching

For a jurisdiction criterion on an entry whose bound role has kind K:

- use the reader's location of kind K;
- K answered and a listed value matches: true; answered and none match: false
  (negated for `not_in`);
- K not answered: **unknown**, and `missing` asks only for kind K's question,
  not residence (the reader is never asked for a location the criterion does
  not use).

A reader who says the property or workplace is where they live is offered a
"same as where I live" shortcut so a homeowner is not asked the same thing
twice. The shortcut copies the residence answer into the K fields.

### 4. Multiple roles and locations (later slices)

- **Several locations of one kind** (rental properties in two counties): store a
  list per kind; a criterion holds if **any** listed location matches, fails
  only if all known locations fail, and is unknown if any is unanswered and none
  match.
- **Several roles** (landlord and employer): `role` becomes a set. Each entry is
  evaluated once per applicable role using that role's location kind, and the
  entry holds if any role-and-location pairing makes it match; it is ruled out
  only if every pairing is ruled out. This is the largest UI change.

## Acceptance cases

1. **Miami-Dade resident with a Broward rental, Broward property rule**
   (entry: landlord, requires `county:Broward`): role landlord, residence
   Miami-Dade, property county Broward. **Applies.** Today: ruled out.
2. Same reader, a provision for tenants in Broward: role renter uses residence,
   Miami-Dade, **no**.
3. Property location unanswered: **unknown**, and the question asked is the
   property county, not residence.
4. Same entry, reader's property is in Palm Beach: **no**.
5. Employee who lives in Duval and works in Orange, rule for Orange employers'
   employees: business location decides. **Applies.**
6. Unmapped or `anyone` audience entries: unchanged from today.
7. Existing 40 baseline entries and every current matcher test: unchanged
   results.

## Slices

1. Location kinds with a single role and one location per kind (acceptance
   cases 1 to 7). Served table, new answer keys, matcher, question flow, privacy
   page.
2. Several locations per kind.
3. Several roles.

Each slice ships behind the existing `?lens=1` flag.

## Out of scope

- Re-mapping stored criteria; the nightly mapping gate; review-by-risk.
- Address-level or radius matching (county and municipality only).
- Any change to what the mapper extracts.

## Open questions for Joe

1. **Derive the location kind from the role (recommended) or have the mapper tag
   it per criterion?** The table above assumes derive.
2. **Role table**: `local_government` stays residence for now (the
   government's own jurisdiction is not a "residence"); `renter` is residence
   (the rented home). Right?
3. **Slices**: is slice 1 enough to ship first, with several locations and
   several roles after?
4. **Shortcut copy** for "same as where I live": acceptable wording and
   behavior?

## Status 2026-11-10: slice 2, matcher only (local branch feat/local-2026-11-10-offline)

The matcher and stored answers accept **a list of places per kind** (`property_county: ["Leon", "Duval"]`). A requirement holds if any listed place matches; an exception holds only if it holds for **every** listed place; a list of one behaves exactly like the plain string; an empty list is unanswered. `cleanAnswers` keeps lists only on the six place keys, de-duplicates and caps at 10. Tests: `lib/impactLens.severalPlaces.test.ts`.

**Control (built, behind `?lens=1`):** property and workplace counties get an "add another county" button in the answers line (not residence; capped at 10; the already-given and "none of these" options are removed from the list). Municipalities are still one per kind. The privacy page now says more than one county may be kept. Slice 3 (several roles) is untouched.
