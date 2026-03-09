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

# 0. Competitive audit (cached weekly, cheap)
echo "--- Competitive Audit ---" >> "$LOG_FILE"
python3 competitive_audit.py >> "$LOG_FILE" 2>&1

# 1. Retry failed video uploads (quota resets at midnight PT)
echo "--- Retrying video uploads ---" >> "$LOG_FILE"
python3 upload_to_youtube.py >> "$LOG_FILE" 2>&1

# 1b. Cross-post newly uploaded videos to Facebook Page
echo "--- Facebook Cross-Posts ---" >> "$LOG_FILE"
python3 -c "
import sys, json, os; sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv(os.path.join('..', 'shopify-theme', '.env'))
from utils.facebook import post_to_facebook_page
from utils.telemetry import get_facebook_posts

# Get videos uploaded today that haven't been posted to FB yet
report_path = 'output/reports/youtube_upload_report.json'
if os.path.exists(report_path):
    report = json.load(open(report_path))
    posted = {p['video_title'] for p in get_facebook_posts()}
    new_uploads = [v for v in report.get('videos', [])
                   if v.get('status') == 'uploaded' and v.get('title') not in posted]
    print(f'Found {len(new_uploads)} videos to cross-post to Facebook')
    for v in new_uploads[:5]:  # Cap at 5 per run to avoid spam
        url = f\"https://youtube.com/watch?v={v['video_id']}\"
        ok, result = post_to_facebook_page(v['title'], url, v.get('channel', 'CumquatVibes'))
        print(f'  {\"OK\" if ok else \"FAIL\"}: {v[\"title\"][:60]}')
else:
    print('No upload report found')
" >> "$LOG_FILE" 2>&1

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

# 6. Drift detection and alerting
echo "--- Drift Detection & Alerts ---" >> "$LOG_FILE"
python3 -c "
import sys; sys.path.insert(0, '.')
from utils.alerts import check_and_alert_drift, check_quota_status
print('Running drift detection...')
result = check_and_alert_drift()
print(f'Drift result: {result}')
print('Checking quota status...')
quota = check_quota_status()
print(f'Quota status: {quota}')
" >> "$LOG_FILE" 2>&1

# Summary report
echo "" >> "$LOG_FILE"
echo "=== NIGHTLY RUN SUMMARY ===" >> "$LOG_FILE"
python3 -c "
import json, os, glob
from datetime import date

# Count today's uploads
report = 'output/reports/youtube_upload_report.json'
if os.path.exists(report):
    data = json.load(open(report))
    total = data.get('uploaded', 0)
    pending = len(glob.glob('output/videos/*.mp4')) - total
    print(f'YouTube: {total} uploaded, ~{max(0,pending)} pending')

# Count scripts and broll
scripts = len(glob.glob('output/scripts/*.txt'))
broll = len(glob.glob('output/broll/*/'))
print(f'Content: {scripts} scripts, {broll} B-roll sets')

# Pipeline DB stats
db_path = 'output/pipeline.db'
if os.path.exists(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        fb = conn.execute('SELECT COUNT(*) FROM facebook_posts').fetchone()[0]
        print(f'Facebook: {fb} total posts')
    except: pass
    try:
        cb = conn.execute('SELECT COUNT(*) FROM competitor_briefs WHERE fetched_at > date(\"now\", \"-7 days\")').fetchone()[0]
        print(f'Competitive: {cb} fresh briefs (last 7d)')
    except: pass
    conn.close()
" >> "$LOG_FILE" 2>&1
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

# Check and execute retraining triggers
echo "" >> "$LOG_FILE"
echo "Checking retraining triggers..." >> "$LOG_FILE"
python3 -c "
from utils.alerts import check_retraining_triggers, execute_retraining
triggers = check_retraining_triggers()
if triggers:
    print(f'Found {len(triggers)} trigger(s)')
    actions = execute_retraining(triggers)
    for a in actions:
        print(f'  -> {a}')
else:
    print('No retraining triggers active')
" >> "$LOG_FILE" 2>&1


# 7. Facebook token health check
echo "--- Facebook Token Health ---" >> "$LOG_FILE"
cd "$SCRIPT_DIR" && python3 check_fb_tokens.py >> "$LOG_FILE" 2>&1