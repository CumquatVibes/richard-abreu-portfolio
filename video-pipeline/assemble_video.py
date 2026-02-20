#!/usr/bin/env python3
"""Assemble a faceless YouTube video from B-roll images + voiceover audio.

Creates a slideshow-style video with:
- Ken Burns effects (zoom/pan) on each image
- Crossfade transitions between images
- Fast pacing (8-10 seconds per image) for retention
- 1920x1080 output at 30fps
- Voiceover audio synced to full video length
"""

import json
import os
import random
import subprocess
import sys
import math

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "videos")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def get_image_dimensions(img_path):
    """Get image dimensions using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", img_path],
        capture_output=True, text=True
    )
    w, h = result.stdout.strip().split(",")
    return int(w), int(h)


def build_ken_burns_segment(img_path, duration, effect_type, idx):
    """Build ffmpeg filter for a single Ken Burns segment.

    Effects:
    0 = slow zoom in (center)
    1 = slow zoom out (center)
    2 = pan left to right
    3 = pan right to left
    4 = zoom in top-left corner
    5 = zoom in bottom-right corner
    """
    # Start with the image scaled to 2560x1440 (oversized for pan room)
    # Then crop to 1920x1080 with animated position
    fps = 30
    total_frames = int(duration * fps)

    if effect_type == 0:  # Zoom in center
        # Scale from 1920 to 2200 over duration
        return (
            f"[{idx}:v]loop=loop={total_frames}:size=1:start=0,"
            f"setpts=N/{fps}/TB,"
            f"scale=2560:-1,"
            f"zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
        )
    elif effect_type == 1:  # Zoom out center
        return (
            f"[{idx}:v]loop=loop={total_frames}:size=1:start=0,"
            f"setpts=N/{fps}/TB,"
            f"scale=2560:-1,"
            f"zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
        )
    elif effect_type == 2:  # Pan left to right
        return (
            f"[{idx}:v]loop=loop={total_frames}:size=1:start=0,"
            f"setpts=N/{fps}/TB,"
            f"scale=2560:-1,"
            f"zoompan=z='1.1':x='(iw/zoom-ow)/({total_frames})*on':"
            f"y='(ih-oh)/2':d={total_frames}:s=1920x1080:fps={fps}"
        )
    elif effect_type == 3:  # Pan right to left
        return (
            f"[{idx}:v]loop=loop={total_frames}:size=1:start=0,"
            f"setpts=N/{fps}/TB,"
            f"scale=2560:-1,"
            f"zoompan=z='1.1':x='(iw/zoom-ow)-((iw/zoom-ow)/({total_frames}))*on':"
            f"y='(ih-oh)/2':d={total_frames}:s=1920x1080:fps={fps}"
        )
    elif effect_type == 4:  # Zoom in top-left
        return (
            f"[{idx}:v]loop=loop={total_frames}:size=1:start=0,"
            f"setpts=N/{fps}/TB,"
            f"scale=2560:-1,"
            f"zoompan=z='min(zoom+0.001,1.2)':x='0':"
            f"y='0':d={total_frames}:s=1920x1080:fps={fps}"
        )
    else:  # Zoom in bottom-right
        return (
            f"[{idx}:v]loop=loop={total_frames}:size=1:start=0,"
            f"setpts=N/{fps}/TB,"
            f"scale=2560:-1,"
            f"zoompan=z='min(zoom+0.001,1.2)':x='iw/zoom-ow':"
            f"y='ih/zoom-oh':d={total_frames}:s=1920x1080:fps={fps}"
        )


def assemble_video(audio_path, broll_dir, output_path, channel_name="RichMind"):
    """Assemble the final video."""
    # Get audio duration
    duration = get_audio_duration(audio_path)
    print(f"Audio duration: {duration:.1f}s ({duration/60:.1f} min)")

    # Collect B-roll images
    images = sorted([
        os.path.join(broll_dir, f) for f in os.listdir(broll_dir)
        if f.endswith(".png") and f.startswith("broll_")
    ])

    if not images:
        print("ERROR: No B-roll images found!")
        return False

    print(f"B-roll images: {len(images)}")

    # Calculate segments — 8 seconds per image, cycle through
    segment_duration = 8.0
    num_segments = int(math.ceil(duration / segment_duration))
    # Adjust last segment
    segments = []
    for i in range(num_segments):
        start = i * segment_duration
        seg_dur = min(segment_duration, duration - start)
        if seg_dur < 1:
            break
        img_idx = i % len(images)
        effect = i % 6  # Cycle through 6 effects
        segments.append({
            "image": images[img_idx],
            "duration": seg_dur,
            "effect": effect,
            "start": start
        })

    print(f"Video segments: {len(segments)} ({segment_duration}s each)")
    print(f"Building ffmpeg command...\n")

    # Strategy: Generate each segment as a short clip, then concat
    # This avoids complex filter graphs that can fail
    temp_dir = os.path.join(os.path.dirname(output_path), "temp_segments")
    os.makedirs(temp_dir, exist_ok=True)

    segment_files = []
    for i, seg in enumerate(segments):
        seg_file = os.path.join(temp_dir, f"seg_{i:04d}.mp4")
        segment_files.append(seg_file)

        if os.path.exists(seg_file):
            print(f"  [{i+1}/{len(segments)}] SKIP (exists)")
            continue

        fps = 30
        total_frames = int(seg["duration"] * fps)

        # Build zoompan filter based on effect type
        effects = {
            0: f"zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}",
            1: f"zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}",
            2: f"zoompan=z='1.08':x='(iw/zoom-ow)/({total_frames})*on':y='(ih-oh)/2':d={total_frames}:s=1920x1080:fps={fps}",
            3: f"zoompan=z='1.08':x='(iw/zoom-ow)-((iw/zoom-ow)/({total_frames}))*on':y='(ih-oh)/2':d={total_frames}:s=1920x1080:fps={fps}",
            4: f"zoompan=z='min(zoom+0.001,1.2)':x='0':y='0':d={total_frames}:s=1920x1080:fps={fps}",
            5: f"zoompan=z='min(zoom+0.001,1.2)':x='iw/zoom-ow':y='ih/zoom-oh':d={total_frames}:s=1920x1080:fps={fps}",
        }

        filter_str = f"scale=2560:-1,{effects[seg['effect']]},format=yuv420p"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", seg["image"],
            "-vf", filter_str,
            "-t", str(seg["duration"]),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            seg_file
        ]

        print(f"  [{i+1}/{len(segments)}] {os.path.basename(seg['image'])} "
              f"(effect {seg['effect']}, {seg['duration']:.1f}s)")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    ERROR: {result.stderr[-200:]}")
            return False

    # Create concat list
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in segment_files:
            f.write(f"file '{sf}'\n")

    print(f"\nConcatenating {len(segment_files)} segments...")

    # Concat all segments
    concat_output = os.path.join(temp_dir, "video_only.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        concat_output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Concat ERROR: {result.stderr[-300:]}")
        return False

    print("Adding audio track...")

    # Merge audio + video
    cmd = [
        "ffmpeg", "-y",
        "-i", concat_output,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Merge ERROR: {result.stderr[-300:]}")
        return False

    # Get final file size
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\nVideo assembled successfully!")
    print(f"Output: {output_path}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Duration: {duration:.1f}s ({duration/60:.1f} min)")

    # Cleanup temp segments
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("Cleaned up temp files.")

    return True


def main():
    if len(sys.argv) >= 3:
        audio_path = sys.argv[1]
        broll_dir = sys.argv[2]
        output_name = sys.argv[3] if len(sys.argv) > 3 else "output"
    else:
        # Default: RichMind Dark Psychology video
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

    success = assemble_video(audio_path, broll_dir, output_path)

    if success:
        print(f"\n{'=' * 60}")
        print("VIDEO READY TO WATCH!")
        print(f"{'=' * 60}")
    else:
        print("\nVideo assembly failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
