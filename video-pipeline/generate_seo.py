#!/usr/bin/env python3
"""
Generate SEO metadata JSON files for RichTraining videos.

Uses the FacelessSEO class from faceless_pipeline.py with Gemini API,
falling back to static generation on failure.
"""

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
CHANNELS_CONFIG_PATH = PIPELINE_DIR / "channels_config.json"
ENV_PATH = PIPELINE_DIR.parent / "shopify-theme" / ".env"
SCRIPTS_DIR = PIPELINE_DIR / "output" / "scripts"
SEO_DIR = PIPELINE_DIR / "output" / "seo"

# Ensure output dirs exist
SEO_DIR.mkdir(parents=True, exist_ok=True)

# Load env
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Load channels config
with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as f:
    CHANNELS = json.load(f)

# ---------------------------------------------------------------------------
# Import FacelessSEO from faceless_pipeline
# ---------------------------------------------------------------------------
# We need to inject the CHANNELS global into the faceless_pipeline module
# before importing FacelessSEO (it references CHANNELS at module level).
# Instead, we copy the class logic inline to avoid circular/module issues.

import requests
from datetime import datetime


class FacelessSEO:
    """Generates SEO metadata tailored for faceless channels.

    Uses Gemini to produce search-optimized titles, descriptions with timestamps,
    and multi-word keyword tags. Falls back to static generation on API failure.
    """

    def __init__(self, channel, topic, script_text=""):
        self.channel = channel
        self.topic = topic
        self.script_text = script_text
        self.niche = channel.get("niche", "general").split(",")[0].strip()

    def _gemini_seo(self):
        """Use Gemini to generate high-quality SEO metadata."""
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return None

        name = self.channel.get("name", "Channel")
        handle = self.channel.get("handle", "")
        niche = self.niche

        # Extract chapter titles from script for timestamps
        chapters = []
        if self.script_text:
            for m in re.finditer(r'##\s+(?:Chapter\s+\d+:\s*)?(.+?)(?:\s*\([\d:]+\s*-\s*[\d:]+\))?\s*$', self.script_text, re.MULTILINE):
                title = m.group(1).strip()
                if title.lower() != "hook":
                    chapters.append(title)

        prompt = f"""Generate YouTube SEO metadata for this video. Return valid JSON only.

VIDEO TOPIC: {self.topic}
CHANNEL: {name} ({handle})
NICHE: {niche}
CHAPTERS: {', '.join(chapters) if chapters else 'N/A'}

SCRIPT EXCERPT (first 500 chars):
{self.script_text[:500] if self.script_text else 'N/A'}

Return this exact JSON structure:
{{
  "titles": ["<primary title under 60 chars>", "<alternative title with channel name>", "<curiosity-driven title variant>"],
  "description": "<3-4 sentence summary of what viewer will learn>\\n\\nTimestamps:\\n0:00 Intro\\n<chapter timestamps>\\n\\n<2 lines of relevant keywords naturally embedded>",
  "tags": ["<15-20 multi-word search phrases like 'workplace productivity tips', 'career growth 2026'>"]
}}

RULES:
- Titles: Include the year 2026, keep primary under 60 chars, make one curiosity-driven
- Description: Start with a specific summary (NOT 'In this video we break down...'). Include what the viewer will learn. Add chapter timestamps.
- Tags: ONLY multi-word phrases (2-4 words each). No single words. Include relevant search terms for professional development.
- Do NOT include generic tags like 'faceless youtube', 'AI narration', 'top 10', 'facts'
- Return ONLY the JSON, no markdown fences"""

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 1024},
            }
            resp = requests.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            # Strip markdown fences if present
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            result = json.loads(text.strip())
            return result
        except Exception as e:
            print(f"  [SEO] Gemini SEO generation failed: {e}")
            return None

    def _static_seo(self):
        """Fallback static SEO generation."""
        name = self.channel.get("name", "Channel")
        niche = self.niche

        titles = [
            self.topic,
            f"{self.topic} | {name}",
            f"{self.topic} - Complete Guide ({datetime.now().year})",
        ]

        footer = CHANNELS.get("seo_defaults", {}).get("description_footer", "")
        channel_hashtag = self.channel.get("name", "").replace(" ", "")
        footer = footer.replace("#{channel_hashtag}", f"#{channel_hashtag}")
        description = (
            f"{self.topic}\n\n"
            f"Step-by-step guide covering everything you need to get started.\n\n"
            f"Don't forget to like, subscribe, and hit the notification bell!\n"
            f"{footer}"
        )

        # Build multi-word tag phrases instead of single words
        topic_lower = self.topic.lower()
        tags = [
            topic_lower,
            f"{niche} tutorial",
            f"{niche} guide 2026",
            f"{self.topic.split(':')[0].lower().strip()} tutorial",
        ]
        # Add channel-specific sub-topics
        sub_topics = [s.lower() for s in self.channel.get("sub_topics", [])]
        tags.extend(sub_topics[:5])
        tags.append(name.lower())

        return {
            "titles": titles,
            "description": description,
            "tags": list(dict.fromkeys(tags))[:20],
            "category_id": self.channel.get("youtube_category", "22"),
        }

    def generate(self):
        """Generate SEO metadata. Uses Gemini if available, falls back to static."""
        result = self._gemini_seo()
        if result and "titles" in result and "description" in result and "tags" in result:
            # Add footer to Gemini description
            footer = CHANNELS.get("seo_defaults", {}).get("description_footer", "")
            channel_hashtag = self.channel.get("name", "").replace(" ", "")
            footer = footer.replace("#{channel_hashtag}", f"#{channel_hashtag}")
            if footer and footer not in result["description"]:
                result["description"] += f"\n{footer}"
            result["category_id"] = self.channel.get("youtube_category", "22")
            return result
        return self._static_seo()


