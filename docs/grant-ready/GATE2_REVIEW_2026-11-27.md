# Gate 2 review: trust and recoverability for the chosen workflow

Todoist `6j2GVjgc3WRhpVpp` (W2, due 2026-11-27). Evidence gathered 2026-11-27 03:30 UTC from the public
API and the AWS account, no writes to production. Demo cases are the three proposed in
`W1_BASELINE_2026-11-25.md` section 3.

## Verdict

**Pass on (a), (b), (d), (e). (c) passes once tonight's nightly regenerates the Jacksonville layers**
(D3 fix merged 2026-11-26, main `d3f94ea`); check the record below on the morning of 11-27 and close.

## (a) Off-site restore

**Met.** On 2026-11-26 the AWS standby restored
`s3://sunshine-ledger-backups-269314582841/backups/sunshineledger-20261126-030001.dump` into a fresh PostGIS:
17,079 entities and 24,521 claims, equal to production's counts before the 03:00 dump; the API and site
answered locally. Repeated that day on main `7467246` (6.5 minutes, same counts). It repeats every Sunday
(`sunshine-standby-weekly-refresh`) and emails the result.

## (b) Demo sources: last successful checks and known gaps

| Demo case | Source | Last successful check | Text | Known gaps shown to readers |
|---|---|---|---|---|
| H.B. 1389 (2026 Regular), housing. Passed, Chapter 2026-179 | LegiScan (Florida Legislature text) | 2026-11-26 04:00 UTC | flsenate.gov bill page; 5,840 of 5,840 LegiScan bills have text | 55 actions. All four layers are AI-generated and marked "not reviewed". Census overlay loaded by hand 2026-11-10. |
| S.B. 1166 (2026 Regular), insurer drug-price disclosures. Died in committee | LegiScan | 2026-11-26 04:00 UTC | flsenate.gov bill page | 4 actions. Layers "not reviewed". Effects describe a bill that did not pass. |
| Jacksonville Ordinance 2026-0851-E, SHIP deadline extension. Awaiting Mayor's signature | Jacksonville Legistar | 2026-11-26 04:00 UTC | Legistar record; 535 of 575 Jacksonville records have text | **No action history** (Legistar history is not ingested, D5): the "how it became law" view is state-only. |

The site does not claim Florida-wide completeness: `/sources/status` shows, per source, how many records have
text (several county and city sources show 0), and GDELT is shown stale.

## (c) Highest-severity demonstration defects

| Defect | State |
|---|---|
| D3: Jacksonville ordinance's expected effect generalized to "local governments" | **Fixed in code** (`fix/local-layers-context`, merged). The record regenerates in the 11-27 nightly (local records only; ~790 over about two nights). Verify: `GET /bills/b6cb1f56-f224-4186-9e0e-132583b21d9c`, layers `created_at` 2026-11-27, no "local governments". If it has not regenerated, withhold the ordinance from the demo and use the state pair. |
| D9: ended bills shown as "Introduced" in filters | **Fixed and live** (2026 Regular: 352 to 2). |
| HB 1389 Who-it-affects leftovers (`6hgfjX9c3R5fXX2G`) | **Closed** 2026-11-26 after checking against the bill text. |
| Impact Lens wrong-mapping baseline unlabeled | **Withheld**: the lens stays behind `?lens=1` and is not part of the demo. |

## (d) Source-to-claim audit template

**Met.** `docs/grant-ready/SOURCE_TO_CLAIM_AUDIT_TEMPLATE.md` (sampling frame and strata, per-claim checks,
error codes, scoring), already used for accuracy samples 01 and 02.

## (e) Past-winner matrix with authoritative links

**Met.** `docs/grant-ready/PAST_WINNERS_COMPARISON.md`: Press Forward South Florida 2026 and Knight awards,
each row with its source link and a Confirmed / Implied / Not found label; no selection criteria inferred from
winners alone.
