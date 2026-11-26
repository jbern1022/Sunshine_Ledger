#!/usr/bin/env bash
# Sunshine Ledger pilot-light standby: what the stopped-by-default AWS EC2
# instance does every time it starts. Runs as root from sunshine-standby.service.
#
# The mode comes from the instance tag `standby-mode` (read through instance
# metadata, so no AWS permission is needed for it):
#
#   refresh  (default)  Pull the code from the public GitHub mirror, rebuild the
#                       images, restore last night's dump as a test, check the
#                       API and site answer locally, then power off. NEVER joins
#                       the Cloudflare tunnel. Run weekly by the scheduler.
#   failover            Restore last night's dump, start the stack READ-ONLY and,
#                       only once it answers locally, start one cloudflared
#                       connector on the production tunnel. Stays up until the
#                       failover Lambda stops it (home is back), or 24 h at most.
#
# Design rule: NOTHING here may depend on the home network (Gitea, the Pi,
# Ollama, docker-host). Code comes from GitHub, secrets from SSM Parameter
# Store, data from the S3 backup bucket.
#
# Manual use (from an SSM Session Manager shell on the instance):
#   sudo shutdown -c                     cancel the 24 h failover auto-stop
#   sudo journalctl -u sunshine-standby  this script's log

set -Eeuo pipefail

REPO=/opt/sunshine-ledger
REGION=us-east-2
PARAM_PATH=/sunshine-ledger/prod/env/
BUCKET=sunshine-ledger-backups-269314582841
TOPIC_ARN=arn:aws:sns:us-east-2:269314582841:sunshine-ledger-uptime-alerts
PROJECT=sunshineledger
MAX_FAILOVER_MINUTES=1440
DUMP=/var/tmp/standby-restore.dump

START=$(date +%s)
log() { echo "[standby +$(( $(date +%s) - START ))s] $*"; }

imds_token() {
  curl -sf -X PUT http://169.254.169.254/latest/api/token \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 300'
}
# Instance tag value, or the default given when the tag is absent.
tag() {
  local v
  v=$(curl -sf -H "X-aws-ec2-metadata-token: $(imds_token)" \
    "http://169.254.169.254/latest/meta-data/tags/instance/$1" || true)
  echo "${v:-$2}"
}

notify() { # notify SUBJECT MESSAGE -- best effort, never fails the run
  aws sns publish --region "$REGION" --topic-arn "$TOPIC_ARN" \
    --subject "Sunshine standby: $1" --message "$2" >/dev/null 2>&1 \
    || log "notify failed: $1"
}

compose() {
  docker compose -p "$PROJECT" -f "$REPO/docker-compose.yml" \
    -f "$REPO/docker-compose.standby.yml" --env-file "$REPO/.env" "$@"
}

# Production settings from SSM -> $REPO/.env (mode 600, git-ignored). The
# standby overrides are appended last, so they win.
write_env() {
  umask 077
  aws ssm get-parameters-by-path --region "$REGION" --path "$PARAM_PATH" \
    --recursive --with-decryption --output json \
  | python3 -c '
import json, sys
for p in sorted(json.load(sys.stdin)["Parameters"], key=lambda p: p["Name"]):
    print(p["Name"].rsplit("/", 1)[1] + "=" + p["Value"])
' > "$REPO/.env.new"
  local n; n=$(grep -c '=' "$REPO/.env.new" || true)
  [[ "$n" -ge 10 ]] || { log "only $n settings came back from SSM"; return 1; }
  printf 'READ_ONLY=true\nNEXT_PUBLIC_READ_ONLY=true\nBIND_ADDRESS=127.0.0.1\n' >> "$REPO/.env.new"
  mv "$REPO/.env.new" "$REPO/.env"
  log "wrote $n settings from SSM"
}

envval() { sed -nE "s/^$1=(.*)$/\1/p" "$REPO/.env" | tail -1; }

fetch_dump() {
  local key
  key=$(aws s3api list-objects-v2 --region "$REGION" --bucket "$BUCKET" --prefix backups/ \
    --query 'sort_by(Contents[?ends_with(Key, `.dump`)], &LastModified)[-1].Key' --output text)
  [[ -n "$key" && "$key" != "None" ]] || { log "no dump found in s3://$BUCKET/backups/"; return 1; }
  aws s3 cp --region "$REGION" --only-show-errors "s3://$BUCKET/$key" "$DUMP"
  DUMP_KEY=$key
  log "downloaded $key ($(du -h "$DUMP" | cut -f1))"
}

