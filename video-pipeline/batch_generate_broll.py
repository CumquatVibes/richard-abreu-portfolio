#!/usr/bin/env python3
"""Batch B-roll generation for all scripts missing B-roll images.

Prioritizes scripts with fewer visuals first for maximum channel coverage.
Skips scripts that already have B-roll directories with images.
Respects Gemini free tier daily quota (~2000 RPD) with a configurable cap.
"""

import os
import re
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from utils.broll import generate_broll

SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "output", "scripts")
BROLL_DIR = os.path.join(os.path.dirname(__file__), "output", "broll")

# --- Quota management ---
DAILY_IMAGE_CAP = 1800          # Stay safely under Gemini free tier ~2000/day
MAX_CONSECUTIVE_FAILS = 5       # Stop early if this many scripts in a row fully fail (likely rate limited)


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

    capped_images = min(total_images, DAILY_IMAGE_CAP)

    print(f"Batch B-Roll Generator")
    print(f"=" * 60)
    print(f"Scripts to process: {len(scripts)}")
    print(f"Total images to generate: {total_images}")
    print(f"Daily quota cap: {DAILY_IMAGE_CAP} images")
    print(f"This run will generate up to: {capped_images} images")
    print(f"Estimated time: {capped_images * 6 / 3600:.1f} hours")
    print(f"=" * 60)
    print()

    total_generated = 0
    total_failed = 0
    total_api_calls = 0
    completed_scripts = 0
    consecutive_full_fails = 0
    stop_reason = "all done"
    start_time = time.time()

    for i, (visual_count, channel, name, path) in enumerate(scripts, 1):
        # Check daily quota cap before starting next script
        if total_api_calls >= DAILY_IMAGE_CAP:
            remaining = len(scripts) - completed_scripts
            stop_reason = f"daily quota cap ({DAILY_IMAGE_CAP} API calls)"
            print(f"\n  Hit daily quota cap: {total_api_calls}/{DAILY_IMAGE_CAP} API calls.")
            print(f"  {remaining} scripts deferred to next run.")
            break

        # Check consecutive failure threshold (likely rate limited)
        if consecutive_full_fails >= MAX_CONSECUTIVE_FAILS:
            remaining = len(scripts) - completed_scripts
            stop_reason = f"rate limited ({consecutive_full_fails} consecutive full failures)"
            print(f"\n  Stopping: {consecutive_full_fails} scripts in a row fully failed (likely rate limited).")
            print(f"  {remaining} scripts deferred to next run.")
            break

        elapsed = time.time() - start_time
        rate = total_generated / max(elapsed, 1) * 3600

        print(f"\n=== [{i}/{len(scripts)}] {channel}: {name[:60]} ===")
        print(f"    Visuals: {visual_count} | Progress: {total_generated}/{total_images} | API calls: {total_api_calls}/{DAILY_IMAGE_CAP} | Rate: {rate:.0f} img/hr")

        try:
            broll_dir, generated, failed, api_calls = generate_broll(path, channel=channel)
            total_generated += generated
            total_failed += failed
            total_api_calls += api_calls
            completed_scripts += 1

            # Track consecutive full failures (all visuals failed = likely rate limited)
            if api_calls > 0 and generated == 0:
                consecutive_full_fails += 1
            else:
                consecutive_full_fails = 0

            print(f"  Result: {generated} generated, {failed} failed -> {broll_dir}")
        except KeyboardInterrupt:
            stop_reason = "interrupted by user"
            print(f"\n\nInterrupted! Completed {completed_scripts} scripts, {total_generated} images.")
            break
        except Exception as e:
            print(f"  ERROR: {e}")
            total_failed += visual_count
            consecutive_full_fails += 1

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"BATCH COMPLETE — stopped: {stop_reason}")
    print(f"  Scripts processed: {completed_scripts}/{len(scripts)}")
    print(f"  Images generated: {total_generated}")
    print(f"  Images failed: {total_failed}")
    print(f"  API calls made: {total_api_calls}/{DAILY_IMAGE_CAP}")
    print(f"  Time: {elapsed/3600:.1f} hours ({elapsed:.0f}s)")
    if completed_scripts < len(scripts):
        print(f"  Remaining: {len(scripts) - completed_scripts} scripts — run again after quota resets")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
