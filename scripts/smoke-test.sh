#!/usr/bin/env bash
set -uo pipefail

# Post-deploy smoke test. Run standalone (`scripts/smoke-test.sh`) or as the
# last step of scripts/deploy.sh.
#
# Exists because the 2026-09-20 outage's root cause -- NEXT_PUBLIC_API_URL
# baked to a localhost value at build time -- produced a completely healthy
# build, a completely healthy deploy, and a site that "worked" for anyone
# with something listening on localhost:8010, while failing silently for
# real visitors. Nothing about the deploy itself would have caught it;
# only checking the actual served output does.

PUBLIC_API_URL="${PUBLIC_API_URL:-https://sunshineledger-api.josephbernal.com}"
PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-https://sunshineledger.josephbernal.com}"
BAD_PATTERNS=("localhost:8010" "localhost:8000" "localhost:3010" "http://backend:8000")

fail=0

echo "==> Checking $PUBLIC_API_URL/health"
api_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_API_URL/health" 2>/dev/null || echo "000")"
if [[ "$api_status" != "200" ]]; then
  echo "FAIL: API health check returned $api_status" >&2
  fail=1
else
  echo "OK: API is up"
fi

echo "==> Fetching $PUBLIC_FRONTEND_URL"
homepage="$(curl -sL --max-time 10 "$PUBLIC_FRONTEND_URL" 2>/dev/null || true)"
if [[ -z "$homepage" ]]; then
  echo "FAIL: could not fetch $PUBLIC_FRONTEND_URL" >&2
  fail=1
else
  echo "OK: frontend responded"

  # NEXT_PUBLIC_* values only ever show up in the compiled JS chunks, not
  # the initial HTML, so pull every chunk the homepage references and scan
  # each one for a hardcoded dev/internal URL that should never reach a
  # browser.
  chunk_paths="$(grep -oE '/_next/static/chunks/[A-Za-z0-9._-]+\.js' <<<"$homepage" | sort -u)"
  if [[ -z "$chunk_paths" ]]; then
    echo "WARN: no /_next/static/chunks/*.js references found on the homepage -- skipping bundle scan" >&2
  else
    while IFS= read -r path; do
      [[ -z "$path" ]] && continue
      chunk="$(curl -sL --max-time 10 "$PUBLIC_FRONTEND_URL$path" 2>/dev/null || true)"
      for pattern in "${BAD_PATTERNS[@]}"; do
        if grep -qF "$pattern" <<<"$chunk"; then
          echo "FAIL: found '$pattern' baked into $path -- NEXT_PUBLIC_API_URL (or INTERNAL_API_URL) was wrong at build time" >&2
          fail=1
        fi
      done
    done <<<"$chunk_paths"
  fi
fi

if [[ "$fail" -eq 1 ]]; then
  echo "==> Smoke test FAILED" >&2
  exit 1
fi

echo "==> Smoke test passed"
