# Milestone step 1: trust defects, status and release restrictions (2026-11-10)

Todoist `6hr2RCQF3JX5cXWG` (coordination only; the fixes live in their own tickets). "Complete when each
relevant fix has regression evidence and deployed behavior is checked, or outstanding release
restrictions are explicitly recorded." This file is that record. Live checks below were read from the
public API on 2026-11-10 with no authentication and no writes.

| Dependency | Fix | Regression evidence in the repo | Deployed behavior checked 2026-11-10 | State |
|---|---|---|---|---|
| Coverage and freshness `6hr2PVw88gQhp6Xp` | Per-source counts by jurisdiction, and a visible "stale" state when a source has not been checked | commit `a2695e0` (the five 2026-10-26 audit findings); `CoverageSummary`, `DataFreshness` tests | `/sources/status` returns 37 sources, each with `last_checked_at`, `stale`, `bill_count`, `bills_with_text`. The paused GDELT source shows `stale: true` (last checked 2026-10-03), so unavailable freshness is exposed, not hidden. 33 of 35 city and state sources were checked within the 04:00 UTC run. | **Done** |
| Privacy disclosure for Impact Lens browser storage `6hr2PVxF9GQhQmvG` | `/privacy` states what the check keeps, where, and that nothing is sent | `app/privacy/page.test.tsx` pins the sentence; wording updated for property, workplace and several counties in this branch | Not deployed yet for the multi-county wording (this branch is unpushed); the earlier wording is live | **Done; this branch's wording awaits deploy** |
| Mapping review lifecycle `6hhJ73hVHcx9RpGG` | Rejection is terminal and withheld from readers; one selection rule; nightly mapping with review-by-risk hold (option B) | `docs/IMPACT_LENS_REVIEW_LIFECYCLE.md`; `tests/test_impact_lens_review.py`, `test_impact_lens_api.py` (held, withdrawn, approved cases) | Lifecycle live; the hold and nightly step are on this unpushed branch | **Built; awaits deploy** |
| Wrong-mapping baseline `6hhJ73W24crJhrwp` | Hand-label the H.B. 1389 and S.B. 1166 criteria sheets | `app.impact_lens.tally` counts verdicts; **no labeled sheets are in the repo** | n/a | **Open, needs the owner's labeling** |

## Release restrictions that stay in force (recorded, not waived)

1. **The Impact Lens remains behind `?lens=1`.** It is not linked from any bill page for readers who do not add
   the parameter. It stays that way until the baseline above is labeled and read.
2. **Risk-gated mapping expansion is limited to option B:** mappings are stored nightly, but a mapping that
   needs review is held from readers until a person approves it. Nothing is auto-approved. Widening that
   (showing more unreviewed mappings) is disabled until the baseline's accepted validation gate is met.
3. **The multi-place and multi-role controls** are behind the same flag and unreleased.
4. **No public registration, no accounts, no entitlements in use.** The auth and entitlement code is
   foundation only and has no routes.

## What a reader of this status should do

* Deploy the unpushed branch when on the network (CI does the backend; the host script `run-ingestion.sh`
  is re-installed by hand).
* Label the two baseline sheets (`python -m app.impact_lens.map_batch --bill "HB 1389" --export sheet.md`,
  fill the Verdict lines, then `python -m app.impact_lens.tally sheet.md`).
* After deploy, re-check this table against the live site and update the "deployed" column.

## Observations from today's live check (for the next nightly)

* Miami (`iqm2_miami`) shows `last_checked_at` 04:12 UTC on 2026-11-10, written by the nightly that ran
  **before** the iQM2 pacing release was installed on the host. The new behavior (the date moves only when
  a cycle finishes; a stopped run records "incomplete") should be visible after the next nightly. If it
  moves again tomorrow with `bill_count` unchanged, check `crawl_checkpoints` before trusting it.
* `bills_with_text` is 0 for both Miami and the federal source, as their notes say.
