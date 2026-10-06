#!/usr/bin/env bash
set -euo pipefail

# Refuse to build when macOS/iCloud sync copies ("name 2.py") sit in the code
# that goes into the backend image. Git ignores them (.gitignore "* [0-9].*"),
# but deploy.sh builds from the working directory, so they ship: on 2026-10-06
# "b6d2f9a3c715_add_bill_layer_criteria 2.py" put the same Alembic revision in
# the image twice and `alembic upgrade head` failed with "multiple heads".
#
# Usage: check-no-sync-copies.sh [repo-root]   (default: this script's repo)

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

copies="$(find "$ROOT/backend/migrations" "$ROOT/backend/app" -type f -name '* [0-9].*' 2>/dev/null || true)"
if [[ -n "$copies" ]]; then
  echo "ERROR: sync copies found in code that ships in the backend image -- refusing to build:" >&2
  echo "$copies" | sed 's/^/  /' >&2
  echo "Compare each with its original, then delete the copy." >&2
  exit 1
fi
