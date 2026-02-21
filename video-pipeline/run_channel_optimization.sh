#!/bin/bash
# Nightly channel optimization — runs after YouTube quota reset
# Scheduled: 3:30 AM EST (12:30 AM PT) — 30 min after quota resets
# Repeats every night until all channels are optimized, then self-removes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/output/channel_optimization_log_$(date +%Y%m%d).txt"
PROGRESS_FILE="$SCRIPT_DIR/output/channel_optimization_progress.json"

echo "=== Channel Optimization Run: $(date) ===" >> "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 optimize_all_channels.py update >> "$LOG_FILE" 2>&1
echo "=== Done: $(date) ===" >> "$LOG_FILE"

# Check if all channels are done (38 total)
# If progress file shows all updated, remove the cron job
if [ -f "$PROGRESS_FILE" ]; then
    UPDATED_COUNT=$(python3 -c "import json; d=json.load(open('$PROGRESS_FILE')); print(len(d.get('updated',[])))" 2>/dev/null)
    if [ "$UPDATED_COUNT" -ge 38 ] 2>/dev/null; then
        echo "All 38 channels optimized! Removing nightly cron job." >> "$LOG_FILE"
        crontab -l 2>/dev/null | grep -v "run_channel_optimization.sh" | crontab -
    else
        echo "Progress: $UPDATED_COUNT/38 channels done. Will run again tomorrow." >> "$LOG_FILE"
    fi
fi
