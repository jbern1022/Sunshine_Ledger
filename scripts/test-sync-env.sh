#!/usr/bin/env bash
# Dry-run test for scripts/sync-env.sh against a fake "server" directory.
# No network, no real host: ssh/scp are stubs mapping "docker:PATH" to $FAKE/PATH.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
FAKE="$W/server"; mkdir -p "$FAKE/sunshine-ledger" "$W/bin" "$W/local"
cat > "$W/bin/scp" <<STUB
#!/usr/bin/env bash
args=(); for a in "\$@"; do [ "\$a" = -q ] || args+=("\${a/docker:/$FAKE/}"); done
cp "\${args[0]}" "\${args[1]}"
STUB
cat > "$W/bin/ssh" <<STUB
#!/usr/bin/env bash
shift; cd "$FAKE" && bash -c "\$*"
STUB
chmod +x "$W/bin/"*
export SSH="$W/bin/ssh" SCP="$W/bin/scp"
S="$HERE/sync-env.sh"
fail() { echo "FAIL: $*"; exit 1; }

printf 'DATABASE_URL=postgres://secret-db\nOLLAMA_HOST=http://x\nCOGNITO_CLIENT_SECRET=topsecret\n' > "$FAKE/sunshine-ledger/deploy.env"
printf 'DATABASE_URL=postgres://secret-db\nOLLAMA_HOST=http://old\n' > "$W/local/.env"

# pull: backs up, installs 600, names only
out=$("$S" pull "$W/local/.env")
echo "$out" | grep -q "added:   COGNITO_CLIENT_SECRET" || fail "pull did not report the added key"
echo "$out" | grep -q "changed: OLLAMA_HOST" || fail "pull did not report the changed key"
echo "$out" | grep -q -e topsecret -e secret-db -e "http://" && fail "pull printed a value"
ls -A "$W/local/" | grep -q '\.env\.bak-' || fail "pull made no backup"
[ "$(stat -c %a "$W/local/.env" 2>/dev/null || stat -f %Lp "$W/local/.env")" = 600 ] || fail "pull mode is not 600"
cmp -s "$W/local/.env" "$FAKE/sunshine-ledger/deploy.env" || fail "pull content differs"

# diff: names only
printf 'NEW_KEY=v\n' >> "$W/local/.env"
out=$("$S" diff "$W/local/.env"); echo "$out" | grep -q "added:   NEW_KEY" || fail "diff missed NEW_KEY"

# push refuses when a server key would be dropped
printf 'DATABASE_URL=postgres://secret-db\n' > "$W/local/stale.env"
if "$S" push "$W/local/stale.env" --yes 2>"$W/err"; then fail "push of a stale file succeeded"; fi
grep -q "COGNITO_CLIENT_SECRET" "$W/err" || fail "refusal did not name the missing key"
grep -q topsecret "$W/err" && fail "refusal printed a value"
grep -q topsecret "$FAKE/sunshine-ledger/deploy.env" || fail "server file was touched by a refused push"

# push without --yes does nothing
if "$S" push "$W/local/.env" >/dev/null 2>&1; then fail "push without --yes succeeded"; fi
grep -q NEW_KEY "$FAKE/sunshine-ledger/deploy.env" && fail "push without --yes changed the server"

# push with --yes: server backed up, replaced, mode 600
"$S" push "$W/local/.env" --yes >/dev/null
grep -q NEW_KEY "$FAKE/sunshine-ledger/deploy.env" || fail "push did not replace the server file"
ls -A "$FAKE/sunshine-ledger/" | grep -q 'deploy\.env\.bak-' || fail "push made no server backup"

echo "sync-env: all checks passed"
