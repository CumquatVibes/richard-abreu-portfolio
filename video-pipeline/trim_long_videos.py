#!/usr/bin/env python3
"""Trim videos longer than 14.5 minutes to fit unverified YouTube channel limits.

Uses ffmpeg stream copy (no re-encoding) for speed. Replaces originals with
trimmed versions and keeps originals in a backup directory.

Usage:
    python3 trim_long_videos.py              # trim all >14.5min videos
    python3 trim_long_videos.py --dry-run    # preview without trimming
    python3 trim_long_videos.py --channel CumquatMotivation  # specific channel
"""

import glob
import json
import os
import subprocess
import sys
import time

VIDEOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "videos")
BACKUP_DIR = os.path.join(VIDEOS_DIR, "originals_60min")
MAX_DURATION = 15 * 60  # YouTube's 15min limit
TARGET_DURATION = 840  # 14m00s — safe buffer for keyframe drift in stream copy


def get_duration(filepath):
    """Get video duration in seconds."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", filepath],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return None


def trim_video(src, dst, duration=TARGET_DURATION):
    """Trim video to target duration using stream copy (no re-encode)."""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", src,
            "-t", str(duration),
            "-c", "copy",
            "-movflags", "+faststart",
            dst,
        ],
        capture_output=True, text=True, timeout=300,
    )
    return result.returncode == 0


def main():
    dry_run = "--dry-run" in sys.argv
    channel_filter = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--channel" and i + 1 < len(sys.argv) - 1:
            channel_filter = sys.argv[i + 2]
        elif arg.startswith("--channel="):
            channel_filter = arg.split("=", 1)[1]

    os.makedirs(BACKUP_DIR, exist_ok=True)

    videos = sorted(glob.glob(os.path.join(VIDEOS_DIR, "*.mp4")))
    if channel_filter:
        videos = [v for v in videos if os.path.basename(v).startswith(channel_filter)]

    long_videos = []
    for v in videos:
        dur = get_duration(v)
        if dur and dur > MAX_DURATION:
            long_videos.append((v, dur))

    print("=" * 60)
    print(f"  VIDEO TRIMMER — {len(long_videos)} videos to trim")
    if dry_run:
        print("  MODE: DRY RUN")
    print("=" * 60)

    trimmed = 0
    failed = 0
    saved_mb = 0

    for i, (filepath, duration) in enumerate(long_videos, 1):
        fname = os.path.basename(filepath)
        channel = fname.split("_")[0]
        dur_min = int(duration // 60)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)

        print(f"\n[{i}/{len(long_videos)}] {fname}")
        print(f"  Channel: {channel} | Duration: {dur_min}min | Size: {size_mb:.0f}MB")

        if dry_run:
            print(f"  -> Would trim to {TARGET_DURATION // 60}m{TARGET_DURATION % 60:.0f}s")
            trimmed += 1
            continue

        # Trim to temp file
        tmp_path = filepath + ".trimmed.mp4"
        print(f"  Trimming to {TARGET_DURATION // 60:.0f}m{TARGET_DURATION % 60:.0f}s...", end=" ", flush=True)

        if trim_video(filepath, tmp_path):
            new_size = os.path.getsize(tmp_path) / (1024 * 1024)
            saved = size_mb - new_size

            # Backup original
            backup_path = os.path.join(BACKUP_DIR, fname)
            os.rename(filepath, backup_path)

            # Replace with trimmed version
            os.rename(tmp_path, filepath)

            new_dur = get_duration(filepath)
            new_dur_min = int(new_dur // 60) if new_dur else 0
            new_dur_sec = int(new_dur % 60) if new_dur else 0

            print(f"OK! {new_dur_min}m{new_dur_sec}s, {new_size:.0f}MB (saved {saved:.0f}MB)")
            trimmed += 1
            saved_mb += saved
        else:
            print("FAILED")
            failed += 1
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    print(f"\n{'=' * 60}")
    print(f"  COMPLETE")
    print(f"  Trimmed: {trimmed}/{len(long_videos)}")
    if failed:
        print(f"  Failed: {failed}")
    if not dry_run:
        print(f"  Disk saved: {saved_mb / 1024:.1f} GB")
        print(f"  Originals backed up to: {BACKUP_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