# Fresh database volume every time, then pg_restore. A fresh postgis/postgis
# volume already has the tiger/tiger_data/topology schemas, so pg_restore
# reports exactly those three "already exists" errors (docs/RUNBOOK.md,
# "Restoring"); anything else is reported but does not stop a failover.
restore_db() {
  local user db
  user=$(envval POSTGRES_USER); db=$(envval POSTGRES_DB)
  user=${user:-sunshine}; db=${db:-sunshine_ledger}
  compose stop backend frontend >/dev/null 2>&1 || true
  compose rm -sf db >/dev/null 2>&1 || true
  docker volume rm -f "${PROJECT}_db_data" >/dev/null
  compose up -d db
  for _ in $(seq 1 60); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q db)")" == healthy ]] && break
    sleep 5
  done
  docker cp "$DUMP" "$(compose ps -q db)":/tmp/restore.dump
  compose exec -T db pg_restore -U "$user" -d "$db" --no-owner --jobs 2 /tmp/restore.dump \
    2> /var/tmp/pg_restore.err || true
  compose exec -T db rm -f /tmp/restore.dump
  RESTORE_ERRORS=$(grep -c 'error:' /var/tmp/pg_restore.err || true)
  UNEXPECTED_ERRORS=$(grep 'error:' /var/tmp/pg_restore.err | grep -vc 'already exists' || true)
  BILLS=$(compose exec -T db psql -U "$user" -d "$db" -tAc 'select count(*) from entities' | tr -d '[:space:]')
  CLAIMS=$(compose exec -T db psql -U "$user" -d "$db" -tAc 'select count(*) from claims' | tr -d '[:space:]')
  log "restore: ${BILLS} entities, ${CLAIMS} claims, ${RESTORE_ERRORS} pg_restore errors (${UNEXPECTED_ERRORS} unexpected)"
  [[ "${BILLS:-0}" -gt 0 ]] || { log "restore produced no entities"; return 1; }
}

wait_http() { # wait_http URL MINUTES
  local deadline=$(( $(date +%s) + $2 * 60 ))
  until curl -sf -o /dev/null --max-time 10 "$1"; do
    (( $(date +%s) < deadline )) || { log "timed out waiting for $1"; return 1; }
    sleep 10
  done
  log "up: $1"
}

start_app() {
  # Frontend runs `npm run build` at container start (NEXT_PUBLIC_* baked in),
  # which takes several minutes on this instance.
  local api_port fe_port
  api_port=$(envval API_PORT); fe_port=$(envval FRONTEND_PORT)
  compose up -d --no-deps backend frontend
  wait_http "http://127.0.0.1:${api_port:-8010}/health" 10
  wait_http "http://127.0.0.1:${fe_port:-3010}/" 20
}

summary() {
  echo "Mode: $MODE. Took $(( ($(date +%s) - START) / 60 )) min."
  echo "Code: $(git -C "$REPO" log -1 --format='%h %s' 2>/dev/null || echo unknown)"
  echo "Data: ${DUMP_KEY:-none}; ${BILLS:-?} entities, ${CLAIMS:-?} claims; pg_restore errors ${RESTORE_ERRORS:-?} (unexpected ${UNEXPECTED_ERRORS:-?})."
}

refresh() {
  local ref; ref=$(tag standby-git-ref main)
  git -C "$REPO" fetch --quiet origin "$ref"
  git -C "$REPO" reset --quiet --hard FETCH_HEAD
  log "code at $(git -C "$REPO" log -1 --format='%h %s') ($ref)"
  # The checkout may carry a newer version of this script and its unit.
  install -m 0644 "$REPO/scripts/standby/sunshine-standby.service" /etc/systemd/system/
  systemctl daemon-reload
  write_env
  compose pull --quiet db
  docker pull --quiet cloudflare/cloudflared:latest >/dev/null
  compose build --quiet backend frontend
  log "images built"
  fetch_dump
  restore_db
  start_app
  compose stop backend frontend
  docker image prune -f >/dev/null
  rm -f "$DUMP"
}

failover() {
  shutdown -h "+$MAX_FAILOVER_MINUTES" "Sunshine standby: ${MAX_FAILOVER_MINUTES}-minute failover limit" || true
  notify "failover starting" "Home origin reported down; the standby is restoring last night's backup. Auto-stop in ${MAX_FAILOVER_MINUTES} min unless cancelled (sudo shutdown -c)."
  write_env
  fetch_dump
  restore_db
  start_app
  # Health-gated: join the tunnel only once both apps answer locally. One
  # connector, never cloudflared2, and --no-deps so nothing else is recreated.
  compose --profile tunnel up -d --no-deps cloudflared
  log "joined the Cloudflare tunnel"
  notify "serving (read-only)" "$(summary)"
}

on_error() {
  local code=$?
  log "FAILED (exit $code)"
  notify "$MODE FAILED" "$(summary)
Exit $code. Log: journalctl -u sunshine-standby (connect with SSM Session Manager)."
  # A failed refresh powers off (nothing to serve). A failed failover stays up
  # so it can be inspected; the 24 h auto-stop still applies.
  [[ "$MODE" == refresh ]] && shutdown -h now
  exit "$code"
}

# First, before anything else: no tunnel connector may survive a reboot. The
# standby override sets restart: "no" on cloudflared; this is the backstop.
docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "label=com.docker.compose.service=cloudflared" \
  | xargs -r docker rm -f >/dev/null
docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "label=com.docker.compose.service=cloudflared2" \
  | xargs -r docker rm -f >/dev/null

MODE=$(tag standby-mode refresh)
log "mode: $MODE"
trap on_error ERR

case "$MODE" in
  failover) failover ;;
  refresh)
    refresh
    # The alarm may have fired while the refresh ran: the failover Lambda
    # then retags the instance instead of starting it. Serve instead of
    # powering off.
    if [[ "$(tag standby-mode refresh)" == failover ]]; then
      MODE=failover
      log "switched to failover during refresh"
      failover
    else
      notify "weekly refresh OK" "$(summary)"
      log "refresh complete; powering off"
      shutdown -h now
    fi
    ;;
  *) log "unknown standby-mode '$MODE'; doing nothing"; exit 1 ;;
esac
