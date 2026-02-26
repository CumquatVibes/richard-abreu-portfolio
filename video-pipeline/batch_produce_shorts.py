#!/usr/bin/env python3
"""Batch produce YouTube Shorts from long-form videos and shorts-format scripts.

Path A: Repurpose existing long-form videos (output/videos/) into vertical shorts.
Path B: Produce native vertical shorts from shorts-format scripts (shorts_facts, shorts_story).

Usage:
    python3 batch_produce_shorts.py                    # Run both paths
    python3 batch_produce_shorts.py --path-a           # Only repurpose long-form
    python3 batch_produce_shorts.py --path-b           # Only native shorts
    python3 batch_produce_shorts.py --channel RichMind # Filter by channel
    python3 batch_produce_shorts.py --dry-run          # Show what would be produced
    python3 batch_produce_shorts.py --max-clips 2      # Max clips per source video
    python3 batch_produce_shorts.py --no-captions      # Skip caption rendering
"""

import argparse
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.shorts import (
    parse_script_segments, find_best_clips, extract_clip,
    crop_to_vertical, add_hook_overlay, assemble_vertical_video,
    SHORTS_DIR,
)
from utils.captions import (
    transcribe_audio, estimate_word_timestamps,
    generate_caption_segments, render_captions_to_video,
    get_video_info,
)
from utils.common import (
    SCRIPTS_DIR, AUDIO_DIR, BROLL_DIR, VIDEOS_DIR,
    find_audio_for_script, strip_timestamp, get_channel_from_filename,
)
from utils.broll import generate_broll, extract_visuals
from utils.telemetry import log_short_produced


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch produce YouTube Shorts from long-form videos and shorts scripts.",
    )
    parser.add_argument("--path-a", action="store_true",
                        help="Only repurpose long-form videos into shorts")
    parser.add_argument("--path-b", action="store_true",
                        help="Only produce native shorts from shorts-format scripts")
    parser.add_argument("--channel", type=str, default=None,
                        help="Filter by channel name (e.g. RichMind)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be produced without actually producing")
    parser.add_argument("--max-clips", type=int, default=3,
                        help="Max clips per source video for Path A (default: 3)")
    parser.add_argument("--no-captions", action="store_true",
                        help="Skip caption rendering")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_script_for_video(video_basename):
    """Find the matching script for a video file.

    Video: RichMind_7_Dark_Psychology_Tricks
    Script: RichMind_7_Dark_Psychology_Tricks_20260219_155540.txt
    Match by: strip timestamp from script name, compare to video basename.

    Returns:
        str | None: Full path to the matching script, or None.
    """
    if not os.path.isdir(SCRIPTS_DIR):
        return None

    for fname in os.listdir(SCRIPTS_DIR):
        if not fname.endswith(".txt"):
            continue
        script_base = os.path.splitext(fname)[0]
        if strip_timestamp(script_base) == video_basename:
            return os.path.join(SCRIPTS_DIR, fname)
    return None


def _short_exists(prefix):
    """Check if any short with the given prefix already exists in SHORTS_DIR."""
    if not os.path.isdir(SHORTS_DIR):
        return False
    for fname in os.listdir(SHORTS_DIR):
        if fname.startswith(prefix) and fname.endswith(".mp4"):
            return True
    return False


def _add_captions(video_path, segment_text, no_captions, caption_style="capcut", caption_position="center"):
    """Add captions to a video file in-place (via temp file).

    Returns True on success, False on skip/failure.
    """
    if no_captions:
        return False

    info = get_video_info(video_path)
    if not info:
        print("    [captions] Could not probe video info, skipping captions")
        return False

    duration = info["duration"]

    # Try Whisper transcription first, fall back to estimation
    words = transcribe_audio(video_path)
    if words is None:
        if segment_text:
            words = estimate_word_timestamps(segment_text, duration)
        else:
            print("    [captions] No transcript and no segment text, skipping")
            return False

    if not words:
        print("    [captions] No words to caption, skipping")
        return False

    caption_segments = generate_caption_segments(words, style=caption_style)
    if not caption_segments:
        print("    [captions] No caption segments generated, skipping")
        return False

    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(temp_fd)

    try:
        success = render_captions_to_video(video_path, temp_path, caption_segments,
                                                style=caption_style, position=caption_position)
        if success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
            shutil.move(temp_path, video_path)
            return True
        else:
            print("    [captions] Caption rendering failed")
            return False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ---------------------------------------------------------------------------