# ---------------------------------------------------------------------------
# Video-to-script mapping
# ---------------------------------------------------------------------------

VIDEO_SCRIPT_MAP = [
    {
        "video": "RichTraining_7_Toxic_Workplace_Habits_Killing_Your_Productivity_And_How_t_20260304_155856.mp4",
        "script": "RichTraining_7_Toxic_Workplace_Habits_Killing_Your_Productivity_And_How_to_Fix_Them_20260304_153003.txt",
        "topic": "7 Toxic Workplace Habits Killing Your Productivity (And How to Fix Them!)",
    },
    {
        "video": "RichTraining_Future-Proof_Your_Career_Top_5_Professional_Certifications_t_20260304_160742.mp4",
        "script": "RichTraining_Future-Proof_Your_Career_Top_5_Professional_Certifications_to_Dominate_2026_20260304_153003.txt",
        "topic": "Future-Proof Your Career: Top 5 Professional Certifications to Dominate 2026",
    },
    {
        "video": "RichTraining_Leadership_Skills_Masterclass_The_Unconventional_Guide_to_In_20260304_161337.mp4",
        "script": "RichTraining_Leadership_Skills_Masterclass_The_Unconventional_Guide_to_Inspiring_Your_Team_20260304_153003.txt",
        "topic": "Leadership Skills Masterclass: The Unconventional Guide to Inspiring Your Team",
    },
]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    channel = CHANNELS.get("channels", {}).get("rich_training")
    if not channel:
        print("[ERROR] Channel 'rich_training' not found in channels_config.json")
        sys.exit(1)

    print(f"[SEO] Generating SEO metadata for {len(VIDEO_SCRIPT_MAP)} RichTraining videos")
    print(f"[SEO] Gemini API key: {'present' if os.getenv('GEMINI_API_KEY') else 'MISSING (will use static fallback)'}")
    print()

    for item in VIDEO_SCRIPT_MAP:
        video_name = item["video"]
        script_name = item["script"]
        topic = item["topic"]

        # Read script text
        script_path = SCRIPTS_DIR / script_name
        script_text = ""
        if script_path.exists():
            with open(script_path, "r", encoding="utf-8") as f:
                script_text = f.read()
            print(f"  [Script] Loaded: {script_name} ({len(script_text)} chars)")
        else:
            print(f"  [Script] WARNING: Script not found at {script_path}")

        # Generate SEO
        seo = FacelessSEO(channel, topic, script_text=script_text)
        seo_data = seo.generate()

        # Save with filename matching the video file (but .json extension)
        seo_filename = Path(video_name).stem + ".json"
        seo_path = SEO_DIR / seo_filename
        with open(seo_path, "w", encoding="utf-8") as f:
            json.dump(seo_data, f, indent=2, ensure_ascii=False)

        print(f"  [SEO] Saved: {seo_path.name}")
        print(f"    Titles: {seo_data.get('titles', ['N/A'])[0][:60]}...")
        print(f"    Tags: {len(seo_data.get('tags', []))} tags")
        print(f"    Category: {seo_data.get('category_id', 'N/A')}")
        print()

    print(f"[DONE] All {len(VIDEO_SCRIPT_MAP)} SEO files saved to {SEO_DIR}")


if __name__ == "__main__":
    main()
