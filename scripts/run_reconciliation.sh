#!/bin/bash
#
# Cron wrapper for reconcile_payments.py
#
# Runs reconciliation with --fix, logs output with a timestamp, and rotates
# logs so the log directory doesn't grow unbounded. Designed to be invoked
# by cron on a schedule (see crontab entry below) — not meant to be run
# directly by a human, though you can for testing.
#
# WHY A WRAPPER SCRIPT INSTEAD OF CALLING reconcile_payments.py FROM CRON
# DIRECTLY:
#   - Activates the correct venv (cron runs with a minimal environment,
#     it doesn't know about your shell's activated venv)
#   - Adds a timestamp header to each run's log output, since the Python
#     script itself doesn't timestamp its own lines
#   - Centralizes log file naming/rotation in one place
#   - Gives a single, stable entrypoint if the reconciliation logic itself
#     ever needs additional pre/post steps (e.g. sending a Slack alert on
#     failure) without touching the core script or the crontab entry
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python3"
RECONCILE_SCRIPT="${SCRIPT_DIR}/reconcile_payments.py"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/reconcile.log"
MAX_LOG_LINES=5000

mkdir -p "$LOG_DIR"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "── ${TIMESTAMP} ──────────────────────────────────────" >> "$LOG_FILE"

# Run reconciliation. Exit code is preserved so cron/monitoring can act on it:
#   0 = clean (no mismatches, or all mismatches fixed)
#   1 = mismatches found, --fix not passed (shouldn't happen here — we always pass --fix)
#   2 = mismatches found, --fix passed, but one or more fixes failed (needs human attention)
if "$VENV_PYTHON" "$RECONCILE_SCRIPT" --fix >> "$LOG_FILE" 2>&1; then
    EXIT_CODE=0
else
    EXIT_CODE=$?
fi

echo "Exit code: ${EXIT_CODE}" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Rotate: keep only the last MAX_LOG_LINES lines so the log file doesn't
# grow unbounded over months of cron runs. Simple tail-based rotation —
# fine for a low-volume safety-net job like this; a high-volume service
# would use logrotate instead.
if [ -f "$LOG_FILE" ]; then
    LINE_COUNT=$(wc -l < "$LOG_FILE")
    if [ "$LINE_COUNT" -gt "$MAX_LOG_LINES" ]; then
        tail -n "$MAX_LOG_LINES" "$LOG_FILE" > "${LOG_FILE}.tmp"
        mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
fi

# Exit code 2 means a fix failed — this is the case worth alerting on.
# A real production setup would send this to Slack/PagerDuty/etc. here.
if [ "$EXIT_CODE" -eq 2 ]; then
    echo "WARNING: reconciliation found a mismatch it could not fix. Check ${LOG_FILE}" >&2
fi

exit "$EXIT_CODE"
