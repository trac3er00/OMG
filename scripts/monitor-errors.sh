#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${1:-.sisyphus/logs}"
PATTERN="${2:-ERROR}"
TAIL_LINES="${3:-100}"

if [ ! -d "$LOG_DIR" ]; then
  echo "Log directory not found: $LOG_DIR"
  exit 1
fi

echo "=== Error Monitor ==="
echo "Scanning: $LOG_DIR"
echo "Pattern:  $PATTERN"
echo "---"

error_count=0
for logfile in "$LOG_DIR"/*.log; do
  [ -f "$logfile" ] || continue
  matches=$(tail -n "$TAIL_LINES" "$logfile" | grep -c "$PATTERN" 2>/dev/null || true)
  if [ "$matches" -gt 0 ]; then
    echo "[$logfile] $matches occurrence(s):"
    tail -n "$TAIL_LINES" "$logfile" | grep "$PATTERN" | head -5
    echo "---"
    error_count=$((error_count + matches))
  fi
done

echo "Total errors found: $error_count"

if [ "$error_count" -gt 10 ]; then
  echo "WARNING: High error rate detected"
  exit 2
fi

exit 0
