#!/bin/bash
# One-shot channel optimization — runs after YouTube quota reset
# Scheduled to run at 3:30 AM EST (12:30 AM PT)
# Auto-removes itself from crontab after running

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/output/channel_optimization_log_$(date +%Y%m%d).txt"

echo "=== Channel Optimization Run: $(date) ===" >> "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 optimize_all_channels.py update >> "$LOG_FILE" 2>&1
echo "=== Done: $(date) ===" >> "$LOG_FILE"

# Remove this cron job after running
crontab -l 2>/dev/null | grep -v "run_channel_optimization.sh" | crontab -
