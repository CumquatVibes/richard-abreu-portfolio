#!/usr/bin/env python3
"""Generate voiceovers for all scripts via ElevenLabs TTS API."""

import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
if not API_KEY:
    print("ERROR: ELEVENLABS_API_KEY not set")
    sys.exit(1)

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "output", "scripts")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "output", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Voice profiles from channels_config.json
VOICES = {
    "neutral_male": {
        "voice_id": "cjVigY5qzO86Huf0OWal",
        "stability": 0.55,
        "similarity_boost": 0.78,
        "style": 0.2,
        "speed": 1.0,
    },
    "storyteller": {
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "stability": 0.35,
        "similarity_boost": 0.75,
        "style": 0.45,
        "speed": 0.95,
    },
    "calm_narrator": {
        "voice_id": "onwK4e9ZLuTAKqWW03F9",
        "stability": 0.65,
        "similarity_boost": 0.8,
        "style": 0.15,
        "speed": 0.95,
    },
    "friendly_casual": {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.35,
        "speed": 1.0,
    },
}

# Channel -> voice mapping
CHANNEL_VOICE = {
    "RichTech": "neutral_male",
    "RichHorror": "storyteller",
    "RichMind": "storyteller",
    "HowToUseAI": "neutral_male",
    "RichPets": "friendly_casual",
}


def clean_script_for_tts(text):
    """Remove metadata headers, visual directions, and formatting for TTS.
    PRESERVES ElevenLabs emotion audio tags like [whispers], [excited], etc."""

    # ElevenLabs v3 emotion tags to preserve
    EMOTION_TAGS = {
        "excited", "nervous", "frustrated", "sorrowful", "calm", "curious",
        "sarcastic", "mischievously", "crying", "angry", "cheerfully", "flatly",
        "deadpan", "playfully", "confident", "fearful", "disgusted", "awed",
        "tender", "sigh", "sighs", "laughs", "laughs harder", "wheezing",
        "gulps", "gasps", "exhales", "swallows", "clears throat", "pauses",
        "hesitates", "stammers", "resigned tone", "trails off", "whispers",
        "shouts", "softly", "firmly", "slowly", "urgently",
    }

    def is_emotion_tag(line_text):
        """Check if a bracket expression is an ElevenLabs emotion tag."""
        match = re.match(r'^\s*\[([^\]]+)\]\s*$', line_text)
        if match:
            return match.group(1).lower().strip() in EMOTION_TAGS
        return False

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        # Skip metadata header lines
        if line.startswith("# Channel:") or line.startswith("# Topic:") or \
           line.startswith("# Format:") or line.startswith("# Words:") or \
           line.startswith("# Est Duration:") or line.startswith("# Generated:"):
            continue
        # Skip visual directions [VISUAL: ...]
        if re.match(r'\s*\[VISUAL:.*\]', line):
            continue
        # Skip cross-promo markers
        if line.strip() == "[CROSS-PROMO]":
            continue
        # Skip section timing headers like (Intro - 0:00 - 0:30)
        if re.match(r'^\s*\(.*\d+:\d+.*\)\s*$', line):
            continue
        # Remove markdown bold
        line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        # Remove markdown italic
        line = re.sub(r'\*(.*?)\*', r'\1', line)
        # Remove "Narrator:", "NARRATOR:", "Host:", "Voiceover:", "Speaker:" prefixes
        line = re.sub(r'^(?:Narrator|NARRATOR|Host|HOST|Voiceover|VOICEOVER|Speaker|SPEAKER)\s*:\s*', '', line.strip())
        # Remove stage directions in parentheses like (Deep, resonant voice) or (Calm, direct tone)
        line = re.sub(r'\([A-Z][^)]{5,}\)', '', line)
        # Clean up any double spaces left by removals
        line = re.sub(r'  +', ' ', line).strip()
        # Skip empty bracket markers UNLESS they are emotion tags
        if line.strip().startswith("[") and line.strip().endswith("]"):
            if not is_emotion_tag(line):
                continue
        cleaned.append(line)

    text = "\n".join(cleaned)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def generate_voiceover(text, voice_profile, output_path):
    """Call ElevenLabs TTS API and save MP3."""
    voice = VOICES[voice_profile]
    voice_id = voice["voice_id"]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    payload = json.dumps({
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": voice["stability"],
            "similarity_boost": voice["similarity_boost"],
            "style": voice["style"],
            "use_speaker_boost": True,
        }
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "xi-api-key": API_KEY,
        "Accept": "audio/mpeg",
    }

    req = Request(url, data=payload, headers=headers)

    try:
        with urlopen(req, timeout=120) as resp:
            audio_data = resp.read()
            with open(output_path, "wb") as f:
                f.write(audio_data)
            size_kb = len(audio_data) / 1024
            return size_kb
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        print(f"  API Error {e.code}: {error_body[:300]}")
        return None


def main():
    # Find all script files that need voiceovers
    scripts_to_process = []

    for filename in sorted(os.listdir(SCRIPTS_DIR)):
        if not filename.endswith(".txt"):
            continue

        # Determine channel from filename
        channel = None
        for ch in CHANNEL_VOICE:
            if filename.startswith(ch):
                channel = ch
                break

        if not channel:
            continue

        # Check if audio already exists
        audio_name = os.path.splitext(filename)[0]
        # Strip timestamp from end for cleaner audio filenames
        audio_name = re.sub(r'_\d{8}_\d{6}$', '', audio_name)
        audio_path = os.path.join(AUDIO_DIR, audio_name + ".mp3")

        if os.path.exists(audio_path):
            print(f"  SKIP (exists): {audio_name}.mp3")
            continue

        scripts_to_process.append({
            "channel": channel,
            "script_file": filename,
            "audio_name": audio_name,
            "audio_path": audio_path,
            "voice_profile": CHANNEL_VOICE[channel],
        })

    print(f"Generating {len(scripts_to_process)} voiceovers via ElevenLabs...\n")

    generated = 0
    for i, item in enumerate(scripts_to_process, 1):
        print(f"[{i}/{len(scripts_to_process)}] {item['channel']}: {item['audio_name']}")
        print(f"  Voice: {item['voice_profile']} ({VOICES[item['voice_profile']]['voice_id']})")

        # Read and clean script
        script_path = os.path.join(SCRIPTS_DIR, item["script_file"])
        with open(script_path, "r") as f:
            raw_text = f.read()

        clean_text = clean_script_for_tts(raw_text)
        word_count = len(clean_text.split())
        print(f"  Script: {word_count} words (cleaned)")

        # Generate voiceover
        size_kb = generate_voiceover(clean_text, item["voice_profile"], item["audio_path"])

        if size_kb:
            print(f"  -> Saved: {item['audio_name']}.mp3 ({size_kb:.0f} KB)")
            generated += 1
        else:
            print(f"  -> FAILED")

        # Rate limit - wait between calls
        if i < len(scripts_to_process):
            time.sleep(2)

    print(f"\nDone! Generated {generated}/{len(scripts_to_process)} voiceovers.")


if __name__ == "__main__":
    main()
