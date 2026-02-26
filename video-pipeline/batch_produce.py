#!/usr/bin/env python3
"""Batch produce all faceless YouTube videos.

For each script:
1. Generate B-roll images from [VISUAL: ...] directions (Gemini API)
2. Assemble video with Ken Burns effects + voiceover audio (ffmpeg)

Handles API rate limits with exponential backoff.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.assembly import assemble_video
from utils.broll import generate_broll, get_broll_template
from utils.common import find_audio_for_script, strip_timestamp, SCRIPTS_DIR, VIDEOS_DIR
from utils.telemetry import log_video_planned, log_video_produced, update_costs
from utils.bandits import select_arm

# Cost rates (USD)
TTS_COST_PER_CHAR = 0.30 / 1000   # ElevenLabs Scale: $0.30 per 1K chars
BROLL_COST_PER_CALL = 0.0          # Gemini Flash free tier; update if on paid plan

os.makedirs(VIDEOS_DIR, exist_ok=True)


def main():
    print("=" * 60)
    print("BATCH VIDEO PRODUCTION")
    print("=" * 60)

    scripts = sorted([
        os.path.join(SCRIPTS_DIR, f) for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".txt")
    ])

    print(f"\nFound {len(scripts)} scripts\n")

    results = {"success": [], "failed": [], "skipped": []}

    for i, script_path in enumerate(scripts, 1):
        basename = os.path.splitext(os.path.basename(script_path))[0]
        video_name = strip_timestamp(basename)
        channel = basename.split("_")[0]

        # Consult bandit for optimal production settings
        channel_key = channel.lower()
        arm_result = select_arm(channel_key)
        arm_name = arm_result.get("arm_name") if not arm_result.get("error") else None

        output_path = os.path.join(VIDEOS_DIR, f"{video_name}.mp4")

        print(f"\n[{i}/{len(scripts)}] {video_name}")
        print("-" * 50)

        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  SKIP (exists): {size_mb:.1f} MB")
            results["skipped"].append(video_name)
            continue

        # Log planned video with bandit arm
        try:
            log_video_planned(video_name, channel, topic=video_name, template_arm=arm_name)
        except Exception:
            pass  # telemetry should never block production

        audio_path, _ = find_audio_for_script(basename)
        if not audio_path:
            print(f"  SKIP: No matching audio found")
            results["failed"].append(video_name)
            continue

        # Generate B-roll
        print(f"  Generating B-roll...")
        broll_dir, broll_count, _, broll_api_calls = generate_broll(script_path, channel=channel)

        if broll_count == 0:
            print(f"  SKIP: No B-roll generated")
            results["failed"].append(video_name)
            continue

        # Count TTS characters from the audio's source script
        tts_chars = 0
        try:
            with open(script_path) as f:
                tts_chars = len(f.read())
        except Exception:
            pass

        # Assemble video with channel-specific segment duration + crossfade
        print(f"  Assembling video...")
        template = get_broll_template(channel)
        seg_dur = template["segment_duration"]
        success, size_mb, duration = assemble_video(
            audio_path, broll_dir, output_path,
            segment_duration=seg_dur, crossfade=0.5
        )

        if success:
            results["success"].append(video_name)
            try:
                log_video_produced(video_name, channel=channel,
                                   video_path=output_path,
                                   video_duration_sec=duration,
                                   video_size_mb=size_mb,
                                   broll_generated=broll_count,
                                   segment_duration=seg_dur,
                                   template_arm=arm_name)
                update_costs(video_name,
                             tts_characters=tts_chars,
                             tts_cost_usd=round(tts_chars * TTS_COST_PER_CHAR, 4),
                             broll_api_calls=broll_api_calls,
                             broll_cost_usd=round(broll_api_calls * BROLL_COST_PER_CALL, 4))
            except Exception:
                pass
        else:
            results["failed"].append(video_name)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"BATCH COMPLETE")
    print(f"{'=' * 60}")
    print(f"Success: {len(results['success'])}")
    print(f"Skipped: {len(results['skipped'])}")
    print(f"Failed:  {len(results['failed'])}")

    if results["success"]:
        print(f"\nNew videos:")
        for v in results["success"]:
            print(f"  + {v}")

    if results["failed"]:
        print(f"\nFailed:")
        for v in results["failed"]:
            print(f"  x {v}")

    print(f"\nOutput: {VIDEOS_DIR}")


if __name__ == "__main__":
    main()
