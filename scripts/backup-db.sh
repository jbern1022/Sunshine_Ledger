#!/usr/bin/env bash
# Sunshine Ledger — off-box database backup.
#
# Dumps the Postgres/PostGIS database from inside the running db container,
# verifies the dump is actually restorable, then rsyncs it to a separate
# physical host (the Pi) so a Sunshine Ledger deployment or Omen disk
# failure doesn't take the data with it.
#
# Run from the Omen docker host itself (crontab), not from a dev machine --
# it operates on the locally-running `sunshineledger-db-1` container.
#
# Retention: keeps the last 14 daily dumps locally and on the remote host;
# older ones are pruned automatically.

set -euo pipefail

CONTAINER="sunshineledger-db-1"
DB_USER="sunshine"
DB_NAME="sunshine_ledger"
BACKUP_DIR="/home/joe/sunshineledger-backups"
REMOTE_HOST="joe@192.168.4.2"
REMOTE_KEY="$HOME/.ssh/sunshineledger_backup_key"
RETENTION_DAYS=14

# A real dump of this database is ~2.2MB. Anything under this is a
# truncated or empty write, not a small database -- on 2026-08-21 a full
# disk produced a 0-byte file that looked like a successful backup until
# the log was read by hand.
MIN_DUMP_BYTES=$((512 * 1024))

# pg_dump needs room for the dump itself plus working space. Checked up
# front so a doomed run fails immediately and loudly, rather than after
# writing a partial file.
MIN_FREE_KB=$((1024 * 1024)) # 1 GiB

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DUMP_FILE="sunshineledger-${TIMESTAMP}.dump"
HOST_PATH="${BACKUP_DIR}/${DUMP_FILE}"

mkdir -p "$BACKUP_DIR"

fail() {
    echo "[$(date)] BACKUP FAILED: $*" >&2
    exit 1
}

# Never leave a partial dump behind: a 0-byte file in the backup directory
# is worse than no file, because it looks like a backup exists.
cleanup_partial() {
    local code=$?
    if [ $code -ne 0 ]; then
        rm -f "$HOST_PATH"
        docker exec "$CONTAINER" rm -f "/tmp/${DUMP_FILE}" 2>/dev/null || true
        echo "[$(date)] Cleaned up partial dump after failure (exit ${code})." >&2
    fi
}
trap cleanup_partial EXIT

echo "[$(date)] Starting backup: ${DUMP_FILE}"

# Prune BEFORE dumping, not after. When the disk fills, the old code
# aborted at the dump step and never reached its prune -- so the next run
# had no more space than the last one and failed the same way. Pruning
# first breaks that feedback loop.
find "$BACKUP_DIR" -name "sunshineledger-*.dump" -mtime "+${RETENTION_DAYS}" -delete

FREE_KB=$(df --output=avail -k "$BACKUP_DIR" | tail -1 | tr -d ' ')
if [ "$FREE_KB" -lt "$MIN_FREE_KB" ]; then
    fail "only $((FREE_KB / 1024))MB free in ${BACKUP_DIR}, need $((MIN_FREE_KB / 1024))MB"
fi

# Custom format (-F c): compressed, supports selective/parallel restore.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f "/tmp/${DUMP_FILE}" \
    || fail "pg_dump returned non-zero"

# Verify the archive is readable before trusting it. pg_restore --list
# exits non-zero on a truncated or corrupt archive, which catches the
# failure mode a size check alone would miss.
docker exec "$CONTAINER" pg_restore --list "/tmp/${DUMP_FILE}" >/dev/null \
    || fail "dump is not a readable pg_dump archive"

docker cp "${CONTAINER}:/tmp/${DUMP_FILE}" "$HOST_PATH" || fail "docker cp out of container failed"
docker exec "$CONTAINER" rm -f "/tmp/${DUMP_FILE}"

DUMP_BYTES=$(stat -c %s "$HOST_PATH")
if [ "$DUMP_BYTES" -lt "$MIN_DUMP_BYTES" ]; then
    fail "dump is ${DUMP_BYTES} bytes, expected at least ${MIN_DUMP_BYTES} -- treating as truncated"
fi

echo "[$(date)] Dump created and verified: $(du -h "$HOST_PATH" | cut -f1)"

# Push off-box. The remote key is restricted (rrsync, write-only, this
# directory only) -- see docs/RUNBOOK.md for how it was set up.
rsync -avz -e "ssh -i ${REMOTE_KEY} -o StrictHostKeyChecking=accept-new" \
    "$HOST_PATH" "${REMOTE_HOST}:" || fail "rsync to ${REMOTE_HOST} failed"

echo "[$(date)] Pushed off-box to ${REMOTE_HOST}"
echo "[$(date)] Backup complete."
