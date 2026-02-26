#!/usr/bin/env python3
"""Batch B-roll generation for all scripts missing B-roll images.

Prioritizes scripts with fewer visuals first for maximum channel coverage.
Skips scripts that already have B-roll directories with images.
"""

import os
import re
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from utils.broll import generate_broll

SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "output", "scripts")
BROLL_DIR = os.path.join(os.path.dirname(__file__), "output", "broll")


def find_scripts_needing_broll():
    """Find scripts with [VISUAL:] tags that don't yet have B-roll."""
    existing_broll = set(os.listdir(BROLL_DIR))

    ready = []
    for s in sorted(os.listdir(SCRIPT_DIR)):
        if not s.endswith(".txt"):
            continue
        name = s.replace(".txt", "")

        # Skip if B-roll directory exists AND has images
        if name in existing_broll:
            broll_path = os.path.join(BROLL_DIR, name)
            pngs = [f for f in os.listdir(broll_path) if f.endswith(".png")]
            if pngs:
                continue

        path = os.path.join(SCRIPT_DIR, s)
        with open(path) as f:
            content = f.read()

        visual_count = len(re.findall(r"\[VISUAL:", content))
        if visual_count > 0:
            channel = name.split("_")[0]
            ready.append((visual_count, channel, name, path))

    # Sort by visual count (fewest first for quick coverage)
    ready.sort(key=lambda x: x[0])
    return ready


def main():
    scripts = find_scripts_needing_broll()
    total_images = sum(s[0] for s in scripts)

    print(f"Batch B-Roll Generator")
    print(f"=" * 60)
    print(f"Scripts to process: {len(scripts)}")
    print(f"Total images to generate: {total_images}")
    print(f"Estimated time: {total_images * 6 / 3600:.1f} hours")
    print(f"=" * 60)
    print()

    total_generated = 0
    total_failed = 0
    completed_scripts = 0
    start_time = time.time()

    for i, (visual_count, channel, name, path) in enumerate(scripts, 1):
        elapsed = time.time() - start_time
        rate = total_generated / max(elapsed, 1) * 3600

        print(f"\n=== [{i}/{len(scripts)}] {channel}: {name[:60]} ===")
        print(f"    Visuals: {visual_count} | Progress: {total_generated}/{total_images} | Rate: {rate:.0f} img/hr")

        try:
            broll_dir, generated, failed, _ = generate_broll(path, channel=channel)
            total_generated += generated
            total_failed += failed
            completed_scripts += 1
            print(f"  Result: {generated} generated, {failed} failed -> {broll_dir}")
        except KeyboardInterrupt:
            print(f"\n\nInterrupted! Completed {completed_scripts} scripts, {total_generated} images.")
            break
        except Exception as e:
            print(f"  ERROR: {e}")
            total_failed += visual_count

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"BATCH COMPLETE")
    print(f"  Scripts processed: {completed_scripts}/{len(scripts)}")
    print(f"  Images generated: {total_generated}")
    print(f"  Images failed: {total_failed}")
    print(f"  Time: {elapsed/3600:.1f} hours ({elapsed:.0f}s)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
