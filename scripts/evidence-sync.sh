#!/usr/bin/env bash
# Sunshine Ledger: nightly evidence vault sync and signed fingerprint list
# (AWS $100 gate: S3 Object Lock vault + KMS-signed daily fingerprints).
#
# Run on docker-host from cron after the 03:00 database backup:
#   45 3 * * * /home/joe/scripts/evidence-sync.sh >> /home/joe/scripts/evidence.log 2>&1
#
# 1. Copies new promise snapshots (raw pages from the crawler, named by their
#    own SHA-256) from the `sunshineledger_snapshots` volume to the vault under
#    snapshots/. The vault has Object Lock (GOVERNANCE, 365 days), so nothing
#    copied there can be altered or deleted by this host's credential.
# 2. Writes a manifest: SHA-256 of the newest database dump (its off-site copy
#    is s3://<backups bucket>/backups/<same name>) and of every snapshot first
#    seen today, plus the SHA-256 of the previous manifest, so the manifests
#    form a chain and a missing or replaced day breaks it.
# 3. Signs the manifest's SHA-256 with the KMS key (ECDSA P-256; the private key
#    never leaves AWS) and stores manifest + signature under manifests/.
#
# Anyone can verify with the public key in docs/evidence-signing-public-key.pem:
#   openssl dgst -sha256 -verify evidence-signing-public-key.pem -signature DAY.json.sig DAY.json
#
# Credential: profile `sunshine-backup` (write-only: PutObject on snapshots/* and
# manifests/*, list snapshots/, kms:Sign with this key). It cannot read back,
# delete or bypass the lock.
set -euo pipefail

VAULT="${EVIDENCE_VAULT:-sunshine-ledger-evidence-269314582841-us-east-2-an}"
KEY="${EVIDENCE_KEY:-alias/sunshine-ledger-evidence-signing}"
PROFILE="${EVIDENCE_PROFILE:-sunshine-backup}"
REGION=us-east-2
VOLUME="${SNAPSHOT_VOLUME:-sunshineledger_snapshots}"
BACKUP_DIR="${BACKUP_DIR:-/home/joe/sunshineledger-backups}"
STATE_DIR="${EVIDENCE_STATE_DIR:-/home/joe/evidence-manifests}"
DOCKER="${DOCKER:-docker}"
AWS="${AWS:-aws}"

log() { echo "[$(date -u +%FT%TZ)] evidence: $*"; }
fail() { log "FAILED: $*"; exit 1; }

mkdir -p "$STATE_DIR"
DAY=$(date -u +%F)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

# --- 1. snapshots: hash everything in the volume, sync the new ones --------
# The volume is root-owned, so a throwaway container reads it.
"$DOCKER" run --rm -v "$VOLUME":/s:ro alpine:3 sh -c 'cd /s && find . -type f -exec sha256sum {} +' \
  | sed 's#  \./#  #' | sort -k2 > "$TMP/all.txt" || fail "could not read volume $VOLUME"
touch "$STATE_DIR/seen.txt"
comm -13 <(sort -k2 "$STATE_DIR/seen.txt") "$TMP/all.txt" > "$TMP/new.txt"
NEW=$(wc -l < "$TMP/new.txt" | tr -d ' ')
if [ "$NEW" -gt 0 ]; then
  "$DOCKER" run --rm -v "$HOME/.aws:/root/.aws:ro" -v "$VOLUME":/s:ro amazon/aws-cli \
    --profile "$PROFILE" --region "$REGION" s3 sync /s "s3://$VAULT/snapshots/" --size-only --only-show-errors \
    || fail "snapshot sync"
fi
log "snapshots: $(wc -l < "$TMP/all.txt" | tr -d ' ') in volume, $NEW new"

# --- 2. manifest -------------------------------------------------------------
DUMP=$(ls -1t "$BACKUP_DIR"/sunshineledger-*.dump 2>/dev/null | head -1 || true)
[ -n "$DUMP" ] || fail "no dump in $BACKUP_DIR"
PREV=$(ls -1 "$STATE_DIR"/*.json 2>/dev/null | grep -v "/$DAY.json$" | tail -1 || true)

python3 - "$DAY" "$DUMP" "$TMP/new.txt" "${PREV:-}" "$VAULT" > "$TMP/$DAY.json" <<'PY'
import hashlib, json, os, sys, datetime
day, dump, new, prev, vault = sys.argv[1:6]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
snaps = []
for line in open(new):
    digest, path = line.rstrip("\n").split("  ", 1)
    snaps.append({"path": f"snapshots/{path}", "sha256": digest})
print(json.dumps({
    "date": day,
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "publisher": "Sunshine Ledger",
    "vault": f"s3://{vault}/",
    "database_dump": {"name": os.path.basename(dump), "bytes": os.path.getsize(dump), "sha256": sha(dump),
                      "offsite_copy": f"backups/{os.path.basename(dump)}"},
    "new_snapshots": snaps,
    "previous_manifest": ({"name": os.path.basename(prev), "sha256": sha(prev)} if prev else None),
    "verify": "openssl dgst -sha256 -verify evidence-signing-public-key.pem -signature <date>.json.sig <date>.json",
}, indent=2, sort_keys=True))
PY

# --- 3. sign and store -------------------------------------------------------
openssl dgst -sha256 -binary "$TMP/$DAY.json" > "$TMP/digest.bin"
"$AWS" --profile "$PROFILE" --region "$REGION" kms sign --key-id "$KEY" --message-type DIGEST \
  --message "fileb://$TMP/digest.bin" --signing-algorithm ECDSA_SHA_256 --query Signature --output text \
  | base64 -d > "$TMP/$DAY.json.sig" || fail "kms sign"
[ -s "$TMP/$DAY.json.sig" ] || fail "empty signature"
for f in "$DAY.json" "$DAY.json.sig"; do
  "$AWS" --profile "$PROFILE" --region "$REGION" s3 cp --only-show-errors "$TMP/$f" \
    "s3://$VAULT/manifests/${DAY:0:4}/$f" || fail "upload $f"
done
cp "$TMP/$DAY.json" "$TMP/$DAY.json.sig" "$STATE_DIR/"
cat "$TMP/new.txt" >> "$STATE_DIR/seen.txt"
log "manifest $DAY signed and stored: dump $(basename "$DUMP"), $NEW new snapshot(s)"
