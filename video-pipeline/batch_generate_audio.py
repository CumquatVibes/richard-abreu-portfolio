#!/usr/bin/env python3
"""Batch generate voiceovers for all scripts via ElevenLabs API."""

import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
AUDIO_DIR = os.path.join(BASE_DIR, "output", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")


def load_config():
    with open(os.path.join(BASE_DIR, "channels_config.json")) as f:
        return json.load(f)


def get_channel_for_script(filename, channels):
    """Determine which channel a script belongs to based on filename prefix."""
    prefix_map = {
        "RichFinance": "rich_finance",
        "RichScience": "rich_science",
        "RichCrypto": "rich_crypto",
        "RichReviews": "rich_reviews",
        "RichSports": "rich_sports",
        "RichMovie": "rich_movie",
        "RichBusiness": "rich_business",
        "RichGaming": "rich_gaming",
        "CumquatGaming": "cumquat_gaming",
        "HowToMeditate": "how_to_meditate",
        "RichMemes": "rich_memes",
        "RichComedy": "rich_comedy",
        "CumquatShortform": "cumquat_shortform",
        "RichNature": "rich_nature",
        "CumquatMotivation": "cumquat_motivation",
        "RichAnimation": "rich_animation",
        "RichFashion": "rich_fashion",
        "RichFamily": "rich_family",
        "RichBeauty": "rich_beauty",
        "RichCooking": "rich_cooking",
        "RichEducation": "rich_education",
        "RichHistory": "rich_history",
        "RichTravel": "rich_travel",
        "RichVlogging": "rich_vlogging",
        "RichKids": "rich_kids",
        "RichFitness": "rich_fitness",
        "RichCars": "rich_cars",
        "RichLifestyle": "rich_lifestyle",
        "RichPhotography": "rich_photography",
        "RichFood": "rich_food",
        "RichDesign": "rich_design",
        "RichDiy": "rich_diy",
        "RichDance": "rich_dance",
        "RichTech": "rich_tech",
        "RichPets": "rich_pets",
        "RichHorror": "rich_horror",
        "RichMind": "rich_mind",
        "RichMusic": "rich_music",
        "HowToUseAI": "how_to_use_ai",
        "EvaReyes": "eva_reyes",
    }
    for prefix, ch_key in prefix_map.items():
        if filename.startswith(prefix):
            return ch_key
    return None


def clean_script_for_tts(text):
    """Clean script text for TTS - remove visual directions, headers, metadata."""
    # Remove YAML frontmatter
    text = re.sub(r'^---.*?---', '', text, flags=re.DOTALL)
    # Remove [VISUAL: ...] directions
    text = re.sub(r'\[VISUAL:.*?\]', '', text)
    # Remove markdown headers but keep text
    text = re.sub(r'^##\s*', '', text, flags=re.MULTILINE)
    # Remove markdown bold/italic
    text = re.sub(r'\*{1,2}(.+?)\*{1,2}', r'\1', text)
    # Remove timestamps like (0:00-0:30)
    text = re.sub(r'\(\d+:\d+[-–]\d+:\d+\)', '', text)
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def get_audio_name(script_filename):
    """Get the audio filename from a script filename (remove timestamp)."""
    basename = os.path.splitext(script_filename)[0]
    # Remove timestamp suffix like _20260221_193640
    parts = basename.rsplit("_", 2)
    if len(parts) >= 3:
        try:
            int(parts[-1])
            int(parts[-2])
            return "_".join(parts[:-2])
        except ValueError:
            pass
    return basename


def generate_voiceover(text, voice_id, voice_settings, output_path):
    """Generate voiceover via ElevenLabs API."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    # Chunk if too long (max ~5000 chars per request)
    MAX_CHARS = 4500
    if len(text) <= MAX_CHARS:
        chunks = [text]
    else:
        # Split on paragraph boundaries
        paragraphs = text.split('\n\n')
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 > MAX_CHARS:
                if current:
                    chunks.append(current)
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current:
            chunks.append(current)

    all_audio = b""
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"    Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")

        payload = json.dumps({
            "text": chunk,
            "model_id": voice_settings.get("model", "eleven_multilingual_v2"),
            "voice_settings": {
                "stability": voice_settings.get("stability", 0.5),
                "similarity_boost": voice_settings.get("similarity_boost", 0.75),
                "style": voice_settings.get("style", 0.2),
                "use_speaker_boost": True
            }
        }).encode()

        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        req = Request(url, data=payload, headers=headers)
        try:
            with urlopen(req, timeout=120) as resp:
                all_audio += resp.read()
        except HTTPError as e:
            err = e.read().decode() if hasattr(e, 'read') else str(e)
            print(f"    ElevenLabs Error {e.code}: {err[:200]}")
            return 0
        except Exception as e:
            print(f"    Error: {str(e)[:200]}")
            return 0

        if i < len(chunks) - 1:
            time.sleep(1)

    if all_audio:
        with open(output_path, "wb") as f:
            f.write(all_audio)
        return len(all_audio) / (1024 * 1024)
    return 0


def main():
    if not ELEVENLABS_API_KEY:
        print("[ERROR] ELEVENLABS_API_KEY not set")
        sys.exit(1)

    config = load_config()
    channels = config.get("channels", {})
    voice_profiles = config.get("voice_profiles", {})

    # Get all script files
    all_scripts = sorted([f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".txt")])

    # Filter to specific channels if args provided
    if len(sys.argv) > 1:
        filter_prefixes = sys.argv[1:]
        all_scripts = [f for f in all_scripts if any(f.startswith(p) for p in filter_prefixes)]

    # Find scripts without audio
    scripts_needing_audio = []
    for script_file in all_scripts:
        audio_name = get_audio_name(script_file)
        audio_path = os.path.join(AUDIO_DIR, f"{audio_name}.mp3")
        if not os.path.exists(audio_path):
            scripts_needing_audio.append(script_file)

    print("=" * 64)
    print(f"  BATCH VOICEOVER GENERATION — {len(scripts_needing_audio)} scripts")
    print("=" * 64)

    if not scripts_needing_audio:
        print("\nAll scripts already have audio. Nothing to do.")
        return

    generated = 0
    failed = []

    for idx, script_file in enumerate(scripts_needing_audio, 1):
        audio_name = get_audio_name(script_file)
        audio_path = os.path.join(AUDIO_DIR, f"{audio_name}.mp3")

        # Determine channel and voice
        ch_key = get_channel_for_script(script_file, channels)
        if not ch_key or ch_key not in channels:
            print(f"\n[{idx}/{len(scripts_needing_audio)}] SKIP: Unknown channel for {script_file[:50]}")
            continue

        ch = channels[ch_key]
        profile_name = ch.get("voice_profile", "neutral_male")
        voice_profile = voice_profiles.get(profile_name, voice_profiles.get("neutral_male", {}))
        voice_id = voice_profile.get("voice_id", "cjVigY5qzO86Huf0OWal")

        print(f"\n[{idx}/{len(scripts_needing_audio)}] {audio_name[:60]}")
        print(f"  Channel: {ch.get('name', ch_key)} | Voice: {profile_name} ({voice_id[:10]}...)")

        # Read and clean script
        script_path = os.path.join(SCRIPTS_DIR, script_file)
        with open(script_path) as f:
            raw_text = f.read()
        clean_text = clean_script_for_tts(raw_text)

        if len(clean_text) < 100:
            print(f"  SKIP: Script too short ({len(clean_text)} chars)")
            continue

        print(f"  Text: {len(clean_text)} chars ({len(clean_text.split())} words)")

        size_mb = generate_voiceover(clean_text, voice_id, voice_profile, audio_path)
        if size_mb:
            print(f"  -> {audio_name}.mp3 ({size_mb:.1f} MB)")
            generated += 1
        else:
            print(f"  -> FAILED")
            failed.append(audio_name)

        time.sleep(1)  # Rate limit

    print(f"\n{'=' * 64}")
    print(f"  BATCH COMPLETE")
    print(f"  Generated: {generated}/{len(scripts_needing_audio)}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for f_name in failed:
            print(f"    x {f_name}")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
