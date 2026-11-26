#!/usr/bin/env bash
# Sunshine Ledger -- keep a local .env in step with the production deploy.env.
#
# The server copy (docker:~/sunshine-ledger/deploy.env) is the SOURCE OF TRUTH.
# Keys get added there (Cognito, AWS, CONGRESS_API_KEY ...) and a stale local
# file pushed over it would silently delete them. So:
#
#   scripts/sync-env.sh [pull] [TARGET]   copy the server file to TARGET (default ./.env),
#                                         mode 600, backing up an existing TARGET first
#   scripts/sync-env.sh diff [TARGET]     key NAMES that differ (added / removed / changed)
#   scripts/sync-env.sh push [SOURCE] --yes
#                                         replace the server file with SOURCE (default ./.env),
#                                         only if SOURCE has every key the server has; the
#                                         server copy is backed up to deploy.env.bak-<timestamp>
#   scripts/sync-env.sh ssm-diff          key NAMES where AWS SSM Parameter Store
#                                         (/sunshine-ledger/prod/env/*) differs from the server
#   scripts/sync-env.sh ssm-push --yes    copy the server's added/changed keys into SSM
#                                         (SecureString). Run it after every deploy.env change:
#                                         the AWS pilot-light standby reads only SSM
#                                         (scripts/standby/). Keys only in SSM are reported,
#                                         never deleted.
#
# Values are never printed, only key names.
#
# Overridable for testing: SYNC_ENV_REMOTE (default "docker"), SYNC_ENV_REMOTE_PATH
# (default "sunshine-ledger/deploy.env", relative to the remote home), SSH, SCP.

set -euo pipefail

REMOTE="${SYNC_ENV_REMOTE:-docker}"
REMOTE_PATH="${SYNC_ENV_REMOTE_PATH:-sunshine-ledger/deploy.env}"
SSH="${SSH:-ssh}"
SCP="${SCP:-scp}"
AWS="${AWS:-aws}"
SSM_PATH="${SYNC_ENV_SSM_PATH:-/sunshine-ledger/prod/env/}"
export AWS_PROFILE="${AWS_PROFILE:-sunshine-ledger}" AWS_REGION="${AWS_REGION:-us-east-2}" AWS_PAGER=""

die() { echo "sync-env: $*" >&2; exit 1; }

# sha256 of stdin: shasum on macOS, sha256sum on Linux.
sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256; else sha256sum; fi | cut -d' ' -f1; }

# Key names in a dotenv file: KEY=... or export KEY=..., comments and blanks ignored.
keys() {
    sed -nE 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' "$1" | sort -u
}

# Print "KEY<TAB>sha256(value)" so values can be compared without being shown.
hashed() {
    local k v
    while IFS= read -r k; do
        v=$(sed -nE "s/^[[:space:]]*(export[[:space:]]+)?${k}=(.*)$/\\2/p" "$1" | tail -1)
        printf '%s\t%s\n' "$k" "$(printf '%s' "$v" | sha)"
    done < <(keys "$1")
}

# Report names: what B has that A lacks, what A has that B lacks, and changed values.
report() { # report OLD NEW
    local old="$1" new="$2" added removed changed
    added=$(comm -13 <(keys "$old") <(keys "$new"))
    removed=$(comm -23 <(keys "$old") <(keys "$new"))
    changed=$(join -t $'\t' <(hashed "$old") <(hashed "$new") | awk -F'\t' '$2 != $3 {print $1}')
    echo "  added:   ${added:-none}" | paste -sd' ' -
    echo "  removed: ${removed:-none}" | paste -sd' ' -
    echo "  changed: ${changed:-none}" | paste -sd' ' -
}

# "KEY<TAB>sha256(value)" for every parameter under $SSM_PATH (values never shown).
ssm_hashed() {
    "$AWS" ssm get-parameters-by-path --path "$SSM_PATH" --recursive --with-decryption --output json \
      | python3 -c '
import hashlib, json, sys
for p in json.load(sys.stdin)["Parameters"]:
    print(p["Name"].rsplit("/", 1)[1] + "\t" + hashlib.sha256(p["Value"].encode()).hexdigest())
' | sort
}

# Names of keys whose value on the server differs from SSM or is missing there.
ssm_stale() { # ssm_stale SERVER_HASHED SSM_HASHED
    join -t $'\t' -a 1 "$1" "$2" | awk -F'\t' '$2 != $3 {print $1}'
}

