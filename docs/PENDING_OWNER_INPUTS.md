# What is left, and what each item waits for (2026-11-10)

Everything in the repo that engineering can finish without you is finished, merged and deployed (main). What
remains needs something only the owner can provide: an input, an access grant, a decision, or a date to pass.
Order is by how soon it matters.

## 1. Inputs and access (nothing to decide; I need the thing)

| Needed | Unblocks | How |
|---|---|---|
| **Winners CSV** from the Division of Elections results site (unofficial now, certified later) | The whole promises pipeline: winners, site discovery, crawl, extraction, review queue. Campaign sites go offline within weeks of Nov 3. | Download in a browser (the site returns 403 to scripts), then `docker exec sunshineledger-backend-1 python -m app.promises.winners FILE --source-url URL` (add `--certified` after certification). Campaign-site URLs: `sites --csv`. |
| **`CONGRESS_API_KEY`** (free, ~5 minutes at api.congress.gov/sign-up) | Federal sponsorships and cosponsorships, federal bill text, Florida-places findings, federal Who-it-affects layers, nightly. | Add to `~/sunshine-ledger/deploy.env` on the docker host, recreate the backend. Check the first log: the cosponsored response is unverified. |
| **AWS access** (a dev Cognito user pool, SES sender and domain records) | The Cognito integration, auth screens, recovery validation, email, alert sending. The adapter and everything behind it is built and tested without it. | Create the pool and a scoped IAM role; tell me the region. |
| **Hand-labeled baseline** for H.B. 1389 and S.B. 1166 | Lifting `?lens=1` on the Impact Lens (your bar: zero wrong mappings), and Milestone step 1. | `python -m app.impact_lens.map_batch --bill "HB 1389" --export sheet.md`, fill each `Verdict:` line, `python -m app.impact_lens.tally sheet.md`. Held mappings also wait in `python -m app.impact_lens.review --queue`. |
| **Admin credential rotation** or Cloudflare Access (MFA) in front of `/admin` | Closing the single-shared-password gap in `docs/ADMIN_ACCESS_AUDIT.md`. | Your call which; I can then verify. |
| **Apply the tag-quarantine migration** | `feat/tag-quarantine-rebased` (one head, tested). Merging it adds a second head until applied. | Run its alembic upgrade when ready; tell me and I merge. |
| **Run the prod title cleanup** | 135 of 400 Jacksonville titles still contain line breaks. | `python -m app.pipeline.title_cleanup --apply` on the host. |
| **Confirm the Randy Fine link** | The roster's one same-name candidate. | `python -m app.federal.roster --confirm F000484=7cc7a66c-1bf3-4a02-a629-44659884c7d5` |
| **Check the district plan dates** (2022-11-08) against enactment, and that no newer congressional plan exists | Accuracy of pre-2024 district history. | A quick lookup; tell me if the date is wrong. |
| **Dismiss the Dependabot alerts** (minimatch waits on upstream) | Tidying. | In GitHub. |

## 2. Decisions

| Decision | Why it is waiting | My recommendation |
|---|---|---|
| **Tampa / Orlando terms ruling** | The Tampa OnBase scraper (2 days) and Orlando are blocked on robots/terms; the dossier has the vendor's terms text. | Your call. |
| **Whether `official` follows are in the first public release** (`watchlists.ENABLED_KINDS`) | Official-following is the electioneering-adjacent kind; public release is gated on the scoped legal review anyway. | Ship bills and topics first, hold officials until the review. |
| **Whether to email GDELT** about the throttled address | Outreach is yours to send. | Optional; the bulk-file route avoids the need. |
| **Reuse of the committee project lists beyond a link-back** | Neither Appropriations site states a licence. | Keep to a link-back until confirmed. |
| **Pro: prices, quotas, pilot length, bulk/API tier, team roles, payment provider, legal entity** | Undecided by design; entitlements are built without them. | After the pilot evidence. |
| **Funding and entity structure** (`6hr2PW7jVHPG37vp`) | A decision, not engineering. | n/a |
| **Domain and trademark clearance** (`6h8mJfQjW2V8Rm9x`) | Yours. | n/a |
| **Lost-authenticator support review**: acceptable ownership proof, who may approve, escalation | Needed before public recovery; the gate in code is built. | Draft with counsel. |

## 3. Waiting on time or an event

* **Election certification** (date to check): winners reconcile, certified-results module, tenure-end reasons and
  the flag display, roster reconcile. The tenure-end flag is built to take the reason once it is known.
* **Tonight's nightly (04:00 UTC 2026-11-11)** verifies: the first run of the Impact Lens mapping step, iQM2
  pacing with Miami in the background, the new host script. A one-shot check is scheduled for 8:07 local while
  this session stays open; otherwise read the nightly log (`scripts/run-ingestion.sh` says where).
* The minimatch alert (upstream), tag slugs (more cities ingesting), the uncertainty review (~Oct 2027).
* First ingests for the 9 newest cities (docker host; spot-check once the nightly has run).

## 4. People, not code

Legal reviews (Phase 3 checkpoint, accounts and official-following, the other Bernal Labs reviews), reviewer
assignments, governance ownership, resident and journalist interviews, the validation research cases for the
accountability methodology (need your framework and review), news-analysis reviewers and thresholds (a pilot
of about 30 articles first).

## 5. Parked on purpose

Access Ledger, Pattern and Tenant Ledger, Judicial Sentencing Matrix, Phase 3 and nationwide items, subsidy and
eviction, floor-speech video pipeline, vetted-contributor quotes. Not Sunshine scope: the duplicate
`C:\OllamaModels` folder and Ollama auto-start after reboot (needs Powerstation access).

## What is built but switched off, and what is deliberately not built

Built, tested, deployed, and **dark** (404 until you flip a flag): reader accounts (`AUTH_ENABLED`, and
`NEXT_PUBLIC_AUTH_ENABLED` for the screens), public sign-up (`REGISTRATION_OPEN`, and
`NEXT_PUBLIC_REGISTRATION_OPEN`), sessions, the MFA gate, export and deletion, watchlists, the Follow button, alerts
and digests (queue only), entitlements. See `docs/ACCOUNTS_BUILD_STATUS.md`. Turning them on needs a real user pool
(section 1), the privacy-page change, SES, and the gates in Todoist `6hCMm7FWfJ47jCgp`.

Not built, because it needs the real pool or an input first:

* **MFA enrollment** (QR and manual key), **passkey registration**, and the **recovery request** screens: Cognito's
  token and challenge behavior must be observed in a dev pool before the flow is fixed.
* **Alert sending**: needs SES, a verified sender, unsubscribe and bounce handling.
* **Enacted-stage earmarks**: need the enacted laws' joint explanatory statement tables, and the lists' reuse terms.
* **News analysis in production**: no articles, no human labels, no frozen thresholds exist; public labels are gated.
* **Layer 3 of the Federal Impact Lens**: attributed estimates only when CBO or an agency publishes a Florida figure.
* **Official follow buttons**: wait for the legal review (topic buttons are on the filtered browse page).