# Path A: Repurpose long-form videos
# ---------------------------------------------------------------------------

def produce_shorts_from_longform(results, channel_filter=None, dry_run=False,
                                  max_clips=3, no_captions=False):
    """Repurpose long-form videos into vertical shorts."""
    print("\n" + "=" * 60)
    print("PATH A: Repurpose Long-Form Videos")
    print("=" * 60)

    if not os.path.isdir(VIDEOS_DIR):
        print(f"\n  No videos directory found at {VIDEOS_DIR}")
        return

    videos = sorted([
        f for f in os.listdir(VIDEOS_DIR)
        if f.endswith(".mp4")
    ])

    if channel_filter:
        videos = [v for v in videos if get_channel_from_filename(v) == channel_filter]

    print(f"\nFound {len(videos)} source video(s)\n")

    for vi, video_file in enumerate(videos, 1):
        video_path = os.path.join(VIDEOS_DIR, video_file)
        video_basename = os.path.splitext(video_file)[0]
        channel = get_channel_from_filename(video_file)

        print(f"\n[{vi}/{len(videos)}] {video_basename}")
        print("-" * 50)

        # Find matching script
        script_path = _find_script_for_video(video_basename)
        if not script_path:
            print("  SKIP: No matching script found")
            results["path_a"]["skipped"].append(video_basename)
            continue

        # Parse segments and find best clips
        segments = parse_script_segments(script_path)
        if not segments:
            print("  SKIP: No segments parsed from script")
            results["path_a"]["skipped"].append(video_basename)
            continue

        clips = find_best_clips(segments)
        if not clips:
            print("  SKIP: No suitable clips found")
            results["path_a"]["skipped"].append(video_basename)
            continue

        clips = clips[:max_clips]
        print(f"  Found {len(clips)} candidate clip(s) (max {max_clips})")

        # Consult shorts bandit for this channel
        try:
            from utils.bandits import select_arm_by_type
            shorts_arm_result = select_arm_by_type(channel.lower(), "shorts_config")
            shorts_config = shorts_arm_result.get("config", {}) if not shorts_arm_result.get("error") else {}
            shorts_arm_name = shorts_arm_result.get("arm_name") if not shorts_arm_result.get("error") else None
        except Exception:
            shorts_config = {}
            shorts_arm_name = None

        crop_strategy = shorts_config.get("crop_strategy", "center")
        caption_style = shorts_config.get("caption_style", "capcut")
        caption_position = shorts_config.get("caption_position", "center")

        for ci, clip in enumerate(clips, 1):
            short_name = f"{video_basename}_short_{ci:02d}"
            output_path = os.path.join(SHORTS_DIR, f"{short_name}.mp4")

            print(f"\n  Clip {ci}/{len(clips)}: {clip['name']} "
                  f"({clip['start_sec']:.0f}s-{clip['end_sec']:.0f}s, "
                  f"score={clip['score']})")

            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"    SKIP (exists): {size_mb:.1f} MB")
                results["path_a"]["skipped"].append(short_name)
                continue

            if dry_run:
                print(f"    DRY RUN: Would produce -> {short_name}.mp4")
                print(f"    Hook: {clip['hook_text'][:80]}")
                results["path_a"]["produced"].append(short_name)
                continue

            # Create temp directory for intermediate files
            temp_dir = tempfile.mkdtemp(prefix="shorts_a_")

            try:
                # Step 1: Extract clip
                raw_clip = os.path.join(temp_dir, "raw_clip.mp4")
                ok, _, _ = extract_clip(video_path, clip["start_sec"],
                                        clip["end_sec"], raw_clip)
                if not ok:
                    print(f"    FAILED: Could not extract clip")
                    results["path_a"]["failed"].append(short_name)
                    continue

                # Step 2: Crop to vertical
                vertical_clip = os.path.join(temp_dir, "vertical_clip.mp4")
                ok = crop_to_vertical(raw_clip, vertical_clip, strategy=crop_strategy)
                if not ok:
                    print(f"    FAILED: Could not crop to vertical")
                    results["path_a"]["failed"].append(short_name)
                    continue

                # Step 3: Captions
                _add_captions(vertical_clip, clip.get("hook_text", ""), no_captions,
                              caption_style=caption_style, caption_position=caption_position)

                # Step 4: Hook overlay
                hook_text = clip.get("hook_text", "")
                if hook_text:
                    hooked_clip = os.path.join(temp_dir, "hooked_clip.mp4")
                    ok = add_hook_overlay(vertical_clip, hooked_clip, hook_text)
                    if ok:
                        final_source = hooked_clip
                    else:
                        final_source = vertical_clip
                else:
                    final_source = vertical_clip

                # Step 5: Move to output
                os.makedirs(SHORTS_DIR, exist_ok=True)
                shutil.copy2(final_source, output_path)

                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"    OK: {short_name}.mp4 ({size_mb:.1f} MB)")
                results["path_a"]["produced"].append(short_name)

                # Log to telemetry
                try:
                    log_short_produced(
                        video_name=short_name, channel=channel,
                        source_video=video_basename, platform="youtube",
                        caption_style=caption_style if not no_captions else None,
                        video_size_mb=size_mb,
                        shorts_arm=shorts_arm_name,
                        crop_strategy=crop_strategy,
                        caption_position=caption_position)
                except Exception:
                    pass

            except Exception as exc:
                print(f"    FAILED: {exc}")
                results["path_a"]["failed"].append(short_name)

            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Path B: Native shorts from shorts-format scripts
