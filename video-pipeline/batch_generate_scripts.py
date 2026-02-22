#!/usr/bin/env python3
"""Batch generate scripts for all remaining YouTube channels via Gemini API."""

import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)

DONE_CHANNELS = {
    "rich_tech", "rich_pets", "rich_horror", "rich_mind",
    "how_to_use_ai", "rich_music", "eva_reyes", "cumquat_vibes"
}

SCRIPTS_PER_CHANNEL = 3


def load_config():
    with open(os.path.join(BASE_DIR, "channels_config.json")) as f:
        return json.load(f)


def gemini_call(prompt, model="gemini-2.0-flash", retries=3):
    """Call Gemini API with retries."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 4096}
    }).encode()

    for attempt in range(retries):
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except HTTPError as e:
            if e.code == 429:
                wait = 15 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                err = e.read().decode() if hasattr(e, 'read') else str(e)
                print(f"    API Error {e.code}: {err[:200]}")
                if attempt == retries - 1:
                    return None
                time.sleep(5)
        except Exception as e:
            print(f"    Error: {str(e)[:200]}")
            if attempt == retries - 1:
                return None
            time.sleep(5)
    return None


def generate_topics(channel_key, channel_config, count=3):
    """Generate video topic ideas for a channel."""
    niche = channel_config.get("niche", "general")
    sub_topics = channel_config.get("sub_topics", [])
    formats = channel_config.get("formats", ["listicle"])
    name = channel_config.get("name", channel_key)

    prompt = f"""Generate exactly {count} YouTube video topics for '{name}', a faceless {niche} channel.

Sub-topics: {', '.join(sub_topics[:6])}
Preferred formats: {', '.join(formats[:3])}

Requirements:
- Specific, clickable video titles optimized for YouTube search
- Mix evergreen + trending topics for February 2026
- Use numbers when relevant (Top 7, 5 Best, etc.)
- Curiosity-driven but not misleading clickbait
- Each title should stand alone as a compelling video

Return ONLY the titles, one per line, no numbering, no bullets, no quotes."""

    text = gemini_call(prompt)
    if not text:
        return []
    topics = [line.strip().strip("-").strip("•").strip('"').strip()
              for line in text.strip().split("\n")
              if line.strip() and not line.strip().startswith("#") and len(line.strip()) > 10]
    return topics[:count]


def generate_script(channel_key, channel_config, topic, config):
    """Generate a full video script for a topic."""
    niche = channel_config.get("niche", "general")
    name = channel_config.get("name", channel_key)
    sub_topics = channel_config.get("sub_topics", [])
    formats = channel_config.get("formats", ["listicle"])
    format_name = formats[0] if formats else "listicle"

    # Get format config
    fmt = config.get("content_formats", {}).get(format_name, {})
    word_count = fmt.get("word_count", 1200)
    structure = fmt.get("structure", "hook → numbered items → recap → CTA")

    prompt = f"""Write a complete YouTube video script for the channel '{name}' ({niche}).

TITLE: {topic}

FORMAT: {format_name}
STRUCTURE: {structure}
TARGET WORD COUNT: {word_count} words
TARGET DURATION: {fmt.get('duration_target', '8-12 min')}

SCRIPT REQUIREMENTS:
1. START with a powerful hook in the FIRST 10 seconds — a shocking stat, provocative question, or bold claim that makes viewers stay
2. Use conversational, engaging narration style (faceless voiceover)
3. Include [VISUAL: description] directions for B-roll throughout
4. End with a clear CTA (subscribe, like, comment prompt)
5. Include chapter markers as ## headers
6. Do NOT use filler phrases like "without further ado" or "in today's video"
7. Be factual and well-researched — include specific data points
8. The first 30 seconds must be the most compelling part of the entire script
9. Each section should have 2-3 [VISUAL:] directions

OUTPUT FORMAT:
---
title: {topic}
channel: {name}
format: {format_name}
---

## Hook (0:00-0:30)
[script text with [VISUAL: directions]]

## Chapter 1: [Title]
[script text]

... continue for all chapters ...