fetch_server() { # fetch_server DEST
    "$SCP" -q "${REMOTE}:${REMOTE_PATH}" "$1" || die "could not copy ${REMOTE}:${REMOTE_PATH}"
}

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
chmod 600 "$TMP"

cmd="${1:-pull}"
case "$cmd" in
    pull)
        target="${2:-./.env}"
        fetch_server "$TMP"
        if [ -e "$target" ]; then
            echo "Changes to ${target} (server is the source of truth):"
            report "$target" "$TMP"
            bak="${target}.bak-$(date +%Y%m%d-%H%M%S)"
            cp -p "$target" "$bak"
            chmod 600 "$bak"
            echo "Previous ${target} kept as ${bak}"
        fi
        install -m 600 "$TMP" "$target"
        echo "Pulled ${REMOTE}:${REMOTE_PATH} -> ${target} ($(keys "$target" | wc -l | tr -d ' ') keys, mode 600)"
        ;;
    diff)
        target="${2:-./.env}"
        [ -e "$target" ] || die "${target} does not exist"
        fetch_server "$TMP"
        echo "Differences from the server to ${target} (names only):"
        report "$TMP" "$target"
        ;;
    push)
        shift
        source_file="./.env" yes=0
        for a in "$@"; do
            case "$a" in
                --yes) yes=1 ;;
                *) source_file="$a" ;;
            esac
        done
        [ -e "$source_file" ] || die "${source_file} does not exist"
        fetch_server "$TMP"
        missing=$(comm -23 <(keys "$TMP") <(keys "$source_file"))
        if [ -n "$missing" ]; then
            echo "Refusing to push: ${source_file} lacks keys the server has, and pushing would delete them:" >&2
            printf '  %s\n' $missing >&2
            echo "Run 'scripts/sync-env.sh pull' first, then make your change." >&2
            exit 1
        fi
        echo "Push ${source_file} -> ${REMOTE}:${REMOTE_PATH}:"
        report "$TMP" "$source_file"
        [ "$yes" -eq 1 ] || die "not pushed: re-run with --yes to replace the server file"
        stamp=$(date +%Y%m%d-%H%M%S)
        "$SSH" "$REMOTE" "cp -p '${REMOTE_PATH}' '${REMOTE_PATH}.bak-${stamp}' && chmod 600 '${REMOTE_PATH}.bak-${stamp}'" \
            || die "could not back up the server file; nothing pushed"
        "$SCP" -q "$source_file" "${REMOTE}:${REMOTE_PATH}" || die "copy failed; server backup is ${REMOTE_PATH}.bak-${stamp}"
        "$SSH" "$REMOTE" "chmod 600 '${REMOTE_PATH}'"
        echo "Pushed. Server backup: ${REMOTE}:${REMOTE_PATH}.bak-${stamp}. Recreate the backend for it to take effect."
        ;;
    ssm-diff|ssm-push)
        fetch_server "$TMP"
        hashed "$TMP" | sort > "$TMP.server"; ssm_hashed > "$TMP.ssm"
        trap 'rm -f "$TMP" "$TMP.server" "$TMP.ssm" "$TMP.val"' EXIT
        stale=$(ssm_stale "$TMP.server" "$TMP.ssm")
        extra=$(comm -13 <(cut -f1 "$TMP.server") <(cut -f1 "$TMP.ssm"))
        echo "SSM ${SSM_PATH} vs ${REMOTE}:${REMOTE_PATH} (names only):"
        echo "  missing or changed in SSM: ${stale:-none}" | paste -sd' ' -
        echo "  only in SSM (left alone):  ${extra:-none}" | paste -sd' ' -
        [ "$cmd" = ssm-push ] || exit 0
        [ -n "$stale" ] || { echo "SSM is up to date."; exit 0; }
        [ "${2:-}" = --yes ] || die "not pushed: re-run with --yes to write these keys to SSM"
        for k in $stale; do
            ( umask 077; sed -nE "s/^[[:space:]]*(export[[:space:]]+)?${k}=(.*)$/\\2/p" "$TMP" | tail -1 | tr -d '\n' > "$TMP.val" )
            "$AWS" ssm put-parameter --name "${SSM_PATH}${k}" --type SecureString --tier Standard \
                --overwrite --value "file://$TMP.val" >/dev/null || die "could not write ${k}"
            echo "  wrote ${k}"
        done
        ;;
    -h|--help|help)
        sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    *) die "unknown command '${cmd}' (pull | diff | push | ssm-diff | ssm-push)" ;;
esac
