#!/usr/bin/env bash
# Sunshine Ledger — off-box database backup.
#
# Dumps the Postgres/PostGIS database from inside the running db container,
# then rsyncs the dump to a separate physical host (the Pi) so a Sunshine
# Ledger deployment or Omen disk failure doesn't take the data with it.
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

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DUMP_FILE="sunshineledger-${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup: ${DUMP_FILE}"

# Custom format (-F c): compressed, supports selective/parallel restore.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f "/tmp/${DUMP_FILE}"
docker cp "${CONTAINER}:/tmp/${DUMP_FILE}" "${BACKUP_DIR}/${DUMP_FILE}"
docker exec "$CONTAINER" rm "/tmp/${DUMP_FILE}"

DUMP_SIZE=$(du -h "${BACKUP_DIR}/${DUMP_FILE}" | cut -f1)
echo "[$(date)] Dump created: ${DUMP_SIZE}"

# Push off-box. The remote key is restricted (rrsync, write-only, this
# directory only) -- see docs/RUNBOOK.md for how it was set up.
rsync -avz -e "ssh -i ${REMOTE_KEY} -o StrictHostKeyChecking=accept-new" \
  "${BACKUP_DIR}/${DUMP_FILE}" "${REMOTE_HOST}:"

echo "[$(date)] Pushed off-box to ${REMOTE_HOST}"

# Prune local copies older than retention window.
find "$BACKUP_DIR" -name "sunshineledger-*.dump" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date)] Backup complete."
