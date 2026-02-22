#!/usr/bin/env python3
"""Assemble a faceless YouTube video from B-roll images + voiceover audio.

Creates a slideshow-style video with:
- Ken Burns effects (zoom/pan) on each image
- Crossfade transitions between images
- Fast pacing (6-10 seconds per image) for retention
- 1920x1080 output at 30fps
- Voiceover audio synced to full video length

Usage:
    python assemble_video.py <audio_path> <broll_dir> [output_name]
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

OUTPUT_DIR = os.path.join(BASE_DIR, "output", "videos")
os.makedirs(OUTPUT_DIR, exist_ok=True)

from utils.assembly import assemble_video


def main():
    if len(sys.argv) >= 3:
        audio_path = sys.argv[1]
        broll_dir = sys.argv[2]
        output_name = sys.argv[3] if len(sys.argv) > 3 else "output"
    else:
        audio_path = os.path.join(
            BASE_DIR, "output", "audio",
            "RichMind_7_Dark_Psychology_Tricks_That_Manipulators_Use_on_You_Every_Day.mp3"
        )
        broll_dir = os.path.join(
            BASE_DIR, "output", "broll",
            "RichMind_7_Dark_Psychology_Tricks_That_Manipulators_Use_on_You_Every_Day_20260219_155540"
        )
        output_name = "RichMind_7_Dark_Psychology_Tricks_That_Manipulators_Use_on_You_Every_Day"

    output_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")

    print("=" * 60)
    print("FACELESS VIDEO ASSEMBLY")
    print("=" * 60)
    print(f"Audio: {os.path.basename(audio_path)}")
    print(f"B-roll: {broll_dir}")
    print(f"Output: {output_path}\n")

    success, size_mb, duration = assemble_video(
        audio_path, broll_dir, output_path,
        segment_duration=8, crossfade=0.5
    )

    if success:
        print(f"\n{'=' * 60}")
        print("VIDEO READY TO WATCH!")
        print(f"{'=' * 60}")
    else:
        print("\nVideo assembly failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
