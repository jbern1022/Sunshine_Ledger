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
# alembic revision/apply steps, which are one-off and reviewed by hand.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
ENV_FILE="$REPO_ROOT/.env"
PROJECT_NAME="sunshineledger"
DOCKER_CONTEXT="sunshine-vm"

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

COMPOSE=(docker --context "$DOCKER_CONTEXT" compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

echo "==> Building backend + frontend..."
"${COMPOSE[@]}" build backend frontend

echo "==> Applying..."
"${COMPOSE[@]}" up -d

echo "==> Deploy complete. Running smoke test..."
"$SCRIPT_DIR/smoke-test.sh"
