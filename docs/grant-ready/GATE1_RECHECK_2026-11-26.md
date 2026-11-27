# Gate 1 re-check (2026-11-26, evening ET)

Gate 1 (Todoist `6j2GVjh4FvRHPqqG`) passed earlier on 2026-11-26 on the evidence in
`W1_BASELINE_2026-11-25.md` section 4. This page refreshes that evidence a day later and
records what moved. Read from the public site and API at 2026-11-27 03:05 UTC, no
authentication, no writes.

## (a) Live status

| Check | 2026-11-26 (baseline) | Now |
|---|---|---|
| Site | 200 (root 307 to the automatic jurisdiction pick) | Same, 0.31 s |
| API `/health` | 200 | 200 in 0.14 s, `read_only: false` (home origin, not the AWS standby) |
| API `/health/data` | **503 "stale"**: 370 bills reported as stuck (D2) | **200 "ok"**: 0 bills missing a summary of 21,070 |
| Last ingest | 2026-11-25 04:31 UTC | 2026-11-26 05:57 UTC (21 h before this check) |
| Sources | 33 of 37 fresh; LegiScan and Miami stale (D1, D4) | **36 of 37 fresh**; only GDELT stale (D7, decision pending) |
| LegiScan | Last check 2026-11-24 (DNS failure) | 2026-11-26 04:00 UTC; 5,840 bills, all with text |
| Miami (iQM2) | Last check 2026-11-24 | 2026-11-26 05:07 UTC |
| Jacksonville | — | 2026-11-26 04:00 UTC; 575 records, 535 with text |
| Bills in the default view | 16,590 | 20,681 (21,070 including roll-call-only federal bills) |

## (b) Coverage and the election calendar

Unchanged and correct: the 2026 calendar is finished (`verify_by` 2026-11-04 has passed and
is not raised as a fault, by design). 2027 Regular Session has 17 pre-filed bills.

## (c) Defects from the baseline

| # | Was | Now |
|---|---|---|
| D1 | State bills not refreshed (host DNS) | LegiScan fresh. A one-time retry of network steps is merged (`run-ingestion.sh`), but the host copy is installed only when the owner runs `install-host-scripts.sh`. Root cause (Pi first in the host's resolver list) still open. |
| D2 | `/health/data` permanently 503 | **Fixed and live** (see above). |
| D3 | Jacksonville 2026-0851-E layers generalize to "local governments" | **Fix on branch `fix/local-layers-context`** (not merged). Local records' prompts now name the government and instrument; generalizations the text doesn't make are dropped, with one retry; "shall be authorized" is read as a permission. Only city and county records regenerate. |
| D4 | Miami stale | Fresh. |
| D6 | LegiScan note lacked 2027 | **Fixed and live**. |
| D8 | Thin text outside Jacksonville | Disclosed: every source shows how many of its records have text. |
| D9 | 352 ended bills shown as "Introduced" | Bill pages fixed and live. **Filter and counts fixed on branch `fix/reader-status-filter`** (not merged): 2026 Regular Session "Introduced" drops from 352 to 2 (Replaced 209, Adopted 64, Died 47, Withdrawn 37, Tabled 2). |
| D5, D7 | Jacksonville history; GDELT | Deferred as before. |

## (d) Usage counts

Built and deployed dark (`usage_counts_enabled=False`). Switching on is the owner's decision
because `/privacy` must say so first.

## (e) Candidate sources

See `CAMPAIGN_SITES_2026.md`: campaign-site URLs for the 141 winners, found through
Ballotpedia's candidate pages (a directory: it points at sites, it is never crawled), ready
to load with `python -m app.promises.sites --csv` and snapshot with the crawler.
