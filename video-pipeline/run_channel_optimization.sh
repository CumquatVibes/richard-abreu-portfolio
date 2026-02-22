#!/bin/bash
# Nightly pipeline — runs after YouTube quota reset
# Scheduled: 3:30 AM EST (12:30 AM PT) — 30 min after quota resets
#
# Tasks (in order):
# 1. Retry failed/quota-blocked video uploads
# 2. Backfill custom thumbnails for uploaded videos
# 3. Upload new assets to Google Drive
# 4. Pull YouTube Analytics metrics for published videos
# 5. Run channel optimization (if not all done)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/output/nightly_pipeline_log_$(date +%Y%m%d).txt"
PROGRESS_FILE="$SCRIPT_DIR/output/channel_optimization_progress.json"

echo "=== Nightly Pipeline Run: $(date) ===" >> "$LOG_FILE"
cd "$SCRIPT_DIR"

# 1. Retry failed video uploads (quota resets at midnight PT)
echo "--- Retrying video uploads ---" >> "$LOG_FILE"
python3 upload_to_youtube.py >> "$LOG_FILE" 2>&1

# 2. Backfill thumbnails for any uploaded videos missing custom thumbnails
echo "--- Backfilling thumbnails ---" >> "$LOG_FILE"
python3 backfill_thumbnails.py >> "$LOG_FILE" 2>&1

# 3. Sync to Google Drive (videos, audio, thumbnails)
echo "--- Syncing to Google Drive ---" >> "$LOG_FILE"
python3 upload_videos_to_drive.py >> "$LOG_FILE" 2>&1

# 4. Pull YouTube Analytics for feedback loop
echo "--- Pulling YouTube Analytics ---" >> "$LOG_FILE"
python3 -c "
import sys; sys.path.insert(0, '.')
from utils.analytics import pull_all_published_metrics
print('Pulling 7-day metrics...')
pull_all_published_metrics('7d')
print('Pulling 28-day metrics...')
pull_all_published_metrics('28d')
print('Analytics pull complete.')
" >> "$LOG_FILE" 2>&1

# 5. Channel optimization
echo "--- Channel Optimization ---" >> "$LOG_FILE"
python3 optimize_all_channels.py update >> "$LOG_FILE" 2>&1

echo "=== Nightly Pipeline Done: $(date) ===" >> "$LOG_FILE"

# Check if all channels are optimized
if [ -f "$PROGRESS_FILE" ]; then
    UPDATED_COUNT=$(python3 -c "import json; d=json.load(open('$PROGRESS_FILE')); print(len(d.get('updated',[])))" 2>/dev/null)
    if [ "$UPDATED_COUNT" -ge 38 ] 2>/dev/null; then
        echo "All 38 channels optimized." >> "$LOG_FILE"
    else
        echo "Optimization progress: $UPDATED_COUNT/38 channels." >> "$LOG_FILE"
    fi
fi
