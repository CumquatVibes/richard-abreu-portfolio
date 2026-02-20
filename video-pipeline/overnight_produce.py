#!/usr/bin/env python3
"""Overnight batch production pipeline with self-assessment.

For each of the 15 scripts:
1. Generate B-roll images (Gemini API, with aggressive retry on 429)
2. Assemble video (ffmpeg Ken Burns + voiceover)
3. Self-assess quality and log lessons learned
4. Upload to Google Drive

Produces a full report at the end.
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
import urllib.parse
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = "gemini-2.0-flash-exp-image-generation"

SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
AUDIO_DIR = os.path.join(BASE_DIR, "output", "audio")
BROLL_DIR = os.path.join(BASE_DIR, "output", "broll")
VIDEOS_DIR = os.path.join(BASE_DIR, "output", "videos")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# Rate limit tracking
last_api_call = 0
MIN_DELAY = 8  # seconds between Gemini API calls
BACKOFF_429 = 60  # seconds to wait after rate limit

# Production report
report = {
    "start_time": datetime.now().isoformat(),
    "videos": [],
    "total_broll_generated": 0,
    "total_broll_failed": 0,
    "total_videos_assembled": 0,
    "lessons_learned": [],
    "api_rate_limits_hit": 0,
}


def rate_limited_delay():
    """Ensure minimum delay between API calls."""
    global last_api_call
    elapsed = time.time() - last_api_call
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)
    last_api_call = time.time()


def extract_visuals(script_path):
    """Extract [VISUAL: ...] directions from a script."""
    with open(script_path) as f:
        content = f.read()
    return re.findall(r'\[VISUAL:\s*(.+?)\]', content)


def get_channel_template(channel):
    """Get template config for a channel."""
    templates = {
        "RichMind": {
            "broll_prefix": "Cinematic 16:9 aspect ratio, dark moody aesthetic, high contrast, professional video B-roll shot.",
            "broll_suffix": "Ultra-realistic, photographic quality, no text, no watermarks.",
            "segment_duration": 8,
        },
        "RichHorror": {
            "broll_prefix": "Cinematic 16:9, horror atmosphere, desaturated colors, deep shadows, eerie lighting.",
            "broll_suffix": "Photorealistic, unsettling, no text, no gore, psychological horror aesthetic.",
            "segment_duration": 6,
        },
        "RichTech": {
            "broll_prefix": "Clean modern 16:9, tech aesthetic, neon accents, sleek minimalist design.",
            "broll_suffix": "Professional product photography style, sharp focus, no text, no watermarks.",
            "segment_duration": 7,
        },
        "HowToUseAI": {
            "broll_prefix": "Clean modern 16:9, tech aesthetic, digital workflow visualization.",
            "broll_suffix": "Professional, sharp focus, no text, no watermarks.",
            "segment_duration": 7,
        },
        "RichPets": {
            "broll_prefix": "Warm natural 16:9, soft lighting, friendly atmosphere, professional pet photography.",
            "broll_suffix": "Photorealistic, heartwarming, cute, no text, no watermarks.",
            "segment_duration": 8,
        },
    }
    return templates.get(channel, templates["RichMind"])


def generate_image(prompt, output_path, channel="RichMind"):
    """Generate a single B-roll image with retry logic."""
    global last_api_call
    template = get_channel_template(channel)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
    enhanced = f"{template['broll_prefix']} {prompt}. {template['broll_suffix']}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": enhanced}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.8}
    }).encode()

    max_retries = 5
    for attempt in range(max_retries):
        rate_limited_delay()
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
                report["api_rate_limits_hit"] += 1
                wait = BACKOFF_429 * (attempt + 1)
                print(f"      Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            else:
                err = e.read().decode() if hasattr(e, 'read') else str(e)
                print(f"      Error {e.code}: {err[:120]}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    return 0
        except Exception as e:
            print(f"      Error: {str(e)[:120]}")
            return 0
    return 0


def generate_broll(script_path, channel):
    """Generate all B-roll for a script."""
    basename = os.path.splitext(os.path.basename(script_path))[0]
    broll_out = os.path.join(BROLL_DIR, basename)
    os.makedirs(broll_out, exist_ok=True)

    visuals = extract_visuals(script_path)
    if not visuals:
        print(f"    No [VISUAL:] directions found")
        return broll_out, 0, 0

    generated = 0
    failed = 0
    for i, visual in enumerate(visuals, 1):
        filepath = os.path.join(broll_out, f"broll_{i:02d}.png")
        if os.path.exists(filepath):
            generated += 1
            continue

        print(f"    [{i}/{len(visuals)}] {visual[:55]}...")
        size_kb = generate_image(visual, filepath, channel)
        if size_kb:
            print(f"      -> broll_{i:02d}.png ({size_kb:.0f} KB)")
            generated += 1
            report["total_broll_generated"] += 1
        else:
            print(f"      -> FAILED")
            failed += 1
            report["total_broll_failed"] += 1

    return broll_out, generated, failed


def get_audio_duration(audio_path):
    """Get audio duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def assemble_video(audio_path, broll_dir, output_path, segment_duration=8):
    """Assemble video from B-roll + voiceover."""
    duration = get_audio_duration(audio_path)

    images = sorted([
        os.path.join(broll_dir, f) for f in os.listdir(broll_dir)
        if f.endswith(".png") and f.startswith("broll_")
    ])

    if not images:
        return False, 0, 0

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
            return False, 0, 0

    # Concat
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

    # Merge audio
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", concat_output, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", output_path],
        capture_output=True, text=True
    )

    shutil.rmtree(temp_dir, ignore_errors=True)

    if result.returncode == 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        return True, size_mb, duration
    return False, 0, 0


