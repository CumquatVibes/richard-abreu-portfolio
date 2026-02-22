#!/usr/bin/env python3
"""Overnight batch production pipeline with self-assessment.

For each script:
1. Generate B-roll images (Gemini API, with aggressive retry on 429)
2. Assemble video (ffmpeg Ken Burns + voiceover + crossfade)
3. Self-assess quality and log lessons learned
4. Upload to Google Drive

Produces a full report at the end.
"""

import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.assembly import assemble_video
from utils.broll import generate_broll, get_broll_template, extract_visuals
from utils.common import find_audio_for_script, strip_timestamp, SCRIPTS_DIR, VIDEOS_DIR, REPORT_DIR

os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

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

    # Score: Visual variety
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

    # Score: Audio quality
    audio_size_kb = video_info.get("audio_size_kb", 0)
    if audio_size_kb > 0 and video_info.get("duration", 0) > 0:
        bitrate = (audio_size_kb * 8) / video_info["duration"]
        if bitrate >= 80:
            assessment["score"] += 15
            assessment["strengths"].append(f"Good audio bitrate ({bitrate:.0f} kbps)")
        else:
            assessment["score"] += 8
            assessment["issues"].append(f"Low audio bitrate ({bitrate:.0f} kbps)")

    # Score: Video file size
    size_mb = video_info.get("size_mb", 0)
    if 30 <= size_mb <= 500:
        assessment["score"] += 15
        assessment["strengths"].append(f"Good file size ({size_mb:.1f} MB) for YouTube upload")
    elif size_mb > 0:
        assessment["score"] += 8

    if num_images < total_visuals * 0.7:
        assessment["improvements"].append("Lesson: Space out API calls more to avoid rate limits")

    return assessment


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
        channel = basename.split("_")[0]
        video_name = strip_timestamp(basename)
        output_path = os.path.join(VIDEOS_DIR, f"{video_name}.mp4")

        print(f"\n{'='*70}")
        print(f"  [{i}/{len(scripts)}] {channel}: {video_name}")
        print(f"{'='*70}")

        video_info = {
            "name": video_name,
            "channel": channel,
            "script": basename,
        }

        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  SKIP (exists): {size_mb:.1f} MB")
            video_info["status"] = "skipped"
            video_info["size_mb"] = size_mb
            report["videos"].append(video_info)
            continue

        audio_path, audio_name = find_audio_for_script(basename)
        if not audio_path:
            print(f"  SKIP: No audio found for {audio_name}")
            video_info["status"] = "no_audio"
            report["videos"].append(video_info)
            continue

        audio_size_kb = os.path.getsize(audio_path) / 1024
        video_info["audio_size_kb"] = audio_size_kb

        visuals = extract_visuals(script_path)
        video_info["total_visuals"] = len(visuals)
        print(f"  Visuals needed: {len(visuals)}")

        # Generate B-roll with overnight settings (more retries, longer backoff)
        print(f"  Generating B-roll...")
        broll_dir, generated, failed = generate_broll(
            script_path, channel=channel,
            model="gemini-2.0-flash-exp-image-generation",
            retries=5, delay_on_429=60
        )
        video_info["generated_broll"] = generated
        video_info["failed_broll"] = failed
        report["total_broll_generated"] += generated
        report["total_broll_failed"] += failed
        print(f"  B-roll result: {generated} generated, {failed} failed")

        if generated == 0:
            print(f"  SKIP: No B-roll generated")
            video_info["status"] = "no_broll"
            report["videos"].append(video_info)
            continue

        # Assemble video with channel-specific segment duration + crossfade
        print(f"  Assembling video...")
        template = get_broll_template(channel)
        seg_dur = template["segment_duration"]
        success, size_mb, duration = assemble_video(
            audio_path, broll_dir, output_path,
            segment_duration=seg_dur, crossfade=0.5
        )

        if success:
            video_info["status"] = "success"
            video_info["size_mb"] = size_mb
            video_info["duration"] = duration
            report["total_videos_assembled"] += 1
            print(f"  VIDEO COMPLETE: {size_mb:.1f} MB, {duration/60:.1f} min")

            assessment = self_assess_video(video_info)
            video_info["assessment"] = assessment
            print(f"\n  SELF-ASSESSMENT: {assessment['score']}/{assessment['max_score']}")
            for s in assessment["strengths"]:
                print(f"    + {s}")
            for issue in assessment["issues"]:
                print(f"    - {issue}")
            for imp in assessment["improvements"]:
                print(f"    > {imp}")

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

    # Save reports
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(REPORT_DIR, f"production_report_{timestamp}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    report_txt = os.path.join(REPORT_DIR, f"production_report_{timestamp}.txt")
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
