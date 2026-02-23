#!/usr/bin/env python3
"""
produce_ambient.py - Produce long-form ambient/endless videos.

Creates 1-12 hour looping videos from images + audio for channels like:
- rich_music (lofi, study beats)
- rich_nature (ocean, rain, forest)
- how_to_meditate (sleep, meditation)
- rich_art (4K art slideshows for Samsung Frame TV)
- rich_horror (dark ambient)
- rich_travel (city walks, cafe)
- rich_fitness (workout mixes)

Usage:
    # Art slideshow (4K, 1 hour, 6 paintings)
    python produce_ambient.py art-slideshow --images /path/to/art/*.png --duration 1 --resolution 4k

    # Ambient video (lofi study, 3 hours)
    python produce_ambient.py ambient --images /path/to/visuals/*.png --audio /path/to/lofi.mp3 --duration 3

    # From channel config
    python produce_ambient.py channel rich_music --loop-type "Lo-fi Study Beats" --images /path/to/*.png --audio /path/to/music.mp3

    # List available loop types for a channel
    python produce_ambient.py list-loops rich_music
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path

# Add parent to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.ambient import (
    assemble_ambient_video,
    assemble_art_slideshow,
)

PIPELINE_DIR = Path(__file__).resolve().parent
CHANNELS_CONFIG = PIPELINE_DIR / "channels_config.json"
OUTPUT_DIR = PIPELINE_DIR / "output"
VIDEOS_DIR = OUTPUT_DIR / "videos"


def load_channels_config():
    with open(CHANNELS_CONFIG, "r") as f:
        return json.load(f)


def cmd_list_loops(args):
    """List available loop types for a channel."""
    config = load_channels_config()
    looping = config.get("ecosystem", {}).get("looping_content_strategy", {})
    channels = looping.get("channels", {})

    if args.channel:
        if args.channel not in channels:
            print(f"Channel '{args.channel}' has no looping content configured.")
            print(f"Available: {', '.join(channels.keys())}")
            return
        ch = channels[args.channel]
        print(f"\n{args.channel} loop types:")
        for lt in ch.get("loop_types", []):
            print(f"  - {lt['name']}")
            print(f"    Genre: {lt.get('genre', 'N/A')}")
            print(f"    Mood: {lt.get('mood', 'N/A')}")
            print(f"    Visual: {lt.get('visual', 'N/A')}")
            print(f"    Duration: {lt.get('duration', 'N/A')}")
            print()
    else:
        print("\nAll channels with looping content:")
        for ch_name, ch_data in channels.items():
            types = ch_data.get("loop_types", [])
            print(f"  {ch_name}: {len(types)} loop types")
            for lt in types:
                print(f"    - {lt['name']} ({lt.get('duration', '?')})")
        print(f"\nDuration tiers:")
        for tier, data in looping.get("duration_tiers", {}).items():
            print(f"  {tier}: {data['duration']} — {data['use']} (ads: {data['mid_roll_ads']})")


def cmd_art_slideshow(args):
    """Produce a 4K art slideshow video."""
    images = _resolve_images(args.images)
    if not images:
        print("No images found.")
        return

    duration_per_image = args.per_image * 60  # Convert minutes to seconds

    output_name = args.name or f"art_slideshow_{len(images)}works_{args.duration}h"
    output_path = str(VIDEOS_DIR / f"{output_name}.mp4")
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nProducing art slideshow:")
    print(f"  Images: {len(images)}")
    print(f"  Per image: {args.per_image} min")
    print(f"  Resolution: {args.resolution}")
    print(f"  Music: {args.music or 'none'}")
    print(f"  Output: {output_path}\n")

    success, size_mb, duration = assemble_art_slideshow(
        images=images,
        output_path=output_path,
        duration_per_image=duration_per_image,
        resolution=args.resolution,
        music_path=args.music,
        music_volume=args.music_volume,
        verbose=True,
    )

    if success:
        print(f"\nDone: {output_path}")
        print(f"  Size: {size_mb:.0f} MB")
        print(f"  Duration: {duration/3600:.1f} hours")
    else:
        print("\nFailed to produce art slideshow.")


def cmd_ambient(args):
    """Produce a long-form ambient video."""
    images = _resolve_images(args.images)
    if not images:
        print("No images found.")
        return

    if not args.audio:
        print("--audio is required for ambient videos.")
        return

    output_name = args.name or f"ambient_{args.duration}h"
    output_path = str(VIDEOS_DIR / f"{output_name}.mp4")
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nProducing ambient video:")
    print(f"  Images: {len(images)}")
    print(f"  Audio: {args.audio}")
    print(f"  Duration: {args.duration}h")
    print(f"  Segment: {args.segment}s")
    print(f"  Resolution: {args.resolution}")
    print(f"  Output: {output_path}\n")

    success, size_mb, duration = assemble_ambient_video(
        images=images,
        audio_path=args.audio,
        output_path=output_path,
        target_duration_hours=args.duration,
        segment_duration=args.segment,
        resolution=args.resolution,
        fps=24,
        verbose=True,
    )

    if success:
        print(f"\nDone: {output_path}")
        print(f"  Size: {size_mb:.0f} MB")
        print(f"  Duration: {duration/3600:.1f} hours")
    else:
        print("\nFailed to produce ambient video.")


def cmd_channel(args):
    """Produce ambient video from channel config."""
    config = load_channels_config()
    looping = config.get("ecosystem", {}).get("looping_content_strategy", {})
    channels = looping.get("channels", {})

    if args.channel not in channels:
        print(f"Channel '{args.channel}' has no looping content configured.")
        return

    ch = channels[args.channel]
    loop_types = ch.get("loop_types", [])

    # Find matching loop type
    loop_config = None
    for lt in loop_types:
        if lt["name"].lower() == args.loop_type.lower():
            loop_config = lt
            break

    if not loop_config:
        print(f"Loop type '{args.loop_type}' not found for {args.channel}.")
        print(f"Available: {', '.join(lt['name'] for lt in loop_types)}")
        return

    images = _resolve_images(args.images)
    if not images:
        print("No images found. Use --images to specify image paths.")
        return

    if not args.audio:
        print("--audio is required.")
        return

    # Parse target duration from config (e.g. "2-4 hours" -> use middle)
    dur_str = loop_config.get("duration", "1 hour")
    duration = _parse_duration(dur_str) if not args.duration else args.duration

    safe_name = loop_config["name"].replace(" ", "_").replace("/", "_")
    output_name = args.name or f"{args.channel}_{safe_name}_{duration}h"
    output_path = str(VIDEOS_DIR / f"{output_name}.mp4")
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nProducing: {loop_config['name']}")
    print(f"  Channel: {args.channel}")
    print(f"  Genre: {loop_config.get('genre', 'N/A')}")
    print(f"  Mood: {loop_config.get('mood', 'N/A')}")
    print(f"  Duration: {duration}h")
    print(f"  Images: {len(images)}")
    print(f"  Output: {output_path}\n")

    success, size_mb, dur = assemble_ambient_video(
        images=images,
        audio_path=args.audio,
        output_path=output_path,
        target_duration_hours=duration,
        segment_duration=args.segment,
        resolution=args.resolution,
        fps=24,
        verbose=True,
    )

    if success:
        print(f"\nDone: {output_path}")
        print(f"  Size: {size_mb:.0f} MB")
        print(f"  Duration: {dur/3600:.1f} hours")
    else:
        print("\nFailed to produce ambient video.")


def _resolve_images(image_args):
    """Resolve image arguments (glob patterns or file paths) to sorted list."""
    images = []
    for pattern in image_args:
        expanded = glob.glob(pattern)
        if expanded:
            images.extend(expanded)
        elif os.path.isfile(pattern):
            images.append(pattern)
    return sorted(set(images))


def _parse_duration(dur_str):
    """Parse duration string like '2-4 hours' to float (midpoint)."""
    import re
    numbers = re.findall(r"[\d.]+", dur_str)
    if len(numbers) >= 2:
        return (float(numbers[0]) + float(numbers[1])) / 2
    elif numbers:
        return float(numbers[0])
    return 1.0


def main():
    parser = argparse.ArgumentParser(
        description="Produce long-form ambient / endless videos"
    )
    subparsers = parser.add_subparsers(dest="command")

    # list-loops
    p_list = subparsers.add_parser("list-loops", help="List loop types for a channel")
    p_list.add_argument("channel", nargs="?", help="Channel name (optional)")

    # art-slideshow
    p_art = subparsers.add_parser("art-slideshow", help="Produce 4K art slideshow")
    p_art.add_argument("--images", nargs="+", required=True, help="Image paths or glob patterns")
    p_art.add_argument("--per-image", type=float, default=10, help="Minutes per artwork (default 10)")
    p_art.add_argument("--resolution", default="4k", choices=["1080p", "4k"])
    p_art.add_argument("--music", help="Optional ambient music file")
    p_art.add_argument("--music-volume", type=float, default=0.15)
    p_art.add_argument("--name", help="Output filename (without extension)")
    p_art.add_argument("--duration", type=float, help="Override total duration (hours)")

    # ambient
    p_amb = subparsers.add_parser("ambient", help="Produce long-form ambient video")
    p_amb.add_argument("--images", nargs="+", required=True, help="Image paths or glob patterns")
    p_amb.add_argument("--audio", required=True, help="Audio file (will be looped)")
    p_amb.add_argument("--duration", type=float, default=1, help="Target duration in hours (default 1)")
    p_amb.add_argument("--segment", type=int, default=120, help="Seconds per image (default 120)")
    p_amb.add_argument("--resolution", default="1080p", choices=["1080p", "4k"])
    p_amb.add_argument("--name", help="Output filename (without extension)")

    # channel
    p_ch = subparsers.add_parser("channel", help="Produce from channel config")
    p_ch.add_argument("channel", help="Channel name from channels_config.json")
    p_ch.add_argument("--loop-type", required=True, help="Loop type name")
    p_ch.add_argument("--images", nargs="+", required=True, help="Image paths or glob patterns")
    p_ch.add_argument("--audio", required=True, help="Audio file")
    p_ch.add_argument("--duration", type=float, help="Override duration (hours)")
    p_ch.add_argument("--segment", type=int, default=120, help="Seconds per image")
    p_ch.add_argument("--resolution", default="1080p", choices=["1080p", "4k"])
    p_ch.add_argument("--name", help="Output filename (without extension)")

    args = parser.parse_args()

    if args.command == "list-loops":
        cmd_list_loops(args)
    elif args.command == "art-slideshow":
        cmd_art_slideshow(args)
    elif args.command == "ambient":
        cmd_ambient(args)
    elif args.command == "channel":
        cmd_channel(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
