#!/usr/bin/env bash
# Offline test for the network-step retry in scripts/run-ingestion.sh.
# A stub `docker` on PATH fails chosen steps a set number of times
# ($W/fail/<module> holds how many more calls should fail).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
mkdir -p "$W/bin" "$W/fail"
cat > "$W/bin/docker" <<STUB
#!/usr/bin/env bash
# docker exec CONTAINER cmd...
shift 2
[ "\$1" = printenv ] && exit 0                       # READ_ONLY unset
args=\$(printf '%s ' "\$@")
case "\$args" in *nightly_state_sync*) key=nightly_state_sync ;; *) key=\$(echo "\$args" | grep -oE 'app[.][a-z_.]+' | head -1) ;; esac
echo "\$key" >> "$W/calls"
f="$W/fail/\$key"
if [ -s "\$f" ] && [ "\$(cat "\$f")" -gt 0 ]; then echo \$(( \$(cat "\$f") - 1 )) > "\$f"; exit 1; fi
exit 0
STUB
chmod +x "$W/bin/docker"
run() { PATH="$W/bin:$PATH" NET_RETRY_WAIT_MINUTES=0 INGESTION_PUSH_URL='' bash "$HERE/run-ingestion.sh" >"$W/out" 2>&1; }
fail() { echo "FAIL: $*"; cat "$W/out"; exit 1; }

# 1. A network step that fails once recovers on the retry: run succeeds.
echo 1 > "$W/fail/nightly_state_sync"
run || fail "run failed although LegiScan recovered on retry"
grep -q "RECOVERED on retry: LegiScan state bills" "$W/out" || fail "no recovery line"
[ "$(grep -c nightly_state_sync "$W/calls")" = 2 ] || fail "LegiScan not called exactly twice"

# 2. A network step that keeps failing still fails the run, named once.
: > "$W/calls"; echo 5 > "$W/fail/app.pipeline.legistar"
if run; then fail "run succeeded although Legistar failed twice"; fi
grep -q "INGESTION FAILED: 1 step(s) -- Legistar (nightly cities)" "$W/out" || fail "wrong failure summary"
[ "$(grep -c 'app.pipeline.legistar' "$W/calls")" = 2 ] || fail "Legistar not retried exactly once"

# 3. A non-network step (Ollama) is not retried.
: > "$W/calls"; rm -f "$W/fail/"*; echo 5 > "$W/fail/app.pipeline.summarize_batch"
if run; then fail "run succeeded although Summarize failed"; fi
[ "$(grep -c summarize_batch "$W/calls")" = 1 ] || fail "Summarize was retried"
grep -q "one retry in" "$W/out" && fail "retry phase ran with no network failures"

echo "run-ingestion retry: all checks passed"
