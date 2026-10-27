# Free and professional feature matrix (working draft)

Status: DRAFT for Joe's review, 2026-10-27. Todoist `6hrFRCgWJGRXG2mG`; Notion "SL Pro 1".
Source of the rules: Notion "Professional features and gradual fee rollout" (accepted
direction, 2026-10-26) and the Trust & Accountability Doctrine. **Nothing here is built, priced
or promised.** Final packaging waits for the step 3 and 4 pilot evidence.

## Principles (accepted, not mine)

1. Free public findings, supporting sources and corrections are the planning baseline and stay free.
2. Charge only for monitoring convenience, reusable exports and collaboration.
3. Paying status never changes conclusions, inclusion, correction treatment or editorial review.
4. Impact Lens answers are never monetized (they stay in the browser; see the Impact Lens design).
5. Private customer notes are separate from public evidence and never become evidence by being saved.
6. Free at launch; fees introduced gradually, reversible and configurable. No automatic conversion,
   no promise of indefinite free professional access, no automatic enrollment in charges.

## Working packages (names, prices and quotas are proposals to validate)

| Package | Who it is for (hypothesis) | State |
|---|---|---|
| **Public** | Residents, journalists reading, anyone | Free, no account |
| **Research** (individual) | A reporter, researcher or advocate who returns to the same issues | Free pilot first |
| **Team** | A newsroom desk, civic group or research team sharing a workspace | After the individual pilot works |

## Matrix: every candidate capability

`Free` = always free, no account. `Pilot` = professional, free during the pilot, may become paid later.
`Later` = depends on work not started. "?" = undecided and recorded in the open-decisions list.

| # | Capability | Public | Research | Team | Depends on | Notes |
|---|---|---|---|---|---|---|
| 1 | Browse bills, local records, legislators, map, election calendar | Free | Free | Free | built | Never gated |
| 2 | Bill Says / Interpretation / Expected Effect / Who it affects, with sources | Free | Free | Free | built | Core findings never gated |
| 3 | Corrections log, corrections RSS, "Report a problem", right of reply | Free | Free | Free | built | Never gated (principle 1 and 3) |
| 4 | Public RSS feeds (bills, corrections) | Free | Free | Free | built | Already public |
| 5 | Impact Lens ("may I be impacted?") | Free | Free | Free | built | Answers stay in the browser (principle 4) |
| 6 | Methodology, data freshness, source list | Free | Free | Free | built | |
| 7 | Reader account (email, password hash, delete account) | n/a | Pilot | Pilot | auth task `6hWPfQj65r54vP8G` | Needed for anything saved on the server; open decision on sign-in method |
| 8 | Saved watchlists (bills, topics; people held until the legal review) | Free? | Pilot | Pilot | accounts | Basic watchlists may belong in Public; "?" |
| 9 | Alerts on watchlist changes (email or push) | no | Pilot | Pilot | outbound email, accounts | Blocked on email infrastructure; idempotent, unsubscribe required |
| 10 | Change digests (daily or weekly summary of watched items) | no | Pilot | Pilot | alerts | Monitoring convenience |
| 11 | Saved searches and filters | no | Pilot | Pilot | accounts | Shareable URLs for filters are free (built or planned) |
| 12 | Private notes on a bill or item | no | Pilot | Pilot | accounts | Kept apart from public evidence (principle 5) |
| 13 | Evidence export: cited, reproducible record of one bill, claim or case (PDF or Markdown) | no | Pilot | Pilot | end-to-end accountability record, source-rights check | Must carry sources, retrieval dates, version and corrections; format chosen from pilot |
| 14 | Briefing export (several items, one topic or jurisdiction) | no | Pilot | Pilot | 13 | Same rules as 13 |
| 15 | Bulk or API access | no | ? | ? | rate and cost model | Undecided; public API stays available for reading |
| 16 | Team workspace: shared watchlists, notes, exports | no | no | Pilot | accounts, roles | Minimum roles not yet chosen |
| 17 | Admin and billing for a team (seats, invoices) | no | no | Later | sandbox billing, provider and entity decision | Open: funding and entity decision `6hr2PW7jVHPG37vp` |
| 18 | Priority support or onboarding | no | ? | ? | | Optional; must not affect review priority |
| 19 | Reviewer or editorial priority for paying customers | **Never** | **Never** | **Never** | | Principle 3 |

## Pilot access (proposed, to confirm)

- Professional capabilities enabled by explicit grant, with an expiry date and an audit record. No card taken.
- On sign-up, plain text: selected professional features may become paid later; no commitment either way.
- No automatic conversion. A paid offer is an explicit opt-in with a price, notice period and cancellation.

## Downgrade and expiry behavior (proposed)

- When a grant ends, the account keeps working as a free reader account.
- Saved items are never deleted because a grant ended: watchlists and notes stay readable; new alerts,
  digests and exports stop; a user can export their own saved data once, free, at any time.
- Notice: at least 30 days before any change to what is free, by email and on the account page. (Proposal.)
- Public pages, sources and corrections are identical before and after.

## Open decisions (undecided; nothing is assumed)

Prices; quota sizes; pilot length; whether basic watchlists (8) are Public; whether bulk or API access (15)
is Research or Team; team role names; whether any early-user discount exists (the accepted direction does
not promise one); payment provider and legal entity; sign-in method; whether email verification is required.

## Public copy this will force (when anything ships)

`/privacy` currently states "No accounts, no login, no passwords" and "No payment processing"; both
must change before accounts or billing exist. The methodology page's "does not accept open or crowdsourced
edits" stays true; private notes are not edits to public content.

## Measurements the pilot needs (minimal data)

Per grant: capability used, count, date; per export: type and size; service cost per capability. No browsing
history, no content of notes, no Impact Lens answers. See "SL Pro 6" in Notion.
