#!/usr/bin/env bash
# Sunshine Ledger — backend test suite.
#
# Always targets the local Docker Desktop context, never the production
# remote host (`sunshine-vm`) -- the test stack is entirely ephemeral
# (tmpfs Postgres, distinct db name) and is torn down after every run
# regardless of pass/fail.

set -uo pipefail

docker --context desktop-linux compose -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from backend-test
STATUS=$?

docker --context desktop-linux compose -f docker-compose.test.yml down -v

exit $STATUS
