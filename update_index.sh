#!/bin/bash
# Incremental command-KB update. Same delta-date contract as ceph-issue-kb:
#   ./update_index.sh              # since yesterday of last success (1-day overlap), or last 1 day if first run
#   ./update_index.sh 7            # last 7 days
#   ./update_index.sh 2026-08-01   # since a specific ISO date
#   ./update_index.sh --reset      # clear the last-run tracker
# Invalid arg (not YYYY-MM-DD and not a day count) → exit 2.
#
# Command help has no date filter. This script records the delta window
# and re-runs live `--help` discovery. Must be run on a node with Ceph
# binaries on PATH (typically a cluster admin node).
#
# After a successful rebuild, touches .reload_trigger so a running MCP
# hot-reloads knowledge/ without restarting Cursor.

set -euo pipefail
cd "$(dirname "$0")"

LAST_RUN_FILE=".last_index_update"

if [[ "${1:-}" == "--reset" ]]; then
    rm -f "$LAST_RUN_FILE"
    echo "Last-run tracker reset. Next run will use last 1 day."
    exit 0
fi

if [[ -n "${1:-}" ]]; then
    ARG="$1"
    if [[ "$ARG" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        if ! date -j -f "%Y-%m-%d" "$ARG" +%Y-%m-%d >/dev/null 2>&1 \
           && ! date -d "$ARG" +%Y-%m-%d >/dev/null 2>&1; then
            echo "error: invalid date '$ARG' (expected YYYY-MM-DD or integer day count)" >&2
            exit 2
        fi
        SINCE="$ARG"
    elif [[ "$ARG" =~ ^[0-9]+$ ]]; then
        SINCE=$(date -v-"${ARG}"d +%Y-%m-%d 2>/dev/null || date -d "${ARG} days ago" +%Y-%m-%d)
    else
        echo "error: invalid date '$ARG' (expected YYYY-MM-DD or integer day count)" >&2
        exit 2
    fi
elif [[ -f "$LAST_RUN_FILE" ]]; then
    SINCE=$(cat "$LAST_RUN_FILE")
    echo "(Last successful run: $SINCE)"
else
    SINCE=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "1 day ago" +%Y-%m-%d)
    echo "(First run — using last 1 day as the recorded window)"
fi

if ! command -v ceph >/dev/null 2>&1; then
    echo "error: 'ceph' is not on PATH." >&2
    echo "error: generate_reference.py must run on a node with Ceph binaries." >&2
    echo "error: after capture, copy knowledge/<version>/ back to this repo," >&2
    echo "error: then: touch .reload_trigger   # running MCP hot-reloads in ~5s" >&2
    exit 1
fi

echo "=== Ceph Command KB Update ==="
echo "Delta since: $SINCE (full rediscovery; date is recorded in metadata)"
echo ""

python3 generate_reference.py --since "$SINCE" --verbose --force

touch .reload_trigger

date -v-1d +%Y-%m-%d > "$LAST_RUN_FILE" 2>/dev/null || date -d "1 day ago" +%Y-%m-%d > "$LAST_RUN_FILE"

echo ""
echo "=== Command index updated since $SINCE ==="
echo "Touched .reload_trigger — running MCP hot-reloads within ~5s (no Cursor restart)."