# ---------------------------------------------------------------------------

def produce_native_shorts(results, channel_filter=None, dry_run=False,
                           no_captions=False):
    """Produce native vertical shorts from shorts-format scripts."""
    print("\n" + "=" * 60)
    print("PATH B: Native Shorts from Scripts")
    print("=" * 60)

    if not os.path.isdir(SCRIPTS_DIR):
        print(f"\n  No scripts directory found at {SCRIPTS_DIR}")
        return

    # Find shorts-format scripts
    shorts_scripts = sorted([
        f for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".txt") and ("_shorts_facts_" in f or "_shorts_story_" in f)
    ])

    if channel_filter:
        shorts_scripts = [
            s for s in shorts_scripts
            if get_channel_from_filename(s) == channel_filter
        ]

    print(f"\nFound {len(shorts_scripts)} shorts script(s)\n")

    for si, script_file in enumerate(shorts_scripts, 1):
        script_path = os.path.join(SCRIPTS_DIR, script_file)
        script_basename = os.path.splitext(script_file)[0]
        video_name = strip_timestamp(script_basename)
        channel = get_channel_from_filename(script_file)
        output_path = os.path.join(SHORTS_DIR, f"{video_name}.mp4")

        print(f"\n[{si}/{len(shorts_scripts)}] {video_name}")
        print("-" * 50)

        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  SKIP (exists): {size_mb:.1f} MB")
            results["path_b"]["skipped"].append(video_name)
            continue

        if dry_run:
            audio_path, _ = find_audio_for_script(script_basename)
            audio_status = "audio found" if audio_path else "NO AUDIO"
            print(f"  DRY RUN: Would produce -> {video_name}.mp4 ({audio_status})")
            results["path_b"]["produced"].append(video_name)
            continue

        # Find audio
        audio_path, _ = find_audio_for_script(script_basename)
        if not audio_path:
            print(f"  WARNING: No matching audio found, skipping")
            results["path_b"]["skipped"].append(video_name)
            continue

        # Check/generate B-roll
        broll_dir = os.path.join(BROLL_DIR, script_basename)
        if os.path.isdir(broll_dir) and any(
            f.startswith("broll_") and f.endswith(".png")
            for f in os.listdir(broll_dir)
        ):
            broll_count = len([
                f for f in os.listdir(broll_dir)
                if f.startswith("broll_") and f.endswith(".png")
            ])
            print(f"  B-roll: {broll_count} images (existing)")
        else:
            print(f"  Generating B-roll...")
            broll_dir, broll_count, broll_failed, _ = generate_broll(
                script_path, channel=channel,
            )
            if broll_count == 0:
                print(f"  SKIP: No B-roll generated")
                results["path_b"]["failed"].append(video_name)
                continue
            print(f"  B-roll: {broll_count} generated, {broll_failed} failed")

        # Consult shorts bandit for this channel
        try:
            from utils.bandits import select_arm_by_type
            shorts_arm_result = select_arm_by_type(channel.lower(), "shorts_config")
            shorts_config = shorts_arm_result.get("config", {}) if not shorts_arm_result.get("error") else {}
            shorts_arm_name = shorts_arm_result.get("arm_name") if not shorts_arm_result.get("error") else None
        except Exception:
            shorts_config = {}
            shorts_arm_name = None

        crop_strategy = shorts_config.get("crop_strategy", "center")
        caption_style = shorts_config.get("caption_style", "capcut")
        caption_position = shorts_config.get("caption_position", "center")

        # Assemble vertical video
        print(f"  Assembling vertical video...")
        temp_dir = tempfile.mkdtemp(prefix="shorts_b_")

        try:
            assembled_path = os.path.join(temp_dir, "assembled.mp4")
            ok, size_mb, duration = assemble_vertical_video(
                audio_path, broll_dir, assembled_path,
                segment_duration=4,
            )

            if not ok:
                print(f"  FAILED: Assembly failed")
                results["path_b"]["failed"].append(video_name)
                continue

            # Captions
            # Read script text for fallback estimation
            with open(script_path, "r", encoding="utf-8") as fh:
                script_text = fh.read()
            _add_captions(assembled_path, script_text, no_captions,
                         caption_style=caption_style, caption_position=caption_position)

            # Hook overlay — parse first narration line from script
            segments = parse_script_segments(script_path)
            hook_text = ""
            if segments:
                first_text = segments[0].get("text", "")
                if first_text:
                    hook_text = first_text.split(".")[0].strip()

            if hook_text:
                hooked_path = os.path.join(temp_dir, "hooked.mp4")
                ok = add_hook_overlay(assembled_path, hooked_path, hook_text)
                final_source = hooked_path if ok else assembled_path
            else:
                final_source = assembled_path

            # Move to output
            os.makedirs(SHORTS_DIR, exist_ok=True)
            shutil.copy2(final_source, output_path)

            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  OK: {video_name}.mp4 ({size_mb:.1f} MB, {duration:.1f}s)")
            results["path_b"]["produced"].append(video_name)

            # Log to telemetry
            try:
                log_short_produced(
                    video_name=video_name, channel=channel,
                    source_video=video_name, platform="youtube",
                    caption_style=caption_style if not no_captions else None,
                    video_size_mb=size_mb,
                    shorts_arm=shorts_arm_name,
                    crop_strategy=crop_strategy,
                    caption_position=caption_position)
            except Exception:
                pass

        except Exception as exc:
            print(f"  FAILED: {exc}")
            results["path_b"]["failed"].append(video_name)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    os.makedirs(SHORTS_DIR, exist_ok=True)

    results = {
        "path_a": {"produced": [], "skipped": [], "failed": []},
        "path_b": {"produced": [], "skipped": [], "failed": []},
    }

    print("=" * 60)
    print("BATCH SHORTS PRODUCTION")
    print("=" * 60)

    if args.channel:
        print(f"Channel filter: {args.channel}")
    if args.dry_run:
        print("Mode: DRY RUN")
    if args.no_captions:
        print("Captions: DISABLED")

    # Run Path A unless --path-b was specified exclusively
    if not args.path_b:
        produce_shorts_from_longform(
            results,
            channel_filter=args.channel,
            dry_run=args.dry_run,
            max_clips=args.max_clips,
            no_captions=args.no_captions,
        )

    # Run Path B unless --path-a was specified exclusively
    if not args.path_a:
        produce_native_shorts(
            results,
            channel_filter=args.channel,
            dry_run=args.dry_run,
            no_captions=args.no_captions,
        )

    # Final report
    print(f"\n{'=' * 60}")
    print("BATCH SHORTS COMPLETE")
    print(f"{'=' * 60}")

    for path_key, label in [("path_a", "Path A (Long-form)"), ("path_b", "Path B (Native)")]:
        r = results[path_key]
        total = len(r["produced"]) + len(r["skipped"]) + len(r["failed"])
        if total == 0:
            continue
        print(f"\n{label}:")
        print(f"  Produced: {len(r['produced'])}")
        print(f"  Skipped:  {len(r['skipped'])}")
        print(f"  Failed:   {len(r['failed'])}")

        if r["produced"]:
            print(f"\n  New shorts:")
            for name in r["produced"]:
                print(f"    + {name}")

        if r["failed"]:
            print(f"\n  Failed:")
            for name in r["failed"]:
                print(f"    x {name}")

    total_produced = len(results["path_a"]["produced"]) + len(results["path_b"]["produced"])
    total_failed = len(results["path_a"]["failed"]) + len(results["path_b"]["failed"])
    print(f"\nTotal produced: {total_produced}")
    print(f"Total failed:   {total_failed}")
    print(f"\nOutput: {SHORTS_DIR}")


if __name__ == "__main__":
    main()
