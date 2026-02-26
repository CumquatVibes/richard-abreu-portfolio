#!/usr/bin/env python3
"""Generate B-roll images for a video script using Gemini image generation.

Usage:
    python generate_broll.py [script_path]
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.broll import generate_broll
from utils.common import get_channel_from_filename


def main():
    script_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        BASE_DIR, "output", "scripts",
        "RichMind_7_Dark_Psychology_Tricks_That_Manipulators_Use_on_You_Every_Day_20260219_155540.txt"
    )

    basename = os.path.splitext(os.path.basename(script_path))[0]
    channel = get_channel_from_filename(script_path)

    print(f"Generating B-roll for: {basename}")
    print(f"Channel: {channel}\n")

    broll_dir, generated, failed, _ = generate_broll(script_path, channel=channel)

    print(f"\nDone! {generated} generated, {failed} failed.")
    print(f"Output: {broll_dir}")


if __name__ == "__main__":
    main()
