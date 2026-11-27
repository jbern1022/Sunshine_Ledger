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
grep -q "added:   COGNITO_CLIENT_SECRET" <<<"$out" || fail "pull did not report the added key"
grep -q "changed: OLLAMA_HOST" <<<"$out" || fail "pull did not report the changed key"
grep -q -e topsecret -e secret-db -e "http://" <<<"$out" && fail "pull printed a value"
out=$(ls -A "$W/local/"); grep -q '\.env\.bak-' <<<"$out" || fail "pull made no backup"
[ "$(stat -c %a "$W/local/.env" 2>/dev/null || stat -f %Lp "$W/local/.env")" = 600 ] || fail "pull mode is not 600"
cmp -s "$W/local/.env" "$FAKE/sunshine-ledger/deploy.env" || fail "pull content differs"

# diff: names only
printf 'NEW_KEY=v\n' >> "$W/local/.env"
out=$("$S" diff "$W/local/.env"); grep -q "added:   NEW_KEY" <<<"$out" || fail "diff missed NEW_KEY"

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
out=$(ls -A "$FAKE/sunshine-ledger/"); grep -q 'deploy\.env\.bak-' <<<"$out" || fail "push made no server backup"

# ssm-diff / ssm-push against a stub `aws` that keeps parameters as files.
mkdir -p "$W/ssm"
cat > "$W/bin/aws" <<STUB
#!/usr/bin/env bash
D="$W/ssm"
case "\$2" in
  get-parameters-by-path)
    python3 - "\$D" <<'PY'
import json, os, sys
d = sys.argv[1]
print(json.dumps({"Parameters": [{"Name": "/sunshine-ledger/prod/env/" + n, "Value": open(os.path.join(d, n)).read()} for n in sorted(os.listdir(d))]}))
PY
    ;;
  put-parameter)
    while [ \$# -gt 0 ]; do case "\$1" in --name) n="\${2##*/}"; shift;; --value) v="\${2#file://}"; shift;; esac; shift; done
    cp "\$v" "\$D/\$n" ;;
esac
STUB
chmod +x "$W/bin/aws"; export AWS="$W/bin/aws"
printf 'postgres://secret-db' > "$W/ssm/DATABASE_URL"   # same as the server
printf 'stale' > "$W/ssm/OLLAMA_HOST"                    # differs
printf 'x' > "$W/ssm/ONLY_IN_SSM"                        # not on the server
out=$("$S" ssm-diff)
grep -q "missing or changed in SSM: .*OLLAMA_HOST" <<<"$out" || fail "ssm-diff missed the changed key"
grep -q "missing or changed in SSM: .*NEW_KEY" <<<"$out" || fail "ssm-diff missed the missing key"
grep -q "DATABASE_URL" <<<"$out" && fail "ssm-diff reported an unchanged key"
grep -q "only in SSM (left alone):  ONLY_IN_SSM" <<<"$out" || fail "ssm-diff missed the SSM-only key"
if "$S" ssm-push >/dev/null 2>&1; then fail "ssm-push without --yes succeeded"; fi
[ "$(cat "$W/ssm/OLLAMA_HOST")" = stale ] || fail "ssm-push without --yes wrote"
out=$("$S" ssm-push --yes)
grep -q -e topsecret -e secret-db -e "http://" <<<"$out" && fail "ssm-push printed a value"
[ "$(cat "$W/ssm/OLLAMA_HOST")" = "$(sed -n 's/^OLLAMA_HOST=//p' "$FAKE/sunshine-ledger/deploy.env")" ] || fail "ssm-push wrote the wrong value"
[ "$(cat "$W/ssm/COGNITO_CLIENT_SECRET")" = topsecret ] || fail "ssm-push did not add the missing key"
[ -e "$W/ssm/ONLY_IN_SSM" ] || fail "ssm-push deleted an SSM-only key"
out=$("$S" ssm-push --yes); grep -q "SSM is up to date." <<<"$out" || fail "second ssm-push was not a no-op"

echo "sync-env: all checks passed"