def self_assess_video(video_info):
    """Self-assess a produced video and generate quality report."""
    assessment = {
        "video": video_info["name"],
        "channel": video_info["channel"],
        "score": 0,
        "max_score": 100,
        "issues": [],
        "strengths": [],
        "improvements": [],
    }

    # Score: B-roll coverage
    total_visuals = video_info.get("total_visuals", 0)
    generated_broll = video_info.get("generated_broll", 0)
    if total_visuals > 0:
        coverage = generated_broll / total_visuals
        if coverage >= 0.9:
            assessment["score"] += 25
            assessment["strengths"].append(f"Excellent B-roll coverage ({generated_broll}/{total_visuals})")
        elif coverage >= 0.6:
            assessment["score"] += 15
            assessment["issues"].append(f"Partial B-roll coverage ({generated_broll}/{total_visuals})")
            assessment["improvements"].append("Generate missing B-roll images to reduce visual repetition")
        else:
            assessment["score"] += 5
            assessment["issues"].append(f"Low B-roll coverage ({generated_broll}/{total_visuals})")
            assessment["improvements"].append("Critical: Need more B-roll — images cycle too frequently")

    # Score: Duration
    duration_min = video_info.get("duration", 0) / 60
    if 8 <= duration_min <= 15:
        assessment["score"] += 25
        assessment["strengths"].append(f"Optimal duration ({duration_min:.1f} min) for algorithm")
    elif 5 <= duration_min < 8:
        assessment["score"] += 15
        assessment["issues"].append(f"Slightly short ({duration_min:.1f} min)")
        assessment["improvements"].append("Ideal faceless video length is 8-12 min for ad mid-rolls")
    elif duration_min > 15:
        assessment["score"] += 15
        assessment["issues"].append(f"Long video ({duration_min:.1f} min) — retention may drop")
    else:
        assessment["score"] += 5
        assessment["issues"].append(f"Very short ({duration_min:.1f} min)")

    # Score: Visual variety (images vs segments)
    num_images = video_info.get("generated_broll", 0)
    if num_images >= 8:
        assessment["score"] += 20
        assessment["strengths"].append(f"{num_images} unique B-roll images — good visual variety")
    elif num_images >= 5:
        assessment["score"] += 12
        assessment["issues"].append(f"Only {num_images} B-roll images — some visual repetition")
        assessment["improvements"].append("Generate more B-roll or add text overlay variants")
    else:
        assessment["score"] += 5
        assessment["issues"].append(f"Only {num_images} B-roll images — heavy repetition")
        assessment["improvements"].append("Priority: Add more visual variety — text overlays, zoom variants")

    # Score: Audio quality (file size relative to duration = bitrate)
    audio_size_kb = video_info.get("audio_size_kb", 0)
    if audio_size_kb > 0 and video_info.get("duration", 0) > 0:
        bitrate = (audio_size_kb * 8) / video_info["duration"]  # kbps
        if bitrate >= 80:
            assessment["score"] += 15
            assessment["strengths"].append(f"Good audio bitrate ({bitrate:.0f} kbps)")
        else:
            assessment["score"] += 8
            assessment["issues"].append(f"Low audio bitrate ({bitrate:.0f} kbps)")

    # Score: Video file size (reasonable for YouTube)
    size_mb = video_info.get("size_mb", 0)
    if 30 <= size_mb <= 500:
        assessment["score"] += 15
        assessment["strengths"].append(f"Good file size ({size_mb:.1f} MB) for YouTube upload")
    elif size_mb > 0:
        assessment["score"] += 8

    # Lessons learned from this video
    if num_images < total_visuals * 0.7:
        assessment["improvements"].append("Lesson: Space out API calls more (increase MIN_DELAY) to avoid rate limits")

    return assessment


