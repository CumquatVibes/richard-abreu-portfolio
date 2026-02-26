#!/bin/bash
# ============================================================
# setup_daily_cron.sh
# One-time setup: installs the daily YouTube channel analyzer
# as a cron job running at 6 AM ET every day.
#
# Usage: bash setup_daily_cron.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ANALYZER="$SCRIPT_DIR/daily_channel_analyzer.py"
LOG_DIR="$SCRIPT_DIR/output/daily_analysis"
LOG_FILE="$LOG_DIR/cron.log"
PYTHON=$(which python3)

# Verify python3 exists
if [ -z "$PYTHON" ]; then
    echo "❌ python3 not found. Install Python 3 first."
    exit 1
fi

# Verify the analyzer script exists
if [ ! -f "$ANALYZER" ]; then
    echo "❌ daily_channel_analyzer.py not found at $ANALYZER"
    exit 1
fi

# Ensure output directory exists
mkdir -p "$LOG_DIR"

# Build the cron line
CRON_CMD="0 6 * * * cd $SCRIPT_DIR && $PYTHON $ANALYZER >> $LOG_FILE 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "daily_channel_analyzer.py"; then
    echo "⚠️  Cron job already exists. Replacing..."
    # Remove old entry, add new one
    (crontab -l 2>/dev/null | grep -v "daily_channel_analyzer.py"; echo "$CRON_CMD") | crontab -
else
    # Append to existing crontab
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
fi

echo "✅ Daily YouTube analyzer cron job installed!"
echo ""
echo "Schedule: Every day at 6:00 AM ET"
echo "Script:   $ANALYZER"
echo "Log:      $LOG_FILE"
echo ""
echo "Verify with: crontab -l"
echo "Remove with: crontab -l | grep -v 'daily_channel_analyzer' | crontab -"
