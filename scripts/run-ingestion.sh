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

set -euo pipefail

CONTAINER="sunshineledger-backend-1"
WITH_GDELT="${1:-}"

run() {
  docker exec "$CONTAINER" python -c "$1"
}

echo "[$(date)] Starting scheduled ingestion run."

run "
from app.db import SessionLocal
from app.pipeline.legiscan import ingest_state_bills
db = SessionLocal()
written = ingest_state_bills(db)
print(f'LegiScan: {len(written)} bills changed/new')
"

run "
from app.db import SessionLocal
from app.pipeline.legistar import ingest_local_bills
db = SessionLocal()
written = ingest_local_bills(db, client_name='jaxcityc', limit=200)
print(f'Legistar (jaxcityc): {len(written)} bills upserted')
"

echo "[$(date)] Miami iQM2 scrape"
docker exec "$CONTAINER" python -m app.pipeline.miami_iqm2

echo "[$(date)] Summarizing new bills"
docker exec "$CONTAINER" python -m app.pipeline.summarize_batch

if [ "$WITH_GDELT" = "--with-gdelt" ]; then
  echo "[$(date)] GDELT headline refresh (slow -- expect multiple hours)"
  docker exec "$CONTAINER" python -m app.pipeline.gdelt
fi

echo "[$(date)] Scheduled ingestion run complete."
