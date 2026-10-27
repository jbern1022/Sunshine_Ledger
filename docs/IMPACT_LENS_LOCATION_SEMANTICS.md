# Impact Lens: which location does each criterion need?

Status: draft for Joe's review, 2026-10-26. Nothing in the wording or the model has
changed. Todoist `6hr2PW6M6HVFhh3p`. Scenario tests that pin today's behavior:
`frontend/lib/impactLens.location.test.ts`.

## The problem

The lens asks one location question, "Which Florida county do you live in?" (and
optionally "Do you live in one of these cities, towns or villages?"), and uses the
answer for every criterion that names a county or municipality
(`jurisdictionIn` in `frontend/lib/impactLens.ts`). A bill's rule can depend on a
different place than where a reader lives:

| Who the rule is about | Place the rule actually depends on | Is it where they live? |
|---|---|---|
| renter | the rental unit | usually, not always (a second rental, a student) |
| homeowner | the property | not for a second-home owner |
| landlord | the rental property | often not |
| property_developer | the project site | often not |
| employer, business_owner | where the business operates | often not |
| employee | where they work | often not (commuters) |
| local_government | the government's own area | there is no "live", it is an official's role |
| insured | the policy is Florida-wide; a few rules key on where the insured lives or the risk is located | partly |
| healthcare_provider | where they practice | often not |

This is a design-validation finding, not a confirmed wrong live result: no bill checked
so far has been shown wrongly. The 40-entry baseline never exercised a county condition.

## What the matcher does today (pinned by tests)

- A reader gives one county (and maybe one municipality). Every `jurisdiction`
  requirement or exclusion is tested against that single answer, whatever the role.
- A landlord who lives in Leon and owns a rental in Duval, reading a Duval-only rule,
  gets **Does Not Appear to Apply**. That is a wrong negative, and it is the direction
  the design wants to avoid ("unknown is not no"). It is shown only when the Who layer is
  marked complete, but nothing stops it on a complete layer.
- A reader with a role the entry doesn't name gets no question about location at all.
- There is no way to answer "several counties" or "it depends".

## Decisions needed

1. **What does the county answer mean?** Options:
   - **A. Role-specific wording, still one answer.** Ask "Which county is the rental
     property in?" for landlords, "...do you work in?" for employees, and so on. Smallest
     change; wrong for readers with property in several counties.
   - **B. Several counties allowed.** A reader can select more than one. Requirement is
     met if any selected place matches; excluded only if every selected place is excluded;
     unknown stays unknown. Handles landlords and chains; costs a multi-select control.
   - **C. A and B together.** Recommended: wording follows the role, and the answer may
     hold more than one place.
2. **Local governments.** An official is not asked where they live. Either skip location
   for `local_government` and ask "which government do you work for?", or leave that role
   out of the location question. Needs your call.
3. **A second "I live here" question?** If a rule is about a resident (for example a
   residency requirement), the lens needs the residence county too. Recommend adding it
   only when a bill's condition says "resident of", which the vocabulary doesn't yet
   distinguish from "located in". That is a vocabulary change (version bump).

## What this needs from the mapper

The mapper currently emits `jurisdiction in [...]` with no statement of which kind of
place the condition names. To pick the right question the criteria would need a
`place_role` (residence, property, business, workplace, government's own area) per
`jurisdiction` test. The mapper could propose it and the guards verify it against the
quote, like property type. It is not worth building before decision 1.

## Scenarios to exercise (the ticket asks for these)

| # | Reader | Rule | Today | Should be |
|---|---|---|---|---|
| 1 | landlord, lives Leon, rental in Duval | landlords with property in Duval | Does Not Appear to Apply | Applies (needs the property county) |
| 2 | renter, lives Duval, rents in Duval | tenants in Duval | Applies | Applies |
| 3 | employee, lives Duval, works Miami-Dade | employees in Miami-Dade | Does Not Appear to Apply | Applies (needs the workplace county) |
| 4 | business owner, home Leon, business in Duval | businesses in Duval | Does Not Appear to Apply | Applies |
| 5 | homeowner, two homes (Duval, Leon) | homes in Leon | Depends on which county was typed | Applies (several places) |
| 6 | county official | rule on counties | Asked where they live | Not asked where they live |
| 7 | landlord, unknown county | rule on Duval | Can't Determine, asks county | Same, with the property wording |

Rows 1, 3, 4, 5, 6 are the cases that would change.

## Constraints to keep

- Matching stays in the browser; answers never leave it (see the privacy page).
- Uncertainty stays visible: a place that cannot be determined is Can't Determine, never
  a silent no.
- No wording or model change ships until you resolve decision 1.
