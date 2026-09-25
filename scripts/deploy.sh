#!/usr/bin/env bash
set -euo pipefail

# Canonical deploy path for Sunshine Ledger's backend + frontend.
#
# Always resolves the compose file and .env relative to this script's own
# location, never the caller's cwd or PATH -- the 2026-09-20 outage happened
# because a `docker compose` invocation somewhere picked up a stale
# scratchpad clone's compose file (and, through it, its .env) instead of the
# repo's own. Running everything through this one script means there's only
# ever one place that command gets typed.
#
# Does NOT run migrations -- see docs/RUNBOOK.md "Deploy / redeploy" for the
# alembic revision/apply steps, which are one-off and reviewed by hand. It
# does refuse to start new code against a database that is behind it (see
# "Migration check" below), since the Woodpecker pipeline now deploys every
# push to main without a human in the loop.
#
# Overrides (used by the Woodpecker deploy step, which runs on docker-host
# itself against the local Docker socket):
#   DEPLOY_DOCKER_CONTEXT   docker context to deploy to (default: sunshine-vm)
#   DEPLOY_ENV_FILE         production .env (default: <repo>/.env)
#   DEPLOY_PIPELINE_WAIT_MINUTES  how long to wait for a running pipeline
#                                 job to finish before giving up (default 30)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
ENV_FILE="${DEPLOY_ENV_FILE:-$REPO_ROOT/.env}"
PROJECT_NAME="sunshineledger"
DOCKER_CONTEXT="${DEPLOY_DOCKER_CONTEXT:-sunshine-vm}"
PIPELINE_WAIT_MINUTES="${DEPLOY_PIPELINE_WAIT_MINUTES:-30}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: expected compose file at $COMPOSE_FILE -- refusing to deploy" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: expected .env at $ENV_FILE -- refusing to deploy" >&2
  exit 1
fi

# NEXT_PUBLIC_* vars are inlined into the frontend's client JS at build time.
# A relative/localhost value here builds clean and deploys clean, then fails
# silently in every visitor's browser -- exactly what happened on
# 2026-09-20. Refuse to build with anything but a real public https origin.
if ! grep -qE '^NEXT_PUBLIC_API_URL=https://' "$ENV_FILE"; then
  echo "ERROR: NEXT_PUBLIC_API_URL in $ENV_FILE is not a public https:// URL -- refusing to bake a bad build" >&2
  grep '^NEXT_PUBLIC_API_URL=' "$ENV_FILE" >&2 || echo "  (not set at all)" >&2
  exit 1
fi

echo "==> Deploying from $REPO_ROOT"
echo "==> compose file: $COMPOSE_FILE"
echo "==> env file:      $ENV_FILE"
echo "==> context:        $DOCKER_CONTEXT  project: $PROJECT_NAME"

# --profile tunnel: the cloudflared services only start when asked for (see
# docker-compose.yml), and production is the one place that asks.
COMPOSE=(docker --context "$DOCKER_CONTEXT" compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile tunnel)

echo "==> Building backend + frontend..."
"${COMPOSE[@]}" build backend frontend

# Migration check: the database must already be at the revision the new code
# expects. Revisions come from the image just built, so a migration added in
# this push is seen. To ship one: let this fail, then run
#   docker compose ... run --rm backend alembic upgrade head
# (RUNBOOK "Manual commands"), which uses that same freshly built image, and
# deploy again.
revisions() { { grep -oE '^[0-9a-f]{12}' || true; } | sort | tr '\n' ' '; }
code_heads="$("${COMPOSE[@]}" run --rm --no-deps -T backend alembic heads 2>/dev/null | revisions)"
db_current="$("${COMPOSE[@]}" run --rm -T backend alembic current 2>/dev/null | revisions)"
if [[ -z "$code_heads" || "$code_heads" != "$db_current" ]]; then
  echo "ERROR: database is at [${db_current:-unknown}] but the new code expects [${code_heads:-unknown}]." >&2
  echo "       Apply the migration by hand (docs/RUNBOOK.md \"Manual commands\"), then deploy again." >&2
  exit 1
fi
echo "==> Database at expected revision: $code_heads"

# Don't restart the backend under a running pipeline job (the nightly
# ingestion runs its steps with `docker exec ... python -m app.pipeline.X`;
# recreating the container kills that step mid-run). The bracket in the
# pattern keeps grep from matching the shell running it.
backend_id="$("${COMPOSE[@]}" ps -q backend || true)"
if [[ -n "$backend_id" ]]; then
  deadline=$(( $(date +%s) + PIPELINE_WAIT_MINUTES * 60 ))
  while docker --context "$DOCKER_CONTEXT" exec "$backend_id" \
      sh -c 'grep -lsa "app[.]pipeline" /proc/[0-9]*/cmdline' >/dev/null 2>&1; do
    if (( $(date +%s) >= deadline )); then
      echo "ERROR: a pipeline job is still running after ${PIPELINE_WAIT_MINUTES} min -- not restarting the backend under it" >&2
      exit 1
    fi
    echo "==> A pipeline job is running in the backend; waiting..."
    sleep 60
  done
fi

echo "==> Applying..."
"${COMPOSE[@]}" up -d

echo "==> Deploy complete. Running smoke test..."
"$SCRIPT_DIR/smoke-test.sh"
