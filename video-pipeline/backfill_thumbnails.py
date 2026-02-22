#!/usr/bin/env python3
"""Backfill custom thumbnails for already-uploaded YouTube videos.

Generates thumbnails via Gemini and uploads them via YouTube thumbnails.set API.
Only processes videos that were successfully uploaded but don't have custom thumbnails yet.

Usage:
    python backfill_thumbnails.py           # Generate + upload thumbnails
    python backfill_thumbnails.py --generate-only  # Only generate, don't upload
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from upload_to_youtube import (
    generate_thumbnail,
    upload_thumbnail,
    load_channel_tokens,
    refresh_default_token,
    get_token_for_channel,
    make_title,
    UPLOAD_REPORT_PATH,
    THUMBNAILS_DIR,
)

# Reload channel tokens at module level
channel_access_tokens = {}


def main():
    global channel_access_tokens

    generate_only = "--generate-only" in sys.argv

    print("Thumbnail Backfill for Uploaded Videos")
    print("=" * 60)

    # Load upload report
    if not os.path.exists(UPLOAD_REPORT_PATH):
        print("No upload report found. Run upload_to_youtube.py first.")
        return

    with open(UPLOAD_REPORT_PATH) as f:
        report = json.load(f)

    # Find successfully uploaded videos
    uploaded = [r for r in report.get("results", []) if r.get("status") == "success" and r.get("video_id")]
    print(f"Found {len(uploaded)} successfully uploaded videos\n")

    if not uploaded:
        print("No uploaded videos to process.")
        return

    # Load tokens
    if not generate_only:
        print("Loading channel tokens...")
        channel_access_tokens = load_channel_tokens()
        default_token = refresh_default_token()
        print(f"  {len(channel_access_tokens)} channel tokens loaded\n")
    else:
        default_token = None

    generated = 0
    uploaded_count = 0
    skipped = 0

    for i, entry in enumerate(uploaded, 1):
        video_file = entry["file"]
        channel = entry["channel"]
        video_id = entry["video_id"]
        title = make_title(video_file)

        # Check if thumbnail already exists
        thumb_name = os.path.splitext(video_file)[0] + "_thumb.png"
        thumb_path = os.path.join(THUMBNAILS_DIR, thumb_name)

        print(f"[{i}/{len(uploaded)}] {channel}: {title}")

        if os.path.exists(thumb_path):
            print(f"  Thumbnail exists ({os.path.getsize(thumb_path) / 1024:.0f} KB)")
        else:
            # Generate thumbnail
            thumb_path = generate_thumbnail(title, channel, video_file)
            if thumb_path:
                generated += 1
            else:
                print(f"  Thumbnail generation failed, skipping")
                skipped += 1
                continue

        # Upload to YouTube
        if not generate_only and thumb_path:
            from upload_to_youtube import TOKEN_KEY_MAP
            token_key = TOKEN_KEY_MAP.get(channel, channel)
            token = channel_access_tokens.get(token_key, default_token)
            if upload_thumbnail(video_id, thumb_path, token):
                uploaded_count += 1
            else:
                print(f"  Thumbnail upload failed for {video_id}")

    print(f"\n{'=' * 60}")
    print(f"Thumbnails generated: {generated}")
    if not generate_only:
        print(f"Thumbnails uploaded:  {uploaded_count}")
    print(f"Skipped:              {skipped}")


if __name__ == "__main__":
    main()
