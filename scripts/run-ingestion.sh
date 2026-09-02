#!/usr/bin/env bash
# Sunshine Ledger — scheduled data ingestion.
#
# Runs from the Omen docker host itself (crontab), operating directly on
# the locally-running `sunshineledger-backend-1` container via `docker
# exec` -- no repo checkout needed on this host, the image already has
# the pipeline code baked in.
#
# Steps, in order: pull new/changed state bills (LegiScan), pull new
# local matters (Legistar: Jacksonville only -- Miami's Legistar client
# is stale, see docs/RUNBOOK.md), scrape Miami's real source (iQM2),
# summarize anything new, then (GDELT mode only) refresh news headlines.
#
# GDELT is deliberately NOT run on every invocation: it re-checks every
# bill in the database against GDELT's free DOC API (~8s/bill minimum
# throttle, heavy 429 rate limiting observed even with backoff), so a
# full pass takes multiple hours and hammers a free third-party API.
# Run it weekly, not daily -- see the crontab entries this pairs with.
#
# Usage: run-ingestion.sh [--with-gdelt]

# NOT `set -e`. The steps below are independent data sources, and an
# earlier failure must not cancel the later ones: a single over-long
# Jacksonville committee name crashed the Legistar step on four consecutive
# nights, and because the script aborted there, the Miami scrape and the
# summarization run never executed at all. Each step now records its own
# failure and the script reports them together at the end.
set -uo pipefail

# shellcheck source=monitoring.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/monitoring.sh"

CONTAINER="sunshineledger-backend-1"
WITH_GDELT="${1:-}"

FAILED_STEPS=()

# Run one pipeline step, isolating its failure from the rest of the run.
step() {
    local name="$1"
    shift
    echo "[$(date)] ${name}"
    if ! "$@"; then
        echo "[$(date)] STEP FAILED: ${name}" >&2
        FAILED_STEPS+=("$name")
    fi
}

py() {
    docker exec "$CONTAINER" python -c "$1"
}

echo "[$(date)] Starting scheduled ingestion run."

step "LegiScan state bills" py "
from app.db import SessionLocal
from app.pipeline.legiscan import ingest_state_bills
db = SessionLocal()
written = ingest_state_bills(db)
print(f'LegiScan: {len(written)} bills changed/new')
"

step "Legistar (jaxcityc)" py "
from app.db import SessionLocal
from app.pipeline.legistar import ingest_local_bills
db = SessionLocal()
written = ingest_local_bills(db, client_name='jaxcityc', limit=200)
print(f'Legistar (jaxcityc): {len(written)} bills upserted')
"

step "Miami iQM2 scrape" docker exec "$CONTAINER" python -m app.pipeline.miami_iqm2

step "Summarize new/changed bills" docker exec "$CONTAINER" python -m app.pipeline.summarize_batch

if [ "$WITH_GDELT" = "--with-gdelt" ]; then
    step "GDELT headline refresh" docker exec "$CONTAINER" python -m app.pipeline.gdelt
fi

if [ ${#FAILED_STEPS[@]} -gt 0 ]; then
    # Exit non-zero as well as pinging: the exit code is what a human sees
    # running this by hand, the ping is what reaches someone at 4am.
    echo "[$(date)] INGESTION FAILED: ${#FAILED_STEPS[@]} step(s) -- ${FAILED_STEPS[*]}" >&2
    # Name the failing steps in the alert. The four-night outage was one
    # step failing while the rest were fine; an alert that says which one
    # turns a debugging session into a glance.
    monitor_ping "${INGESTION_PUSH_URL:-}" down \
        "${#FAILED_STEPS[@]} step(s) failed: ${FAILED_STEPS[*]}" "$SECONDS"
    exit 1
fi

echo "[$(date)] Scheduled ingestion run complete (all steps OK)."
monitor_ping "${INGESTION_PUSH_URL:-}" up "all steps OK${WITH_GDELT:+ (with GDELT)}" "$SECONDS"
