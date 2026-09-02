#!/usr/bin/env bash
# Sunshine Ledger — scheduled-job heartbeat pings.
#
# Sourced by backup-db.sh and run-ingestion.sh. Both scripts already fail
# loudly and exit non-zero, but cron discards exit codes, so "loud" still
# means "silent" unless a human opens the log. Twice that gap turned into a
# real outage nobody noticed: a 0-byte backup on 2026-08-21, and four
# consecutive nights of failed ingestion on 2026-08-21..24.
#
# A push monitor closes it from both ends. The script pings on success, so
# a *missing* ping is itself an alert -- which catches the failure a
# log-based check can never see: the job not running at all, because cron
# stopped or the host is down.
#
# CONFIGURATION -- put the push URLs in monitoring.env beside this file:
#
#   BACKUP_PUSH_URL="https://uptime.example.com/api/push/aBcDeF"
#   INGESTION_PUSH_URL="https://uptime.example.com/api/push/GhIjKl"
#
# Until that file exists with a URL set, every ping is a silent no-op and
# the jobs behave exactly as they do today. Nothing here can turn a working
# backup into a failing one.

# Resolve monitoring.env relative to this file, so cron's working directory
# (which is $HOME, not the script directory) can't change what gets loaded.
_MONITORING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f "${_MONITORING_DIR}/monitoring.env" ] && . "${_MONITORING_DIR}/monitoring.env"

# monitor_ping <push_url> <up|down> <message> [duration_seconds]
#
# Deliberately cannot fail the caller. A monitoring outage must never turn
# a successful backup into a failed one, so every path returns 0 -- the
# curl is best-effort and its exit code is swallowed on purpose.
monitor_ping() {
    local url="${1:-}" status="${2:-up}" msg="${3:-}" duration="${4:-0}"

    # Unconfigured is the normal state before the monitors exist. Not an
    # error, and not worth a log line on every run.
    [ -z "$url" ] && return 0

    if ! command -v curl >/dev/null 2>&1; then
        echo "[$(date)] monitor: curl not found, skipping ping" >&2
        return 0
    fi

    # -G with --data-urlencode so a message containing spaces, ampersands
    # or a quoted committee name can't corrupt the query string.
    # --max-time bounds the whole attempt: a hung monitoring host must not
    # hold a nightly job open indefinitely.
    if curl -fsS -o /dev/null --max-time 10 --retry 2 --retry-delay 2 -G "$url" \
        --data-urlencode "status=${status}" \
        --data-urlencode "msg=${msg}" \
        --data-urlencode "ping=${duration}" 2>/dev/null; then
        return 0
    fi

    # Worth a log line: the job itself is fine, but its alerting is not, and
    # silent monitoring is how this project got bitten in the first place.
    echo "[$(date)] monitor: ping failed (status=${status}) -- job result unaffected" >&2
    return 0
}
