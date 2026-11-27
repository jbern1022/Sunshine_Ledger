#!/usr/bin/env bash
# Tests scripts/evidence-sync.sh with fake docker and aws commands (no AWS, no Docker).
#   bash scripts/test-evidence-sync.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/backups" "$T/state"
echo "dump-bytes" > "$T/backups/sunshineledger-20261127-030001.dump"
: > "$T/calls"

# Fake docker: the alpine run prints the volume's hashes from $T/volume.txt.
cat > "$T/bin/docker" <<EOF
#!/usr/bin/env bash
echo "docker \$*" >> "$T/calls"
case "\$*" in *alpine*) cat "$T/volume.txt" ;; esac
EOF
# Fake aws: kms sign returns a base64 "signature"; s3 cp records the destination.
cat > "$T/bin/aws" <<EOF
#!/usr/bin/env bash
echo "aws \$*" >> "$T/calls"
case "\$*" in *"kms sign"*) printf 'fake-signature' | base64 ;; esac
EOF
chmod +x "$T/bin/"*

run() {
  PATH="$T/bin:$PATH" BACKUP_DIR="$T/backups" EVIDENCE_STATE_DIR="$T/state" HOME="$T" \
    bash "$HERE/evidence-sync.sh" > "$T/out" 2>&1 || { cat "$T/out"; return 1; }
}
fail() { echo "FAIL: $*"; cat "$T/out"; exit 1; }
DAY=$(date -u +%F)

# Night 1: two snapshots, nothing seen before.
printf '%s  ./ab/abc.html\n%s  ./cd/cde.html\n' "$(printf a%.0s {1..64})" "$(printf c%.0s {1..64})" > "$T/volume.txt"
run
M="$T/state/$DAY.json"
[ -f "$M" ] && [ -f "$M.sig" ] || fail "manifest and signature kept locally"
python3 - "$M" <<'PY' || fail "night 1 manifest"
import json, sys, hashlib
m = json.load(open(sys.argv[1]))
assert [s["path"] for s in m["new_snapshots"]] == ["snapshots/ab/abc.html", "snapshots/cd/cde.html"], m["new_snapshots"]
assert m["database_dump"]["sha256"] == hashlib.sha256(b"dump-bytes\n").hexdigest()
assert m["previous_manifest"] is None
PY
[ "$(cat "$M.sig")" = "fake-signature" ] || fail "signature decoded from base64"
grep -q "s3 sync /s s3://sunshine-ledger-evidence-269314582841-us-east-2-an/snapshots/" "$T/calls" || fail "snapshots synced"
grep -q "manifests/${DAY:0:4}/$DAY.json.sig" "$T/calls" || fail "signature uploaded"
grep -q -- "--signing-algorithm ECDSA_SHA_256" "$T/calls" || fail "signing algorithm"

# Night 2 (pretend the first manifest was yesterday's): one more snapshot.
mv "$M" "$T/state/2000-01-01.json"; mv "$M.sig" "$T/state/2000-01-01.json.sig"
printf '%s  ./ef/efg.html\n' "$(printf e%.0s {1..64})" >> "$T/volume.txt"
: > "$T/calls"
run
python3 - "$T/state/$DAY.json" "$T/state/2000-01-01.json" <<'PY' || fail "night 2 manifest"
import json, sys, hashlib
m = json.load(open(sys.argv[1]))
assert [s["path"] for s in m["new_snapshots"]] == ["snapshots/ef/efg.html"], m["new_snapshots"]
assert m["previous_manifest"] == {"name": "2000-01-01.json",
                                  "sha256": hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()}
PY

# Night 3: nothing new -> no sync call, manifest still written.
rm "$T/state/$DAY.json" "$T/state/$DAY.json.sig"; : > "$T/calls"
run
grep -q "s3 sync" "$T/calls" && fail "no sync when nothing is new"
grep -q "0 new" "$T/out" || fail "logs 0 new"

echo "evidence-sync: all tests passed"
