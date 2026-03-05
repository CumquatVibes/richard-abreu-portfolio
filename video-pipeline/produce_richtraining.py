#!/usr/bin/env python3
"""Generate TTS audio and assemble videos for RichTraining scripts.

Uses edge-tts (free Microsoft Edge TTS) since ElevenLabs quota is exhausted.
Reads 3 existing scripts, generates voiceover audio, then assembles MP4
videos with Ken Burns B-roll effects.
"""

import asyncio
import os
import sys
import re
from pathlib import Path
from datetime import datetime

import edge_tts

# Add pipeline dir to path
PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from faceless_pipeline import _clean_script_for_tts
from utils.assembly import assemble_video

OUTPUT_DIR = PIPELINE_DIR / "output"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"
BROLL_DIR = OUTPUT_DIR / "broll"
VIDEOS_DIR = OUTPUT_DIR / "videos"

for d in [AUDIO_DIR, VIDEOS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Professional male voice — calm, clear narrator style
VOICE = "en-US-GuyNeural"
RATE = "-5%"  # Slightly slower for training content

# RichTraining scripts
SCRIPTS = [
    "RichTraining_7_Toxic_Workplace_Habits_Killing_Your_Productivity_And_How_to_Fix_Them_20260304_153003.txt",
    "RichTraining_Future-Proof_Your_Career_Top_5_Professional_Certifications_to_Dominate_2026_20260304_153003.txt",
    "RichTraining_Leadership_Skills_Masterclass_The_Unconventional_Guide_to_Inspiring_Your_Team_20260304_153003.txt",
]


def get_broll_dir(script_name):
    """Find the B-roll directory matching a script name."""
    base = script_name.replace(".txt", "")
    broll_path = BROLL_DIR / base
    if broll_path.exists():
        return broll_path
    prefix = base[:60]
    for d in BROLL_DIR.iterdir():
        if d.is_dir() and d.name.startswith(prefix):
            return d
    return None


def strip_script_for_tts(text):
    """Remove non-spoken content from script for TTS. Delegates to shared cleaner."""
    return _clean_script_for_tts(text)


async def generate_tts(text, output_path):
    """Generate TTS audio using edge-tts."""
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(str(output_path))
    size_kb = output_path.stat().st_size / 1024
    print(f"  Audio saved: {output_path.name} ({size_kb:.0f} KB)")
    return output_path


async def main():
    results = []

    for script_file in SCRIPTS:
        script_path = SCRIPTS_DIR / script_file
        if not script_path.exists():
            print(f"\nSKIP: {script_file} not found")
            continue

        short_name = script_file.split("_20260304")[0]
        print(f"\n{'='*60}")
        print(f"Processing: {short_name}")
        print(f"{'='*60}")

        # Read and clean script
        raw_text = script_path.read_text()
        clean_text = strip_script_for_tts(raw_text)
        print(f"  Script: {len(raw_text)} chars raw, {len(clean_text)} chars for TTS")

        # Find B-roll directory
        broll_dir = get_broll_dir(script_file)
        if not broll_dir:
            print(f"  SKIP: No B-roll directory found")
            continue
        broll_count = len([f for f in broll_dir.iterdir()
                          if f.name.startswith("broll_") and f.suffix == ".png"])
        print(f"  B-roll: {broll_count} images in {broll_dir.name}")

        # Generate TTS audio
        print(f"\n  --- TTS Generation (edge-tts, {VOICE}) ---")
        output_name = short_name.replace("RichTraining_", "")
        safe_name = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')[:60]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = AUDIO_DIR / f"RichTraining_{safe_name}_{timestamp}.mp3"

        try:
            await generate_tts(clean_text, audio_path)
        except Exception as exc:
            print(f"  FAILED: TTS generation failed: {exc}")
            results.append((short_name, False, f"TTS failed: {exc}"))
            continue

        # Assemble video
        print(f"\n  --- Video Assembly ---")
        video_name = f"RichTraining_{safe_name}_{timestamp}.mp4"
        video_path = VIDEOS_DIR / video_name

        success, size_mb, duration = assemble_video(
            str(audio_path), str(broll_dir), str(video_path),
            segment_duration=8, crossfade=0.5, verbose=True
        )

        if success:
            print(f"\n  SUCCESS: {video_name}")
            print(f"  Size: {size_mb:.1f} MB, Duration: {duration/60:.1f} min")
            results.append((short_name, True, f"{size_mb:.1f} MB, {duration/60:.1f} min"))
        else:
            print(f"\n  FAILED: Video assembly failed")
            results.append((short_name, False, "Assembly failed"))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, success, detail in results:
        status = "OK" if success else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    succeeded = sum(1 for _, s, _ in results if s)
    print(f"\n  {succeeded}/{len(results)} videos produced")


if __name__ == "__main__":
    asyncio.run(main())
