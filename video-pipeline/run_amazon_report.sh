#!/bin/bash
# Weekly Amazon Associates Report — runs every Sunday at 9 AM EST
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/output/reports/amazon_report_log_$(date +%Y%m%d).txt"

mkdir -p "$SCRIPT_DIR/output/reports"

echo "=== Amazon Report Run: $(date) ===" >> "$LOG_FILE"
cd "$SCRIPT_DIR"
python3 amazon_weekly_report.py >> "$LOG_FILE" 2>&1
echo "=== Done: $(date) ===" >> "$LOG_FILE"