## Outro
[CTA and closing]"""

    return gemini_call(prompt)


def sanitize_filename(text, max_len=80):
    """Create a safe filename from text."""
    clean = re.sub(r'[^\w\s-]', '', text)
    clean = re.sub(r'\s+', '_', clean.strip())
    return clean[:max_len]


def main():
    if not API_KEY:
        print("[ERROR] GEMINI_API_KEY not set")
        sys.exit(1)

    config = load_config()
    channels = config.get("channels", {})

    # Determine which channels to process
    if len(sys.argv) > 1:
        target_channels = sys.argv[1:]
    else:
        # All remaining faceless channels
        target_channels = [
            k for k in channels
            if k not in DONE_CHANNELS and channels[k].get("faceless", False)
        ]

    # Priority ordering
    priority = ["rich_finance", "rich_science"]
    secondary = ["rich_crypto", "rich_reviews", "rich_sports", "rich_movie",
                  "rich_business", "rich_gaming", "cumquat_gaming", "how_to_meditate"]
    growth = ["rich_memes", "rich_comedy", "cumquat_shortform", "rich_nature",
              "cumquat_motivation"]

    ordered = []
    for ch in priority + secondary + growth:
        if ch in target_channels:
            ordered.append(ch)
            target_channels.remove(ch)
    ordered.extend(target_channels)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_scripts = 0
    failed_channels = []

    print("=" * 64)
    print(f"  BATCH SCRIPT GENERATION — {len(ordered)} channels x {SCRIPTS_PER_CHANNEL} scripts")
    print(f"  Timestamp: {timestamp}")
    print("=" * 64)

    for idx, ch_key in enumerate(ordered, 1):
        ch = channels.get(ch_key)
        if not ch:
            print(f"\n[{idx}/{len(ordered)}] SKIP: {ch_key} not found in config")
            continue

        ch_name = ch.get("name", ch_key)
        # Check channel prefix for filename
        prefix_map = {
            "cumquat_": "Cumquat", "rich_": "Rich", "how_to_": "HowTo",
            "eva_": "Eva"
        }
        prefix = ch_key
        for pfx, replacement in prefix_map.items():
            if ch_key.startswith(pfx):
                rest = ch_key[len(pfx):]
                prefix = replacement + rest.capitalize()
                break

        print(f"\n[{idx}/{len(ordered)}] {ch_name} ({ch_key})")
        print("-" * 50)

        # Check if scripts already exist
        existing = [f for f in os.listdir(SCRIPTS_DIR)
                    if f.startswith(prefix) and f.endswith(".txt")]
        if len(existing) >= SCRIPTS_PER_CHANNEL:
            print(f"  SKIP: Already has {len(existing)} scripts")
            total_scripts += len(existing)
            continue

        # Generate topics
        print(f"  Generating {SCRIPTS_PER_CHANNEL} topics...")
        topics = generate_topics(ch_key, ch, SCRIPTS_PER_CHANNEL)
        if not topics:
            print(f"  FAILED: Could not generate topics")
            failed_channels.append(ch_key)
            continue

        for i, topic in enumerate(topics):
            print(f"  Topic {i+1}: {topic}")

        time.sleep(1)

        # Generate scripts for each topic
        for i, topic in enumerate(topics):
            safe_title = sanitize_filename(topic)
            filename = f"{prefix}_{safe_title}_{timestamp}.txt"
            filepath = os.path.join(SCRIPTS_DIR, filename)

            # Check if similar script exists
            if any(safe_title[:30] in f for f in os.listdir(SCRIPTS_DIR)):
                print(f"  [{i+1}/{len(topics)}] SKIP (similar exists): {topic[:60]}")
                total_scripts += 1
                continue

            print(f"  [{i+1}/{len(topics)}] Generating script: {topic[:60]}...")
            script = generate_script(ch_key, ch, topic, config)

            if script and len(script) > 200:
                with open(filepath, "w") as f:
                    f.write(script)
                word_count = len(script.split())
                print(f"    -> {filename[:70]}... ({word_count} words)")
                total_scripts += 1
            else:
                print(f"    -> FAILED")
                failed_channels.append(f"{ch_key}:{topic[:30]}")

            time.sleep(2)  # Rate limit between scripts

        time.sleep(1)  # Rate limit between channels

    print(f"\n{'=' * 64}")
    print(f"  BATCH COMPLETE")
    print(f"  Total scripts generated: {total_scripts}")
    if failed_channels:
        print(f"  Failed: {len(failed_channels)}")
        for f in failed_channels:
            print(f"    x {f}")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
