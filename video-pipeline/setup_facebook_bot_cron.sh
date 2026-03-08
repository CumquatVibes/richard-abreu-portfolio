#!/bin/bash
# ============================================================
# setup_facebook_bot_cron.sh
# One-time setup: installs the Facebook bot as a daily cron job
# running at 7 AM ET every day (after other pipeline jobs).
#
# Usage: bash setup_facebook_bot_cron.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT="$SCRIPT_DIR/facebook_bot.py"
LOG_DIR="$SCRIPT_DIR/output/logs"
LOG_FILE="$LOG_DIR/facebook_bot_cron.log"
PYTHON=$(which python3)

# Verify python3 exists
if [ -z "$PYTHON" ]; then
    echo "python3 not found. Install Python 3 first."
    exit 1
fi

# Verify the bot script exists
if [ ! -f "$BOT" ]; then
    echo "facebook_bot.py not found at $BOT"
    exit 1
fi

# Ensure output directory exists
mkdir -p "$LOG_DIR"

# Build the cron line — runs --all at 7 AM ET daily
CRON_CMD="0 7 * * * cd $SCRIPT_DIR && $PYTHON $BOT --all >> $LOG_FILE 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "facebook_bot.py"; then
    echo "Cron job already exists. Replacing..."
    (crontab -l 2>/dev/null | grep -v "facebook_bot.py"; echo "$CRON_CMD") | crontab -
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
fi

echo "Daily Facebook bot cron job installed!"
echo ""
echo "Schedule: Every day at 7:00 AM ET"
echo "Script:   $BOT --all"
echo "Log:      $LOG_FILE"
echo ""
echo "Verify with: crontab -l"
echo "Remove with: crontab -l | grep -v 'facebook_bot' | crontab -"
