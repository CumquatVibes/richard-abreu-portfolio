#!/usr/bin/env python3
"""Generate B-roll and assemble video for the Overthinking script.

This script uses **(Visual: ...) format instead of [VISUAL: ...].
"""

import base64
import json
import math
import os
import re
import shutil
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = "gemini-2.0-flash-exp-image-generation"

SCRIPT_PATH = os.path.join(
    BASE_DIR, "output", "scripts",
    "RichMind_Why_You_Cant_Stop_Overthinking_The_Psychology_Behind_It_20260219_155540.txt"
)
AUDIO_PATH = os.path.join(
    BASE_DIR, "output", "audio",
    "RichMind_Why_You_Cant_Stop_Overthinking_The_Psychology_Behind_It.mp3"
)
BROLL_DIR = os.path.join(
    BASE_DIR, "output", "broll",
    "RichMind_Why_You_Cant_Stop_Overthinking_The_Psychology_Behind_It_20260219_155540"
)
VIDEO_PATH = os.path.join(
    BASE_DIR, "output", "videos",
    "RichMind_Why_You_Cant_Stop_Overthinking_The_Psychology_Behind_It.mp4"
)

os.makedirs(BROLL_DIR, exist_ok=True)


def extract_visuals():
    with open(SCRIPT_PATH) as f:
        content = f.read()
    # Match **(Visual: ...) or **(Intro music with ... Visual: ...)
    visuals = re.findall(r'\*\*\((?:.*?Visual:\s*)(.+?)\)\*\*', content)
    return visuals


def generate_image(prompt, output_path):
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

    for attempt in range(3):
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
                wait = 60 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    Error {e.code}")
                return 0
    return 0


def assemble_video():
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", AUDIO_PATH],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())

    images = sorted([
        os.path.join(BROLL_DIR, f) for f in os.listdir(BROLL_DIR)
        if f.endswith(".png") and f.startswith("broll_")
    ])

    segment_duration = 8
    temp_dir = os.path.join(os.path.dirname(VIDEO_PATH), "temp_segments")
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

        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", images[img_idx],
             "-vf", filter_str, "-t", str(seg_dur),
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-pix_fmt", "yuv420p", seg_file],
            capture_output=True, text=True
        )

    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in segment_files:
            f.write(f"file '{sf}'\n")

    concat_output = os.path.join(temp_dir, "video_only.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-c:v", "libx264", "-preset", "fast", "-crf", "22",
         "-pix_fmt", "yuv420p", concat_output],
        capture_output=True, text=True
    )

    subprocess.run(
        ["ffmpeg", "-y", "-i", concat_output, "-i", AUDIO_PATH,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", VIDEO_PATH],
        capture_output=True, text=True
    )

    shutil.rmtree(temp_dir, ignore_errors=True)

    size_mb = os.path.getsize(VIDEO_PATH) / (1024 * 1024)
    print(f"Video: {size_mb:.1f} MB, {duration/60:.1f} min")


def main():
    print("Fixing Overthinking video...\n")

    visuals = extract_visuals()
    print(f"Found {len(visuals)} visual directions\n")

    generated = 0
    for i, visual in enumerate(visuals, 1):
        filepath = os.path.join(BROLL_DIR, f"broll_{i:02d}.png")
        if os.path.exists(filepath):
            print(f"[{i}/{len(visuals)}] SKIP (exists)")
            generated += 1
            continue

        print(f"[{i}/{len(visuals)}] {visual[:60]}...")
        size_kb = generate_image(visual, filepath)
        if size_kb:
            print(f"  -> broll_{i:02d}.png ({size_kb:.0f} KB)")
            generated += 1
        else:
            print(f"  -> FAILED")

        if i < len(visuals):
            time.sleep(8)

    print(f"\nB-roll: {generated}/{len(visuals)}")

    if generated > 0:
        print("\nAssembling video...")
        assemble_video()
        print("Done!")


if __name__ == "__main__":
    main()