def find_audio_for_script(script_basename):
    """Find matching audio file."""
    parts = script_basename.rsplit("_", 2)
    if len(parts) >= 3:
        try:
            int(parts[-1])
            int(parts[-2])
            audio_name = "_".join(parts[:-2])
        except ValueError:
            audio_name = script_basename
    else:
        audio_name = script_basename

    audio_path = os.path.join(AUDIO_DIR, f"{audio_name}.mp3")
    if os.path.exists(audio_path):
        return audio_path, audio_name
    return None, audio_name


def main():
    print("=" * 70)
    print("  OVERNIGHT PRODUCTION PIPELINE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    scripts = sorted([
        os.path.join(SCRIPTS_DIR, f) for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".txt")
    ])

    print(f"\n  {len(scripts)} scripts to process\n")

    for i, script_path in enumerate(scripts, 1):
        basename = os.path.splitext(os.path.basename(script_path))[0]

        # Determine channel
        channel = basename.split("_")[0]

        # Clean video name (no timestamp)
        parts = basename.rsplit("_", 2)
        try:
            int(parts[-1])
            int(parts[-2])
            video_name = "_".join(parts[:-2])
        except (ValueError, IndexError):
            video_name = basename

        output_path = os.path.join(VIDEOS_DIR, f"{video_name}.mp4")

        print(f"\n{'='*70}")
        print(f"  [{i}/{len(scripts)}] {channel}: {video_name}")
        print(f"{'='*70}")

        video_info = {
            "name": video_name,
            "channel": channel,
            "script": basename,
        }

        # Check if video already exists
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  SKIP (exists): {size_mb:.1f} MB")
            video_info["status"] = "skipped"
            video_info["size_mb"] = size_mb
            report["videos"].append(video_info)
            continue

        # Find audio
        audio_path, audio_name = find_audio_for_script(basename)
        if not audio_path:
            print(f"  SKIP: No audio found for {audio_name}")
            video_info["status"] = "no_audio"
            report["videos"].append(video_info)
            continue

        audio_size_kb = os.path.getsize(audio_path) / 1024
        video_info["audio_size_kb"] = audio_size_kb

        # Count total visuals needed
        visuals = extract_visuals(script_path)
        video_info["total_visuals"] = len(visuals)
        print(f"  Visuals needed: {len(visuals)}")

        # Generate B-roll
        print(f"  Generating B-roll...")
        template = get_channel_template(channel)
        broll_dir, generated, failed = generate_broll(script_path, channel)
        video_info["generated_broll"] = generated
        video_info["failed_broll"] = failed
        print(f"  B-roll result: {generated} generated, {failed} failed")

        if generated == 0:
            print(f"  SKIP: No B-roll generated")
            video_info["status"] = "no_broll"
            report["videos"].append(video_info)
            continue

        # Assemble video
        print(f"  Assembling video...")
        seg_dur = template["segment_duration"]
        success, size_mb, duration = assemble_video(audio_path, broll_dir, output_path, seg_dur)

        if success:
            video_info["status"] = "success"
            video_info["size_mb"] = size_mb
            video_info["duration"] = duration
            report["total_videos_assembled"] += 1
            print(f"  VIDEO COMPLETE: {size_mb:.1f} MB, {duration/60:.1f} min")

            # Self-assess
            assessment = self_assess_video(video_info)
            video_info["assessment"] = assessment
            print(f"\n  SELF-ASSESSMENT: {assessment['score']}/{assessment['max_score']}")
            for s in assessment["strengths"]:
                print(f"    + {s}")
            for issue in assessment["issues"]:
                print(f"    - {issue}")
            for imp in assessment["improvements"]:
                print(f"    > {imp}")

            # Accumulate lessons
            for imp in assessment["improvements"]:
                if imp not in report["lessons_learned"]:
                    report["lessons_learned"].append(imp)
        else:
            video_info["status"] = "assembly_failed"
            print(f"  FAILED: Video assembly error")

        report["videos"].append(video_info)

    # Final report
    report["end_time"] = datetime.now().isoformat()

    print(f"\n\n{'='*70}")
    print("  PRODUCTION REPORT")
    print(f"{'='*70}")
    print(f"  Started:  {report['start_time']}")
    print(f"  Finished: {report['end_time']}")
    print(f"\n  Videos assembled: {report['total_videos_assembled']}")
    print(f"  B-roll generated: {report['total_broll_generated']}")
    print(f"  B-roll failed:    {report['total_broll_failed']}")
    print(f"  Rate limits hit:  {report['api_rate_limits_hit']}")

    print(f"\n  {'─'*50}")
    print(f"  VIDEO STATUS:")
    for v in report["videos"]:
        status = v.get("status", "unknown")
        size = f"{v.get('size_mb', 0):.1f}MB" if v.get("size_mb") else "N/A"
        score = v.get("assessment", {}).get("score", "N/A")
        print(f"    [{status:>12}] {v['channel']}/{v['name'][:40]} ({size}, score: {score})")

    if report["lessons_learned"]:
        print(f"\n  {'─'*50}")
        print(f"  LESSONS LEARNED:")
        for lesson in report["lessons_learned"]:
            print(f"    > {lesson}")

    # Save report to file
    report_path = os.path.join(REPORT_DIR, f"production_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Also save human-readable version
    report_txt = os.path.join(REPORT_DIR, f"production_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(report_txt, "w") as f:
        f.write("OVERNIGHT PRODUCTION REPORT\n")
        f.write(f"{'='*60}\n")
        f.write(f"Started:  {report['start_time']}\n")
        f.write(f"Finished: {report['end_time']}\n\n")
        f.write(f"Videos assembled: {report['total_videos_assembled']}\n")
        f.write(f"B-roll generated: {report['total_broll_generated']}\n")
        f.write(f"B-roll failed:    {report['total_broll_failed']}\n")
        f.write(f"Rate limits hit:  {report['api_rate_limits_hit']}\n\n")

        f.write("VIDEO DETAILS:\n")
        f.write(f"{'─'*60}\n")
        for v in report["videos"]:
            status = v.get("status", "unknown")
            f.write(f"\n{v['channel']}: {v['name']}\n")
            f.write(f"  Status: {status}\n")
            if v.get("size_mb"):
                f.write(f"  Size: {v['size_mb']:.1f} MB\n")
            if v.get("duration"):
                f.write(f"  Duration: {v['duration']/60:.1f} min\n")
            if v.get("total_visuals"):
                f.write(f"  Visuals: {v.get('generated_broll', 0)}/{v['total_visuals']}\n")
            assessment = v.get("assessment", {})
            if assessment:
                f.write(f"  Quality Score: {assessment.get('score', 'N/A')}/{assessment.get('max_score', 100)}\n")
                for s in assessment.get("strengths", []):
                    f.write(f"    + {s}\n")
                for issue in assessment.get("issues", []):
                    f.write(f"    - {issue}\n")
                for imp in assessment.get("improvements", []):
                    f.write(f"    > {imp}\n")

        if report["lessons_learned"]:
            f.write(f"\n\nLESSONS LEARNED:\n")
            f.write(f"{'─'*60}\n")
            for lesson in report["lessons_learned"]:
                f.write(f"  > {lesson}\n")

    print(f"\n  Report saved: {report_path}")
    print(f"  Report saved: {report_txt}")
    print(f"\n{'='*70}")
    print("  PRODUCTION COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
