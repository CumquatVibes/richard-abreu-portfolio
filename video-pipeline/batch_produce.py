#!/usr/bin/env python3
"""Batch produce all faceless YouTube videos.

For each script:
1. Generate B-roll images from [VISUAL: ...] directions (Gemini API)
2. Assemble video with Ken Burns effects + voiceover audio (ffmpeg)

Handles API rate limits with exponential backoff.
"""

import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = "gemini-2.0-flash-exp-image-generation"

SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
AUDIO_DIR = os.path.join(BASE_DIR, "output", "audio")
BROLL_DIR = os.path.join(BASE_DIR, "output", "broll")
VIDEOS_DIR = os.path.join(BASE_DIR, "output", "videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)


def extract_visuals(script_path):
    """Extract [VISUAL: ...] directions from a script."""
    with open(script_path) as f:
        content = f.read()
    return re.findall(r'\[VISUAL:\s*(.+?)\]', content)


def generate_image(prompt, output_path, retries=3):
    """Generate a single B-roll image with retry logic."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    enhanced = (
        f"Cinematic 16:9 aspect ratio, dark moody aesthetic, high contrast, "
        f"professional video B-roll shot. {prompt}. "
        f"Ultra-realistic, photographic quality, no text, no watermarks."
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": enhanced}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.8}
    }).encode()

    for attempt in range(retries):
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        img_data = base64.b64decode(part["inlineData"]["data"])
                        with open(output_path, "wb") as f:
                            f.write(img_data)
                        return len(img_data) / 1024
            return 0
        except HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                err = e.read().decode() if hasattr(e, 'read') else str(e)
                print(f"    Error {e.code}: {err[:150]}")
                return 0
        except Exception as e:
            print(f"    Error: {str(e)[:150]}")
            return 0
    return 0


def generate_broll(script_path):
    """Generate all B-roll for a script."""
    basename = os.path.splitext(os.path.basename(script_path))[0]
    broll_out = os.path.join(BROLL_DIR, basename)
    os.makedirs(broll_out, exist_ok=True)

    visuals = extract_visuals(script_path)
    if not visuals:
        print(f"  No [VISUAL:] directions found, skipping B-roll generation")
        return broll_out, 0

    generated = 0
    for i, visual in enumerate(visuals, 1):
        filepath = os.path.join(broll_out, f"broll_{i:02d}.png")
        if os.path.exists(filepath):
            generated += 1
            continue

        print(f"  [{i}/{len(visuals)}] {visual[:60]}...")
        size_kb = generate_image(visual, filepath)
        if size_kb:
            print(f"    -> broll_{i:02d}.png ({size_kb:.0f} KB)")
            generated += 1
        else:
            print(f"    -> FAILED")

        if i < len(visuals):
            time.sleep(5)  # Conservative rate limiting

    print(f"  B-roll: {generated}/{len(visuals)} images")
    return broll_out, generated


def assemble_video(audio_path, broll_dir, output_path):
    """Assemble video from B-roll + voiceover."""
    # Get audio duration
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())

    # Collect B-roll images
    images = sorted([
        os.path.join(broll_dir, f) for f in os.listdir(broll_dir)
        if f.endswith(".png") and f.startswith("broll_")
    ])

    if not images:
        print(f"  No B-roll images, skipping video assembly")
        return False

    # Build segments (8s each)
    segment_duration = 8.0
    temp_dir = os.path.join(os.path.dirname(output_path), "temp_segments")
    os.makedirs(temp_dir, exist_ok=True)

    num_segments = int(math.ceil(duration / segment_duration))
    segment_files = []
    fps = 30

    effects = {
        0: "zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        1: "zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        2: "zoompan=z='1.08':x='(iw/zoom-ow)/(FRAMES)*on':y='(ih-oh)/2'",
        3: "zoompan=z='1.08':x='(iw/zoom-ow)-((iw/zoom-ow)/(FRAMES))*on':y='(ih-oh)/2'",
        4: "zoompan=z='min(zoom+0.001,1.2)':x='0':y='0'",
        5: "zoompan=z='min(zoom+0.001,1.2)':x='iw/zoom-ow':y='ih/zoom-oh'",
    }

    for i in range(num_segments):
        start = i * segment_duration
        seg_dur = min(segment_duration, duration - start)
        if seg_dur < 1:
            break

        seg_file = os.path.join(temp_dir, f"seg_{i:04d}.mp4")
        segment_files.append(seg_file)
        if os.path.exists(seg_file):
            continue

        img_idx = i % len(images)
        effect_idx = i % 6
        total_frames = int(seg_dur * fps)

        effect_str = effects[effect_idx].replace("FRAMES", str(total_frames))
        filter_str = f"scale=2560:-1,{effect_str}:d={total_frames}:s=1920x1080:fps={fps},format=yuv420p"

        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", images[img_idx],
            "-vf", filter_str, "-t", str(seg_dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", seg_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    Segment {i} failed")
            return False

    # Concat
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in segment_files:
            f.write(f"file '{sf}'\n")

    concat_output = os.path.join(temp_dir, "video_only.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
           "-c:v", "libx264", "-preset", "fast", "-crf", "22",
           "-pix_fmt", "yuv420p", concat_output]
    subprocess.run(cmd, capture_output=True, text=True)

    # Merge audio
    cmd = ["ffmpeg", "-y", "-i", concat_output, "-i", audio_path,
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)

    if result.returncode == 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  Video: {size_mb:.1f} MB, {duration/60:.1f} min")
        return True
    return False


def find_audio_for_script(script_basename):
    """Find the matching audio file for a script (without timestamp)."""
    # Script: Channel_Title_TIMESTAMP.txt -> Audio: Channel_Title.mp3
    # Remove the timestamp suffix (last part like _20260219_155540)
    parts = script_basename.rsplit("_", 2)
    if len(parts) >= 3:
        try:
            int(parts[-1])  # Check if last part is numeric
            int(parts[-2])  # Check if second-to-last is numeric
            audio_name = "_".join(parts[:-2])
        except ValueError:
            audio_name = script_basename
    else:
        audio_name = script_basename

    audio_path = os.path.join(AUDIO_DIR, f"{audio_name}.mp3")
    if os.path.exists(audio_path):
        return audio_path
    return None


def main():
    print("=" * 60)
    print("BATCH VIDEO PRODUCTION")
    print("=" * 60)

    # Find all scripts
    scripts = sorted([
        os.path.join(SCRIPTS_DIR, f) for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".txt")
    ])

    print(f"\nFound {len(scripts)} scripts\n")

    results = {"success": [], "failed": [], "skipped": []}

    for i, script_path in enumerate(scripts, 1):
        basename = os.path.splitext(os.path.basename(script_path))[0]
        # Remove timestamp for video output name
        parts = basename.rsplit("_", 2)
        try:
            int(parts[-1])
            int(parts[-2])
            video_name = "_".join(parts[:-2])
        except (ValueError, IndexError):
            video_name = basename

        output_path = os.path.join(VIDEOS_DIR, f"{video_name}.mp4")

        print(f"\n[{i}/{len(scripts)}] {video_name}")
        print("-" * 50)

        # Check if video already exists
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  SKIP (exists): {size_mb:.1f} MB")
            results["skipped"].append(video_name)
            continue

        # Find matching audio
        audio_path = find_audio_for_script(basename)
        if not audio_path:
            print(f"  SKIP: No matching audio found")
            results["failed"].append(video_name)
            continue

        # Generate B-roll
        print(f"  Generating B-roll...")
        broll_dir, broll_count = generate_broll(script_path)

        if broll_count == 0:
            print(f"  SKIP: No B-roll generated")
            results["failed"].append(video_name)
            continue

        # Assemble video
        print(f"  Assembling video...")
        if assemble_video(audio_path, broll_dir, output_path):
            results["success"].append(video_name)
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
