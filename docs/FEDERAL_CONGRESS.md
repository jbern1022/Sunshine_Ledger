# Florida's congressional delegation: roster, sponsorships, votes

Todoist 6hvxx9jPhj2Mp35p (roster), 6hvxx9hHg2G2cWjp (sponsorships and votes).

## Commands (the nightly runs all three)

```bash
python -m app.federal.roster                 # people + dated tenures from unitedstates/congress-legislators
python -m app.federal.sponsorships           # needs CONGRESS_API_KEY (free: api.congress.gov/sign-up); --api-key to override
python -m app.federal.rollcalls              # House Clerk + Senate roll-call XML, no key
```

## What is stored

- **Bills**: one entity per federal bill/resolution (`congress_bill` = `119-hr-10840`),
  `source_system="congress"`, with title, a coarse status from the latest action
  text (full text kept in `last_action`), and a link to Congress.gov.
- **Sponsorship**: `sponsor` / `co_sponsor` relationships from each Florida
  member's Congress.gov lists, current Congress only. These bills are marked
  `delegation_sponsored`.
- **Votes**: a `vote` event on the bill (the chamber's own totals) and a
  `voted` relationship for each Florida delegation member, from the chambers'
  roll-call XML. The House file keys members by Bioguide ID, the Senate by LIS
  ID (kept on the person as `lis_id`).

## Rules (owner decisions)

- **Summaries and tags only for delegation bills.** `app/federal/policy.py`
  is applied by the summarizer, layer generator, headline search and
  rhetoric check; every other federal bill is a title, a status and a link out.
  A bill first seen through a roll call has no description until a delegation
  member sponsors or cosponsors it.
- **Roll calls only.** A voice vote has no member-by-member record and is
  never attributed. Roll calls not about a bill or resolution (quorum calls,
  Speaker elections, nominations) are not stored.
- **No scores.** Plain counts and how each member voted.

## Verified and not

- Verified live 2026-11-10: House and Senate roll-call XML (both chambers
  parsed, Florida members matched, no robots.txt on either site); the
  Congress.gov sponsored-legislation response shape.
- Not verified live: the cosponsored-legislation response (the shared
  DEMO_KEY was rate-limited). The client falls back to the only list in a
  response if the key name differs and logs a warning. Run once with the real
  key and read the log.
- Sponsorships cover the current Congress only; earlier Congresses and
  withdrawn cosponsors are not handled.
- Not built: topic tags for delegation bills (the Congress.gov policy area is
  stored on the bill as `policy_area` for a later mapping), the bill and
  member pages' federal presentation, and original-cosponsor flags.
