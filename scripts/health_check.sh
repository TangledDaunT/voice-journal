#!/bin/bash
# Health check script for monitoring

set -e

cd "$(dirname "$0")/.."

if [ ! -d "venv" ]; then
    echo "CRITICAL: venv not found"
    exit 2
fi

source venv/bin/activate

# Check status
OUTPUT=$(python status.py --format json)

# Parse JSON
BACKLOG_HOURS=$(echo "$OUTPUT" | python -c "import sys, json; print(json.load(sys.stdin)['backlog']['total_hours'])" 2>/dev/null || echo "0")
SCHEDULER_RUNNING=$(echo "$OUTPUT" | python -c "import sys, json; print(json.load(sys.stdin)['scheduler_running'])" 2>/dev/null || echo "False")

# Check thresholds
if (( $(echo "$BACKLOG_HOURS > 48.0" | bc -l) )); then
    echo "CRITICAL: Backlog > 48 hours: $BACKLOG_HOURS"
    exit 2
elif (( $(echo "$BACKLOG_HOURS > 24.0" | bc -l) )); then
    echo "WARNING: Backlog > 24 hours: $BACKLOG_HOURS"
    exit 1
elif [ "$SCHEDULER_RUNNING" != "True" ]; then
    echo "WARNING: Scheduler not running"
    exit 1
else
    echo "OK: Backlog ${BACKLOG_HOURS}h, scheduler running"
    exit 0
fi
