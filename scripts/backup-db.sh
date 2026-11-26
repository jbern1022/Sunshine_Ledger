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
#
# Second off-site copy (optional until configured): when S3_BACKUP_BUCKET is
# set, the verified dump is also uploaded to S3 with a write-only credential
# (profile S3_BACKUP_PROFILE, default `sunshine-backup`: s3:PutObject on
# backups/* only). The script never lists, reads back or deletes in S3; the
# bucket's lifecycle rule handles expiry (30 days, old versions 7). See
# docs/RUNBOOK.md "Off-site backups to S3".

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

# S3 copy. Empty bucket = not configured yet: the step is skipped and says so.
S3_BACKUP_BUCKET="${S3_BACKUP_BUCKET:-}"
S3_BACKUP_PROFILE="${S3_BACKUP_PROFILE:-sunshine-backup}"
S3_BACKUP_REGION="${S3_BACKUP_REGION:-us-east-2}"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DUMP_FILE="sunshineledger-${TIMESTAMP}.dump"
HOST_PATH="${BACKUP_DIR}/${DUMP_FILE}"

# shellcheck source=monitoring.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/monitoring.sh"

# Last message passed to fail(), so the exit trap can report *why* rather
# than just that something went wrong. An alert saying "only 340MB free"
# is actionable at 3am; "backup failed" is not.
FAIL_REASON=""

# Set once the dump is verified and copied out of the container. After that
# point a failure (the Pi or S3 copy) must NOT delete the local dump: it is a
# good backup, and possibly the only off-box copy that worked.
DUMP_VERIFIED=0
OFFSITE_NOTE=""

fail() {
    FAIL_REASON="$*"
    echo "[$(date)] BACKUP FAILED: $*" >&2
    exit 1
}

# Never leave a partial dump behind: a 0-byte file in the backup directory
# is worse than no file, because it looks like a backup exists.
#
# The monitor ping lives here rather than at the end of the happy path so
# it fires on EVERY exit, including a `set -e` abort nobody anticipated.
# Those unhandled aborts are precisely the failures that went unnoticed
# before, so pinging only where we remembered to would miss them again.
on_exit() {
    local code=$?
    if [ $code -ne 0 ]; then
        docker exec "$CONTAINER" rm -f "/tmp/${DUMP_FILE}" 2>/dev/null || true
        if [ "$DUMP_VERIFIED" -eq 1 ]; then
            echo "[$(date)] Kept the verified local dump ${HOST_PATH} (exit ${code})." >&2
        else
            rm -f "$HOST_PATH"
            echo "[$(date)] Cleaned up partial dump after failure (exit ${code})." >&2
        fi
        monitor_ping "${BACKUP_PUSH_URL:-}" down \
            "${FAIL_REASON:-exited ${code} before completing}" "$SECONDS"
    else
        monitor_ping "${BACKUP_PUSH_URL:-}" up \
            "dump ${DUMP_BYTES_HUMAN:-unknown} pushed to ${REMOTE_HOST}${OFFSITE_NOTE}" "$SECONDS"
    fi
}
trap on_exit EXIT

# Installed AFTER the trap, deliberately. Anything failing before the trap
# exists dies silently, which is the exact failure mode this file is meant
# to remove -- so the trap goes up first and everything that can fail comes
# after it, mkdir included.
mkdir -p "$BACKUP_DIR"

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

DUMP_BYTES_HUMAN=$(du -h "$HOST_PATH" | cut -f1)
DUMP_VERIFIED=1
echo "[$(date)] Dump created and verified: ${DUMP_BYTES_HUMAN}"

# Push off-box. The remote key is restricted (rrsync, write-only, this
# directory only) -- see docs/RUNBOOK.md for how it was set up.
rsync -avz -e "ssh -i ${REMOTE_KEY} -o StrictHostKeyChecking=accept-new" \
    "$HOST_PATH" "${REMOTE_HOST}:" || fail "rsync to ${REMOTE_HOST} failed"

echo "[$(date)] Pushed off-box to ${REMOTE_HOST}"

# Second off-site copy, outside the house. Once configured, a failure here
# fails the run (and the Kuma push) even though the Pi copy succeeded: a
# warning nobody reads is how backup failures went unnoticed before.
if [ -z "$S3_BACKUP_BUCKET" ]; then
    echo "[$(date)] S3 copy skipped: S3_BACKUP_BUCKET is not set"
else
    command -v aws >/dev/null 2>&1 || fail "S3_BACKUP_BUCKET is set but the aws CLI is not installed"
    AWS_PROFILE="$S3_BACKUP_PROFILE" aws s3 cp "$HOST_PATH" \
        "s3://${S3_BACKUP_BUCKET}/backups/${DUMP_FILE}" \
        --region "$S3_BACKUP_REGION" --only-show-errors \
        || fail "S3 upload to ${S3_BACKUP_BUCKET} failed (the Pi copy succeeded)"
    OFFSITE_NOTE=" and S3"
    echo "[$(date)] Uploaded to s3://${S3_BACKUP_BUCKET}/backups/${DUMP_FILE}"
fi

echo "[$(date)] Backup complete."
