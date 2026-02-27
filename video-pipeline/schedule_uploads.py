#!/usr/bin/env python3
"""
schedule_uploads.py - Schedule video uploads across the week.

Respects YouTube quota (6 uploads/day max), channel posting frequency
from channels_config.json, and optimal posting times.

Usage:
    python schedule_uploads.py                     # Show schedule for pending videos
    python schedule_uploads.py --channel rich_education  # Schedule one channel
    python schedule_uploads.py --apply             # Write schedule to upload queue
    python schedule_uploads.py --dry-run           # Preview without writing
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VIDEOS_DIR = BASE_DIR / "output" / "videos"
REPORT_DIR = BASE_DIR / "output" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_REPORT_PATH = REPORT_DIR / "youtube_upload_report.json"
SCHEDULE_PATH = REPORT_DIR / "upload_schedule.json"
CHANNELS_CONFIG_PATH = BASE_DIR / "channels_config.json"

# Quota constraints
MAX_UPLOADS_PER_DAY = 5  # Conservative: 5 × 1600 = 8000 of 10,000 quota

# Optimal posting times (UTC) — education content performs best in morning/evening
OPTIMAL_HOURS_UTC = [14, 17, 20]  # 9AM, 12PM, 3PM EST


def load_channels_config():
    with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_posting_frequency(channel_config):
    """Parse posting frequency from channel config.

    Returns (long_form_per_week, shorts_per_week)
    """
    posting = channel_config.get("posting", {})
    lf = posting.get("long_form", "")
    shorts = posting.get("shorts", "")

    lf_per_week = 0
    if "3x" in lf:
        lf_per_week = 3
    elif "2x" in lf:
        lf_per_week = 2
    elif "1x" in lf:
        lf_per_week = 1

    shorts_per_week = 0
    if "daily" in shorts or "7x" in shorts:
        shorts_per_week = 7
    elif "3x/day" in shorts:
        shorts_per_week = 21
    elif "3x" in shorts:
        shorts_per_week = 3

    return lf_per_week, shorts_per_week


def get_pending_videos(channel_filter=None):
    """Get videos that haven't been uploaded yet."""
    already_uploaded = set()
    if UPLOAD_REPORT_PATH.exists():
        with open(UPLOAD_REPORT_PATH) as f:
            report = json.load(f)
            for r in report.get("results", []):
                if r.get("status") == "success":
                    already_uploaded.add(r["file"])

    pending = []
    for channel_dir in VIDEOS_DIR.iterdir():
        if not channel_dir.is_dir():
            continue
        for video_file in sorted(channel_dir.glob("*.mp4")):
            # Also check top-level videos dir
            if video_file.name in already_uploaded:
                continue
            channel = video_file.name.split("_")[0]
            if channel_filter and channel.lower() != channel_filter.lower():
                continue
            pending.append({
                "file": video_file.name,
                "path": str(video_file),
                "channel": channel,
                "size_mb": video_file.stat().st_size / (1024 * 1024),
            })

    # Also check top-level videos dir
    for video_file in sorted(VIDEOS_DIR.glob("*.mp4")):
        if video_file.name in already_uploaded:
            continue
        channel = video_file.name.split("_")[0]
        if channel_filter and channel.lower() != channel_filter.lower():
            continue
        pending.append({
            "file": video_file.name,
            "path": str(video_file),
            "channel": channel,
            "size_mb": video_file.stat().st_size / (1024 * 1024),
        })

    return pending


def generate_schedule(pending_videos, start_date=None):
    """Generate an upload schedule respecting frequency and quota limits.

    Returns list of {video, publish_at, day_index}
    """
    if not pending_videos:
        return []

    config = load_channels_config()
    channels = config.get("channels", {})

    # Group videos by channel
    by_channel = {}
    for v in pending_videos:
        ch = v["channel"]
        by_channel.setdefault(ch, []).append(v)

    if start_date is None:
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        # Start tomorrow to give time for sync
        start_date += timedelta(days=1)

    schedule = []
    day_counts = {}  # day_index -> upload count

    for channel_name, videos in by_channel.items():
        # Find channel config
        channel_key = None
        for key, ch_config in channels.items():
            if ch_config.get("name") == channel_name:
                channel_key = key
                break

        if channel_key:
            lf_per_week, _ = get_posting_frequency(channels[channel_key])
        else:
            lf_per_week = 2  # Default

        if lf_per_week == 0:
            lf_per_week = 2

        # Calculate days between posts
        days_between = 7 // lf_per_week  # e.g., 2x/week = every 3.5 days

        # Schedule each video
        for idx, video in enumerate(videos):
            # Target day offset from start
            day_offset = idx * days_between
            target_date = start_date + timedelta(days=day_offset)

            # Find a day that isn't over quota
            for attempt in range(7):
                check_date = target_date + timedelta(days=attempt)
                day_key = check_date.strftime("%Y-%m-%d")
                current_count = day_counts.get(day_key, 0)
                if current_count < MAX_UPLOADS_PER_DAY:
                    # Pick optimal hour
                    hour_idx = current_count % len(OPTIMAL_HOURS_UTC)
                    publish_time = check_date.replace(hour=OPTIMAL_HOURS_UTC[hour_idx])
                    publish_at = publish_time.strftime("%Y-%m-%dT%H:%M:%SZ")

                    schedule.append({
                        "file": video["file"],
                        "path": video["path"],
                        "channel": channel_name,
                        "size_mb": video["size_mb"],
                        "publish_at": publish_at,
                        "day": day_key,
                    })
                    day_counts[day_key] = current_count + 1
                    break

    # Sort by publish_at
    schedule.sort(key=lambda x: x["publish_at"])
    return schedule


def print_schedule(schedule):
    """Pretty-print the upload schedule."""
    if not schedule:
        print("No videos to schedule.")
        return

    print(f"\n{'=' * 70}")
    print(f"  UPLOAD SCHEDULE — {len(schedule)} videos")
    print(f"{'=' * 70}")

    current_day = None
    for entry in schedule:
        day = entry["day"]
        if day != current_day:
            current_day = day
            day_count = sum(1 for e in schedule if e["day"] == day)
            print(f"\n  {day} ({day_count} upload{'s' if day_count > 1 else ''}):")

        publish_time = entry["publish_at"].split("T")[1].replace("Z", "")
        print(f"    {publish_time} UTC | {entry['channel']:20s} | {entry['file'][:50]} ({entry['size_mb']:.0f} MB)")

    # Summary
    days_span = len(set(e["day"] for e in schedule))
    total_mb = sum(e["size_mb"] for e in schedule)
    print(f"\n  Span: {days_span} days | Total: {total_mb:.0f} MB")
    print(f"{'=' * 70}")


def save_schedule(schedule):
    """Save schedule to JSON for the upload script to consume."""
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_videos": len(schedule),
            "schedule": schedule,
        }, f, indent=2)
    print(f"\n  Schedule saved to: {SCHEDULE_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Schedule video uploads")
    parser.add_argument("--channel", help="Filter to a specific channel prefix")
    parser.add_argument("--apply", action="store_true", help="Save schedule to file")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD), default: tomorrow")
    args = parser.parse_args()

    start_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")

    pending = get_pending_videos(channel_filter=args.channel)
    print(f"Pending videos: {len(pending)}")

    if not pending:
        print("No pending videos to schedule.")
        return

    schedule = generate_schedule(pending, start_date=start_date)
    print_schedule(schedule)

    if args.apply and not args.dry_run:
        save_schedule(schedule)
    elif not args.dry_run:
        print("\n  Use --apply to save this schedule.")


if __name__ == "__main__":
    main()
