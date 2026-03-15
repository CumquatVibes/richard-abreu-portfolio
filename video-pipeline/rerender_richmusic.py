#!/usr/bin/env python3
"""
rerender_richmusic.py - Re-render RichMusic 1Hr videos with B-roll images.

Replaces the showcqt spectrum visualizer with the ambient pipeline's
Ken Burns effect over actual B-roll images. Designed to run autonomously
on the PC with no arguments needed.

Steps per video:
  1. Extract audio from existing .mp4
  2. Find matching B-roll images in output/broll/
  3. Re-render using assemble_ambient_video()
  4. Back up old video as .old.mp4, replace with new render

Usage:
    python rerender_richmusic.py
"""

import glob
import os
import subprocess
import sys
import time
from pathlib import Path

# Add parent to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.ambient import assemble_ambient_video

PIPELINE_DIR = Path(__file__).resolve().parent
VIDEOS_DIR = PIPELINE_DIR / "output" / "videos"
BROLL_DIR = PIPELINE_DIR / "output" / "broll"

# Videos to re-render (filenames without extension)
RICHMUSIC_VIDEOS = [
    "RichMusic_Blues_Soul_Timeless_Classics_1Hr_Background_Music",
    "RichMusic_Ambient_Meditation_Deep_Relaxation_1Hr_Background_Music",
    "RichMusic_Classical_Piano_Orchestral_Masterpieces_1Hr_Background_Music",
    "RichMusic_Cinematic_Epic_Instrumental_1Hr_Background_Music",
    "RichMusic_Dark_Horror_Ambient_Suspense_1Hr_Background_Music",
    "RichMusic_Chill_Acoustic_Study_Vibes_1Hr_Background_Music",
    "RichMusic_Country_Folk_Instrumentals_1Hr_Background_Music",
]

# Render settings
TARGET_DURATION_HOURS = 1
SEGMENT_DURATION = 120  # 2 minutes per image
RESOLUTION = "1080p"
FPS = 24


def video_to_broll_dir(video_stem):
    """Convert video filename stem to B-roll directory name.

    Video: RichMusic_Blues_Soul_Timeless_Classics_1Hr_Background_Music
    B-roll: RichMusic_Blues_Soul_Timeless_Classics_Background_Music
    """
    return video_stem.replace("_1Hr_", "_")


def find_broll_images(broll_dir_path):
    """Find all image files in a B-roll directory, sorted."""
    extensions = ("*.png", "*.jpg", "*.jpeg", "*.webp")
    images = []
    for ext in extensions:
        images.extend(glob.glob(str(broll_dir_path / ext)))
    return sorted(images)


def extract_audio(video_path, audio_output_path):
    """Extract audio track from video using ffmpeg.

    Returns True on success.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                    # No video
        "-c:a", "aac", "-b:a", "192k",
        str(audio_output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ERROR extracting audio: {result.stderr[-300:]}")
        return False
    return True


def main():
    start_time = time.time()

    print("=" * 70)
    print("RichMusic Re-Render: showcqt -> ambient B-roll pipeline")
    print("=" * 70)
    print(f"  Videos dir: {VIDEOS_DIR}")
    print(f"  B-roll dir: {BROLL_DIR}")
    print(f"  Settings:   {TARGET_DURATION_HOURS}h, {SEGMENT_DURATION}s/segment, {RESOLUTION}")
    print()

    rendered = []
    skipped = []
    failed = []

    for video_stem in RICHMUSIC_VIDEOS:
        video_path = VIDEOS_DIR / f"{video_stem}.mp4"
        broll_name = video_to_broll_dir(video_stem)
        broll_path = BROLL_DIR / broll_name

        print("-" * 70)
        print(f"VIDEO: {video_stem}")

        # Check if source video exists
        if not video_path.exists():
            print(f"  SKIP: Video not found at {video_path}")
            skipped.append((video_stem, "video not found"))
            continue

        # Check if B-roll directory exists
        if not broll_path.exists() or not broll_path.is_dir():
            print(f"  SKIP: No B-roll directory at {broll_path}")
            skipped.append((video_stem, "no B-roll directory"))
            continue

        # Find B-roll images
        images = find_broll_images(broll_path)
        if not images:
            print(f"  SKIP: No images found in {broll_path}")
            skipped.append((video_stem, "no images in B-roll dir"))
            continue

        print(f"  B-roll: {len(images)} images in {broll_name}/")
        for img in images:
            print(f"    - {os.path.basename(img)}")

        # Step 1: Extract audio from existing video
        audio_path = VIDEOS_DIR / f"{video_stem}_extracted_audio.m4a"
        print(f"  Extracting audio...")
        if not extract_audio(video_path, audio_path):
            print(f"  FAILED: Could not extract audio")
            failed.append((video_stem, "audio extraction failed"))
            continue

        # Step 2: Back up the old video
        backup_path = VIDEOS_DIR / f"{video_stem}.old.mp4"
        if backup_path.exists():
            print(f"  Backup already exists: {backup_path.name}")
        else:
            print(f"  Backing up: {video_path.name} -> {backup_path.name}")
            os.rename(str(video_path), str(backup_path))

        # Step 3: Re-render with ambient pipeline
        print(f"  Rendering with ambient pipeline...")
        render_start = time.time()

        success, size_mb, duration_sec = assemble_ambient_video(
            images=images,
            audio_path=str(audio_path),
            output_path=str(video_path),
            target_duration_hours=TARGET_DURATION_HOURS,
            segment_duration=SEGMENT_DURATION,
            resolution=RESOLUTION,
            fps=FPS,
            verbose=True,
        )

        render_elapsed = time.time() - render_start

        # Clean up extracted audio
        if audio_path.exists():
            os.remove(str(audio_path))

        if success:
            print(f"  SUCCESS: {size_mb:.0f} MB, {duration_sec/3600:.1f}h "
                  f"(rendered in {render_elapsed/60:.1f} min)")
            rendered.append((video_stem, size_mb, duration_sec, render_elapsed))
        else:
            print(f"  FAILED: Render did not complete")
            # Restore backup if render failed
            if backup_path.exists() and not video_path.exists():
                print(f"  Restoring backup...")
                os.rename(str(backup_path), str(video_path))
            failed.append((video_stem, "render failed"))

    # Summary
    total_elapsed = time.time() - start_time
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total time: {total_elapsed/60:.1f} min ({total_elapsed/3600:.1f} h)")
    print()

    if rendered:
        print(f"  RENDERED ({len(rendered)}):")
        for stem, size, dur, elapsed in rendered:
            print(f"    {stem}")
            print(f"      {size:.0f} MB | {dur/3600:.1f}h | rendered in {elapsed/60:.1f} min")

    if skipped:
        print(f"\n  SKIPPED ({len(skipped)}):")
        for stem, reason in skipped:
            print(f"    {stem}: {reason}")

    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for stem, reason in failed:
            print(f"    {stem}: {reason}")

    print()
    print(f"  Totals: {len(rendered)} rendered, {len(skipped)} skipped, {len(failed)} failed")
    print("=" * 70)

    # Exit with error code if anything failed
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
