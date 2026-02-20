#!/usr/bin/env python3
"""
faceless_pipeline.py - Automated Faceless YouTube Channel Production Pipeline

Produces voiceover-driven videos (no avatar) for 38+ niche channels.
Reads channel configs from channels_config.json, reuses ElevenLabs voice
and Gemini/Perplexity for script generation from produce_video.py.

Usage:
    python faceless_pipeline.py list-channels
    python faceless_pipeline.py topics rich_tech --count 10
    python faceless_pipeline.py script rich_tech "10 AI Tools That Changed 2026"
    python faceless_pipeline.py audio rich_horror "5 True Scary Stories From Reddit"
    python faceless_pipeline.py produce rich_tech "Best Budget Laptops 2026" --format landscape
    python faceless_pipeline.py batch rich_tech topics.txt
    python faceless_pipeline.py batch-channels --tier priority --count 2
    python faceless_pipeline.py playlist rich_tech --cross-promo
    python faceless_pipeline.py schedule --week
    python faceless_pipeline.py research rich_tech "AI tools 2026" --engine perplexity

All API keys read from shopify-theme/.env.
Channel configs from channels_config.json.
"""

import argparse
import json
import os
import random
import re
import sys
import textwrap
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PIPELINE_DIR = Path(__file__).resolve().parent
CHANNELS_CONFIG_PATH = PIPELINE_DIR / "channels_config.json"
BRAND_CONFIG_PATH = PIPELINE_DIR / "brand_config.json"
ENV_PATH = PIPELINE_DIR.parent / "shopify-theme" / ".env"
DOWNLOADS_DIR = Path.home() / "Downloads"
OUTPUT_DIR = PIPELINE_DIR / "output"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"

# Ensure output dirs exist
for d in [OUTPUT_DIR, SCRIPTS_DIR, AUDIO_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config Loaders
# ---------------------------------------------------------------------------

def load_channels_config():
    """Load multi-channel configuration."""
    if not CHANNELS_CONFIG_PATH.exists():
        print(f"[ERROR] channels_config.json not found at {CHANNELS_CONFIG_PATH}")
        sys.exit(1)
    with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_brand_config():
    """Load main brand config for voice/composition settings."""
    if not BRAND_CONFIG_PATH.exists():
        return {}
    with open(BRAND_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_api_keys():
    """Load API keys from the shared .env file."""
    if not ENV_PATH.exists():
        print(f"[ERROR] .env not found at {ENV_PATH}")
        sys.exit(1)
    load_dotenv(ENV_PATH)
    return {
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID", "HHOfU1tpMpxmIjLlpy34"),
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "perplexity_api_key": os.getenv("PERPLEXITY_API_KEY"),
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "google_client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
    }


CHANNELS = load_channels_config()
BRAND = load_brand_config()

# ---------------------------------------------------------------------------
# Channel Resolver
# ---------------------------------------------------------------------------

def get_channel(channel_id):
    """Get a channel config by its key."""
    channels = CHANNELS.get("channels", {})
    if channel_id not in channels:
        print(f"[ERROR] Channel '{channel_id}' not found.")
        print(f"[INFO] Available: {', '.join(sorted(channels.keys()))}")
        sys.exit(1)
    ch = channels[channel_id]
    if not ch.get("faceless", True):
        print(f"[WARN] '{channel_id}' is a personal channel (not faceless). Proceeding anyway.")
    return ch


def get_voice_profile(channel):
    """Get the ElevenLabs voice profile for a channel."""
    profile_name = channel.get("voice_profile", "neutral_male")
    profiles = CHANNELS.get("voice_profiles", {})
    return profiles.get(profile_name, profiles.get("neutral_male", {}))


def get_format_config(format_name):
    """Get content format configuration."""
    formats = CHANNELS.get("content_formats", {})
    return formats.get(format_name, {})


def get_hooks(channel):
    """Get niche-specific hooks for a channel."""
    niche_key = channel.get("niche", "").split(",")[0].strip().lower()
    hooks_by_niche = CHANNELS.get("hooks_by_niche", {})
    # Try niche-specific hooks first, fall back to default
    for key in [niche_key, "default"]:
        if key in hooks_by_niche:
            return hooks_by_niche[key]
    return hooks_by_niche.get("default", ["Check this out."])


# ---------------------------------------------------------------------------
# Content Research (Perplexity / Gemini)
# ---------------------------------------------------------------------------

class ContentResearcher:
    """Generates trending topics and researches content for faceless channels."""

    def __init__(self, keys):
        self.perplexity_key = keys.get("perplexity_api_key")
        self.gemini_key = keys.get("gemini_api_key")

    def generate_topics(self, channel, count=10):
        """Generate trending topic ideas for a channel using Gemini."""
        if not self.gemini_key:
            return self._fallback_topics(channel, count)

        niche = channel.get("niche", "general")
        sub_topics = channel.get("sub_topics", [])
        formats = channel.get("formats", ["listicle"])

        prompt = f"""Generate exactly {count} YouTube video topic ideas for a faceless {niche} channel.

Sub-topics to draw from: {', '.join(sub_topics)}
Preferred formats: {', '.join(formats)}

Requirements:
- Each topic should be a specific, clickable video title
- Include a mix of evergreen and trending topics
- Optimize for search (include common search terms)
- Make titles curiosity-driven but not clickbait
- Include numbers where appropriate (Top 10, 5 Best, etc.)

Return ONLY the titles, one per line, no numbering or bullets."""

        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            topics = [line.strip().strip("-").strip("•").strip()
                      for line in text.strip().split("\n")
                      if line.strip() and not line.strip().startswith("#")]
            return topics[:count]
        except Exception as exc:
            print(f"[Research] Gemini topic generation failed: {exc}")
            return self._fallback_topics(channel, count)

    def research_topic(self, topic, niche="general"):
        """Deep research a topic using Perplexity for factual content."""
        if not self.perplexity_key:
            print("[Research] No Perplexity API key — skipping deep research.")
            return None

        prompt = f"""Research this topic for a YouTube video script: "{topic}"

Provide:
1. 8-10 key facts or talking points (with sources where possible)
2. Any trending angles or recent developments
3. Common misconceptions to address
4. 2-3 surprising facts the audience likely doesn't know

Keep it factual. This is for a {niche} YouTube channel."""

        try:
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.perplexity_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"[Research] Perplexity research failed: {exc}")
            return None

    def _fallback_topics(self, channel, count):
        """Template-based topic generation when APIs are unavailable."""
        sub_topics = channel.get("sub_topics", ["interesting things"])
        niche = channel.get("niche", "content").split(",")[0].strip()
        templates = [
            "Top {n} {sub} You Need to Know About in {year}",
            "{n} {sub} That Will Blow Your Mind",
            "The Truth About {sub} Nobody Talks About",
            "Why {sub} Is More Important Than You Think",
            "{sub} Explained in {n} Minutes",
            "Best {sub} for Beginners ({year} Guide)",
            "{n} Common {sub} Mistakes and How to Fix Them",
            "The Complete Guide to {sub} ({year})",
            "{sub} vs {sub2}: Which Is Actually Better?",
            "I Tested {n} {sub} Products. Here's What Happened.",
        ]
        topics = []
        year = datetime.now().year
        for i in range(count):
            tmpl = templates[i % len(templates)]
            sub = random.choice(sub_topics)
            sub2 = random.choice([s for s in sub_topics if s != sub] or sub_topics)
            topic = tmpl.format(n=random.choice([5, 7, 10, 15]), sub=sub, sub2=sub2, year=year)
            topics.append(topic)
        return topics


# ---------------------------------------------------------------------------
# Faceless Script Writer
# ---------------------------------------------------------------------------

class FacelessScriptWriter:
    """
    Generates scripts optimized for faceless channels:
    voiceover-only, no face references, visual cues for editors/automation.
    """

    def __init__(self, channel, topic, format_type=None, research_data=None):
        self.channel = channel
        self.topic = topic
        self.format_type = format_type or (channel.get("formats", ["listicle"])[0])
        self.research = research_data
        self.niche = channel.get("niche", "general").split(",")[0].strip()
        self.templates = CHANNELS.get("script_templates", {})

    def generate(self):
        """Generate a faceless script using templates + research data."""
        template = self.templates.get(self.format_type, {})
        if not template:
            print(f"[Script] No template for format '{self.format_type}', using listicle.")
            template = self.templates.get("listicle", {})
            self.format_type = "listicle"

        # Select a hook
        hooks = get_hooks(self.channel)
        hook = random.choice(hooks).format(
            topic=self.topic,
            count=random.choice([5, 7, 10]),
            product="this",
            year=datetime.now().year,
            place="this location",
            game="this game",
        )

        # Build the script based on format
        if self.format_type in ("shorts_facts", "shorts_story"):
            script = self._build_short(template, hook)
        elif self.format_type == "listicle":
            script = self._build_listicle(template, hook)
        elif self.format_type == "explainer":
            script = self._build_explainer(template, hook)
        elif self.format_type == "compilation":
            script = self._build_compilation(template, hook)
        elif self.format_type == "news_recap":
            script = self._build_news_recap(template, hook)
        elif self.format_type == "tutorial":
            script = self._build_tutorial(template, hook)
        else:
            script = self._build_listicle(template, hook)

        # Add visual cues for automation
        script_with_cues = self._add_visual_cues(script)

        word_count = len(script.split())
        is_short = self.format_type.startswith("shorts_")

        return {
            "raw_text": script,
            "annotated_text": script_with_cues,
            "metadata": {
                "channel": self.channel.get("name", "Unknown"),
                "channel_handle": self.channel.get("handle", ""),
                "topic": self.topic,
                "format": self.format_type,
                "niche": self.niche,
                "word_count": word_count,
                "estimated_seconds": round(word_count / 2.5),
                "is_shorts": is_short,
                "voice_profile": self.channel.get("voice_profile", "neutral_male"),
                "generated_at": datetime.now().isoformat(),
                "has_research": self.research is not None,
            },
        }

    def _build_short(self, template, hook):
        """Build a Shorts script (30-60 seconds)."""
        body = template.get("full", "[HOOK]\n\n{fact}\n\nFollow for more.")
        fact = f"Here's something wild about {self.topic}."
        if self.research:
            # Extract first fact from research
            lines = [l.strip() for l in self.research.split("\n") if l.strip() and len(l.strip()) > 20]
            if lines:
                fact = lines[0][:200]

        return body.replace("[HOOK]", hook).replace("{fact}", fact).replace(
            "{story}", fact).replace("{punchline}", "And that changes everything.").replace(
            "{niche}", self.niche)

    def _build_listicle(self, template, hook):
        """Build a listicle script (Top N format)."""
        intro = template.get("intro", "").replace("[HOOK]", hook)
        item_tmpl = template.get("item", "\n\nNumber {n}: {item_title}.\n\n{item_body}")
        outro = template.get("outro", "")

        # Extract number from topic if present
        nums = re.findall(r'\d+', self.topic)
        count = int(nums[0]) if nums else 10

        retention_hooks = [
            "But wait, it gets even better.",
            "And this next one? Even more impressive.",
            "This is where things get really interesting.",
            "Now, here's one that surprised even me.",
            "You're going to want to remember this one.",
            "Okay, but THIS... this is the real game-changer.",
            "Stay with me, because this next entry is wild.",
            "I saved some of the best for last.",
            "This one completely changed my perspective.",
            "And here's the one everyone keeps asking about.",
        ]

        items_text = ""
        sub_topics = self.channel.get("sub_topics", [self.topic])

        for i in range(count, 0, -1):
            sub = random.choice(sub_topics)
            item_title = f"{sub.title()}"
            if self.research:
                # Try to pull relevant info from research
                item_body = f"When it comes to {sub}, there's a lot most people don't realize. This one stands out because of how it impacts {self.niche.lower()} in ways you wouldn't expect."
            else:
                item_body = f"This is one that a lot of people overlook. {sub.capitalize()} has been gaining attention recently, and for good reason."

            retention = retention_hooks[(count - i) % len(retention_hooks)] if i > 1 else ""

            items_text += item_tmpl.format(
                n=i, item_title=item_title, item_body=item_body,
                retention_hook=retention,
                count=count, topic=self.topic,
            )

        full = intro.format(count=count, topic=self.topic) + items_text + outro
        return full

    def _build_explainer(self, template, hook):
        """Build an explainer script."""
        intro = template.get("intro", "").replace("[HOOK]", hook).format(topic=self.topic)
        section_tmpl = template.get("section", "\n\n{section_title}\n\n{section_body}")
        outro = template.get("outro", "").format(topic=self.topic)

        sections = [
            ("What is it?", f"At its core, {self.topic} is something that affects more people than you'd think."),
            ("Why does it matter?", f"The reason {self.topic} has been getting so much attention lately comes down to a few key factors."),
            ("How does it work?", f"Understanding the mechanics behind {self.topic} is simpler than most people make it seem."),
            ("What you need to know", f"Here's the practical takeaway about {self.topic} that you can use right now."),
        ]

        retention_hooks = [
            "But here's where it gets interesting...",
            "Now this next part is crucial...",
            "And this is the part most people miss...",
            "Stay with me, because this changes everything...",
        ]

        body = ""
        for i, (title, content) in enumerate(sections):
            body += section_tmpl.format(
                section_title=title, section_body=content,
                retention_hook=retention_hooks[i % len(retention_hooks)],
            )

        return intro + body + outro

    def _build_compilation(self, template, hook):
        """Build a compilation script."""
        intro = template.get("intro", "").replace("[HOOK]", hook).format(
            count=10, topic=self.topic)
        segment_tmpl = template.get("segment", "\n\n{segment_narration}")
        outro = template.get("outro", "")

        segments = ""
        sub_topics = self.channel.get("sub_topics", [self.topic])
        for i in range(8):
            sub = random.choice(sub_topics)
            narration = f"Next up, we have this incredible example of {sub}. What makes this stand out is how it pushes the boundaries of what we thought was possible in {self.niche.lower()}."
            segments += segment_tmpl.format(segment_narration=narration)

        return intro + segments + outro

    def _build_news_recap(self, template, hook):
        """Build a news recap script."""
        intro = template.get("intro", "").replace("[HOOK]", hook).format(topic=self.topic)
        story_tmpl = template.get("story", "\n\n{headline}\n\n{details}")
        outro = template.get("outro", "").format(niche=self.niche)

        stories = ""
        sub_topics = self.channel.get("sub_topics", [self.topic])
        for i, sub in enumerate(sub_topics[:5]):
            stories += story_tmpl.format(
                headline=f"Big developments in {sub}",
                details=f"This week brought some significant changes to {sub}. Here's what you need to know.",
                analysis=f"What this means for the broader {self.niche.lower()} space is significant.",
            )

        return intro + stories + outro

    def _build_tutorial(self, template, hook):
        """Build a tutorial script."""
        intro = template.get("intro", "").replace("[HOOK]", hook).format(topic=self.topic)
        step_tmpl = template.get("step", "\n\nStep {n}: {step_title}.\n\n{step_body}")
        outro = template.get("outro", "").format(topic=self.topic)

        steps = ""
        step_titles = [
            "Getting set up",
            "Understanding the basics",
            "The core technique",
            "Advanced tips",
            "Putting it all together",
        ]

        for i, title in enumerate(step_titles, 1):
            steps += step_tmpl.format(
                n=i, step_title=title,
                step_body=f"For this step, focus on getting {self.topic.lower()} right. Take your time here because this foundation matters.",
            )

        return intro + steps + outro

    def _add_visual_cues(self, script):
        """Add visual cue markers for video assembly automation.

        Detects products, places, people, and statistics for context-aware
        b-roll generation. Shows the actual thing being discussed.
        """
        lines = script.split("\n")
        cued = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Number ") or stripped.startswith("Step "):
                cued.append(f"[VISUAL: Text overlay - \"{stripped.split(':')[0]}\"]\n{line}")
            elif "here's" in stripped.lower() or "this is" in stripped.lower():
                cued.append(f"[VISUAL: B-roll transition]\n{line}")
            else:
                # Detect price mentions (likely product)
                if re.search(r'\$[\d,]+', stripped):
                    product_match = re.search(r'(?:the\s+)?([A-Z][A-Za-z0-9\s\-]+?)(?:\s*[\(\-—]|\s+is\b|\s+at\b|\s+for\b)', stripped)
                    if product_match:
                        product = product_match.group(1).strip()
                        cued.append(f"[VISUAL: product photo of {product}, studio lighting, clean background]\n{line}")
                        continue
                # Detect place/location mentions
                if re.search(r'\b(?:in|at|visit|located in|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', stripped):
                    place_match = re.search(r'\b(?:in|at|visit|located in|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})', stripped)
                    if place_match:
                        place = place_match.group(1).strip()
                        cued.append(f"[VISUAL: photo of {place}, establishing shot]\n{line}")
                        continue
                cued.append(line)
        return "\n".join(cued)


# ---------------------------------------------------------------------------
# Faceless Script Generator (AI-powered via Gemini)
# ---------------------------------------------------------------------------

def _is_product_channel(channel):
    """Check if a channel discusses products that could include affiliate links."""
    product_niches = {"tech", "gadget", "review", "beauty", "cooking", "kitchen",
                      "fitness", "gaming", "car", "fashion", "diy", "photography", "food"}
    niche_lower = channel.get("niche", "").lower()
    name_lower = channel.get("name", "").lower()
    return any(kw in niche_lower or kw in name_lower for kw in product_niches)


def generate_ai_faceless_script(channel, topic, format_type, keys, research_data=None):
    """Generate a faceless script using Gemini AI."""
    gemini_key = keys.get("gemini_api_key")
    if not gemini_key:
        print("[AI Script] No Gemini API key — falling back to templates.")
        return None

    niche = channel.get("niche", "general")
    voice_profile = get_voice_profile(channel)
    fmt = get_format_config(format_type)
    is_product = _is_product_channel(channel)

    research_section = ""
    if research_data:
        research_section = f"\n\nResearch data to incorporate (use facts, cite when appropriate):\n{research_data[:2000]}"

    # Product-specific rules for channels that discuss products
    product_rules = ""
    if is_product:
        product_rules = """
PRODUCT GUIDELINES (CRITICAL — this channel discusses products):
- Use REAL, SPECIFIC product names (e.g. "Anker PowerCore 20000" not "a decent power bank")
- Include CURRENT approximate prices (e.g. "$39.99 on Amazon" not "around $40")
- Mention the brand and exact model for every product discussed
- Say "check the links in the description" or "link in the description below" when mentioning products
- Include a brief "prices may vary" disclaimer near the end
- Compare products to alternatives when relevant (e.g. "unlike the cheaper options...")
- Mention specific features and specs (e.g. "20,000mAh capacity" not "large battery")
- Do NOT include products you cannot verify are real and currently available
- If listing tools or software, include pricing tiers (free, pro, enterprise)

PRODUCT B-ROLL (CRITICAL — show real products):
- When introducing a product, ALWAYS add: [VISUAL: product photo of {exact product name}, clean white background, studio lighting]
- After the product intro shot, add: [VISUAL: {exact product name} in use, lifestyle context, hands using the product]
- For software/apps: [VISUAL: screenshot of {app name} interface, {specific feature} visible]
- For comparisons, add: [VISUAL: side-by-side comparison of {product A} vs {product B}]
- NEVER use generic stock footage when a specific product is being discussed
"""

    prompt = f"""Write a YouTube video script for a FACELESS {niche} channel.

Topic: {topic}
Format: {format_type} ({fmt.get('structure', 'standard')})
Target duration: {fmt.get('duration_target', '8-12 min')}
Target word count: {fmt.get('word_count', 1500)}
Voice style: {voice_profile.get('description', 'neutral narrator')}

RULES:
- NO references to "me", "my face", "as you can see me", or any visual self-references
- Use "we", "let's", or address the viewer directly with "you"
- Include [VISUAL: description] cues for the editor/automation (stock footage, text overlays, charts)

VISUAL CUE RULES (CRITICAL — makes videos feel real and professional):
- When mentioning a SPECIFIC PLACE or LOCATION, ALWAYS add: [VISUAL: aerial/exterior photo of THE PLACE NAME, THE CITY/COUNTRY]
- When mentioning a SPECIFIC PERSON, add: [VISUAL: photo portrait of THE PERSON NAME]
- When mentioning a STATISTIC or NUMBER, add: [VISUAL: text overlay - "THE STATISTIC"]
- When describing an EVENT, add: [VISUAL: historical/news photo of THE EVENT NAME, THE YEAR]
- When mentioning a COUNTRY or CITY, add: [VISUAL: landmark or skyline of THE CITY/COUNTRY]
- NEVER leave a product, place, or person mention without a corresponding VISUAL cue
- Alternate between close-up details, wide establishing shots, and text overlays for visual variety

HOOK & RETENTION (CRITICAL — this determines whether people stay or leave):
- The FIRST 15 SECONDS must contain the most shocking/interesting fact or claim from the entire video
- Do NOT start with slow atmospheric intros, greetings, or "welcome to..."
- Pattern-interrupt immediately: open with a bold statement, surprising statistic, or controversial claim
- Example: "This place has killed over 160,000 people... and tourists still visit every year."
- After the hook, preview what's coming: "In the next 8 minutes, you'll discover..."
- Include 2-3 retention hooks throughout ("but the next one is even more disturbing")
- If it's a listicle, lead with the 2nd most interesting item, save #1 for last

STRUCTURE:
- Add [CHAPTER: section name] markers at each major section for YouTube chapter timestamps
- End with a clear CTA (like, subscribe, comment)
- Keep paragraphs short (2-3 sentences max) for natural voiceover pacing
- Add a [PAUSE] marker between major sections for natural breathing room
- Be factual and provide value — no fluff
- Target 1500+ words for optimal video length (8-12 minutes for mid-roll ad eligibility)
{product_rules}{research_section}

Write the complete script now. Return ONLY the script text."""

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        word_count = len(text.split())
        print(f"[AI Script] Generated {word_count} words via Gemini")

        return {
            "raw_text": text,
            "annotated_text": text,  # AI scripts already include visual cues
            "metadata": {
                "channel": channel.get("name", "Unknown"),
                "channel_handle": channel.get("handle", ""),
                "topic": topic,
                "format": format_type,
                "niche": niche,
                "word_count": word_count,
                "estimated_seconds": round(word_count / 2.5),
                "is_shorts": format_type.startswith("shorts_"),
                "voice_profile": channel.get("voice_profile", "neutral_male"),
                "generated_at": datetime.now().isoformat(),
                "ai_generated": True,
                "has_research": research_data is not None,
            },
        }
    except Exception as exc:
        print(f"[AI Script] Gemini generation failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# ElevenLabs Audio (Faceless Voice)
# ---------------------------------------------------------------------------

class FacelessAudioProducer:
    """Produces voiceover audio for faceless channels via ElevenLabs."""

    TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(self, api_key, voice_id):
        self.api_key = api_key
        self.voice_id = voice_id

    def generate(self, text, channel, output_name="voiceover"):
        """Generate voiceover audio using channel-specific voice settings."""
        profile = get_voice_profile(channel)

        # Strip visual cues from script for TTS
        clean_text = re.sub(r'\[VISUAL:.*?\]', '', text)
        clean_text = re.sub(r'\[PAUSE\]', '...', clean_text)
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()

        model = profile.get("model", "eleven_multilingual_v2")
        voice_id = profile.get("voice_id", self.voice_id)

        url = f"{self.TTS_URL}/{voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": clean_text,
            "model_id": model,
            "voice_settings": {
                "stability": profile.get("stability", 0.55),
                "similarity_boost": profile.get("similarity_boost", 0.78),
                "style": profile.get("style", 0.20),
                "use_speaker_boost": True,
            },
        }

        # Chunk long scripts (ElevenLabs has a ~5000 char limit per request)
        if len(clean_text) > 4500:
            return self._generate_chunked(clean_text, voice_id, model, profile, output_name, channel)

        print(f"[Audio] Generating voiceover ({len(clean_text)} chars, model: {model})")
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[Audio] Generation failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[Audio] Response: {exc.response.text[:500]}")
            return None

        channel_name = channel.get("handle", "faceless").lstrip("@")
        safe_name = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = AUDIO_DIR / f"{channel_name}_{safe_name}_{timestamp}.mp3"

        with open(audio_path, "wb") as f:
            f.write(resp.content)

        size_mb = audio_path.stat().st_size / (1024 * 1024)
        print(f"[Audio] Saved: {audio_path.name} ({size_mb:.1f} MB)")
        return audio_path

    def _generate_chunked(self, text, voice_id, model, profile, output_name, channel):
        """Generate audio in chunks for long scripts, then concatenate."""
        # Split on paragraph breaks, keeping chunks under 4500 chars
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) + 2 > 4500:
                if current:
                    chunks.append(current.strip())
                current = p
            else:
                current += "\n\n" + p if current else p
        if current.strip():
            chunks.append(current.strip())

        print(f"[Audio] Long script — splitting into {len(chunks)} chunks")

        audio_parts = []
        for i, chunk in enumerate(chunks):
            print(f"[Audio] Generating chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")
            url = f"{self.TTS_URL}/{voice_id}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": chunk,
                "model_id": model,
                "voice_settings": {
                    "stability": profile.get("stability", 0.55),
                    "similarity_boost": profile.get("similarity_boost", 0.78),
                    "style": profile.get("style", 0.20),
                    "use_speaker_boost": True,
                },
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                chunk_path = AUDIO_DIR / f"_chunk_{i}.mp3"
                with open(chunk_path, "wb") as f:
                    f.write(resp.content)
                audio_parts.append(chunk_path)
            except requests.RequestException as exc:
                print(f"[Audio] Chunk {i + 1} failed: {exc}")
                # Clean up partial chunks
                for p in audio_parts:
                    p.unlink(missing_ok=True)
                return None
            time.sleep(1)  # Rate limit buffer

        # Concatenate chunks
        channel_name = channel.get("handle", "faceless").lstrip("@")
        safe_name = re.sub(r'[^\w\s-]', '', output_name).strip().replace(' ', '_')[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = AUDIO_DIR / f"{channel_name}_{safe_name}_{timestamp}.mp3"

        with open(final_path, "wb") as out:
            for part in audio_parts:
                out.write(part.read_bytes())
                part.unlink()

        size_mb = final_path.stat().st_size / (1024 * 1024)
        print(f"[Audio] Combined: {final_path.name} ({size_mb:.1f} MB)")
        return final_path


# ---------------------------------------------------------------------------
# SEO Generator (Faceless-specific)
# ---------------------------------------------------------------------------

class FacelessSEO:
    """Generates SEO metadata tailored for faceless channels."""

    def __init__(self, channel, topic):
        self.channel = channel
        self.topic = topic
        self.niche = channel.get("niche", "general").split(",")[0].strip()

    def generate(self):
        """Generate title options, description, and tags."""
        name = self.channel.get("name", "Channel")
        handle = self.channel.get("handle", "")
        niche = self.niche

        titles = [
            self.topic,  # Use the original topic as primary title
            f"{self.topic} | {name}",
            f"{self.topic} ({datetime.now().year})",
        ]

        footer = CHANNELS.get("seo_defaults", {}).get("description_footer", "")
        description = (
            f"{self.topic}\n\n"
            f"In this video, we break down everything you need to know about this topic.\n\n"
            f"Don't forget to like, subscribe, and hit the notification bell!\n"
            f"{footer}"
        )

        # Combine channel-specific tags with defaults
        channel_niche_words = [w.strip().lower() for w in niche.split(",")]
        sub_topics = [s.lower() for s in self.channel.get("sub_topics", [])]
        default_tags = CHANNELS.get("seo_defaults", {}).get("default_tags", [])
        topic_words = [w.lower() for w in self.topic.split() if len(w) > 3]

        tags = list(dict.fromkeys(  # deduplicate while preserving order
            channel_niche_words + sub_topics[:5] + topic_words[:5] + default_tags + [name.lower()]
        ))

        return {
            "titles": titles,
            "description": description,
            "tags": tags[:30],  # YouTube max ~500 chars total, keep reasonable
            "category_id": self.channel.get("youtube_category", "22"),
        }


# ---------------------------------------------------------------------------
# Batch Production Engine
# ---------------------------------------------------------------------------

class BatchProducer:
    """Orchestrates batch production across multiple channels."""

    def __init__(self, keys):
        self.keys = keys
        self.researcher = ContentResearcher(keys)
        self.audio_producer = None
        if keys.get("elevenlabs_api_key"):
            self.audio_producer = FacelessAudioProducer(
                api_key=keys["elevenlabs_api_key"],
                voice_id=keys.get("elevenlabs_voice_id", "HHOfU1tpMpxmIjLlpy34"),
            )

    def produce_for_channel(self, channel_id, topic, format_type=None, use_ai=True, skip_audio=False):
        """Full production pipeline for a single video on a channel."""
        channel = get_channel(channel_id)
        if format_type is None:
            format_type = channel.get("formats", ["listicle"])[0]

        print(f"\n{'=' * 64}")
        print(f"  Channel: {channel.get('name')} ({channel.get('handle')})")
        print(f"  Topic: {topic}")
        print(f"  Format: {format_type}")
        print(f"  Voice: {channel.get('voice_profile', 'neutral_male')}")
        print(f"{'=' * 64}\n")

        # Step 1: Research (optional)
        research = None
        if self.keys.get("perplexity_api_key"):
            print("[1/4] Researching topic...")
            research = self.researcher.research_topic(topic, channel.get("niche", ""))
        else:
            print("[1/4] Skipping research (no Perplexity key)")

        # Step 2: Script
        print("[2/4] Generating script...")
        script_data = None
        if use_ai and self.keys.get("gemini_api_key"):
            script_data = generate_ai_faceless_script(channel, topic, format_type, self.keys, research)

        if not script_data:
            writer = FacelessScriptWriter(channel, topic, format_type, research)
            script_data = writer.generate()

        # Save script
        safe_topic = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')[:50]
        channel_name = channel.get("handle", "ch").lstrip("@")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        script_path = SCRIPTS_DIR / f"{channel_name}_{safe_topic}_{timestamp}.txt"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(f"# Channel: {channel.get('name')}\n")
            f.write(f"# Topic: {topic}\n")
            f.write(f"# Format: {format_type}\n")
            f.write(f"# Words: {script_data['metadata']['word_count']}\n")
            f.write(f"# Est. Duration: ~{script_data['metadata']['estimated_seconds']}s\n")
            f.write(f"# Generated: {script_data['metadata']['generated_at']}\n\n")
            f.write(script_data["raw_text"])
        print(f"[Script] Saved: {script_path.name}")

        # Step 3: Audio
        audio_path = None
        if not skip_audio and self.audio_producer:
            print("[3/4] Generating voiceover...")
            audio_path = self.audio_producer.generate(
                script_data["annotated_text"], channel, topic
            )
        else:
            print("[3/4] Skipping audio generation")

        # Step 4: SEO metadata
        print("[4/4] Generating SEO metadata...")
        seo = FacelessSEO(channel, topic)
        seo_data = seo.generate()

        seo_path = SCRIPTS_DIR / f"{channel_name}_{safe_topic}_{timestamp}_seo.json"
        with open(seo_path, "w", encoding="utf-8") as f:
            json.dump(seo_data, f, indent=2)
        print(f"[SEO] Saved: {seo_path.name}")

        result = {
            "channel": channel_id,
            "topic": topic,
            "format": format_type,
            "script_path": str(script_path),
            "audio_path": str(audio_path) if audio_path else None,
            "seo_path": str(seo_path),
            "word_count": script_data["metadata"]["word_count"],
            "estimated_seconds": script_data["metadata"]["estimated_seconds"],
        }

        print(f"\n[DONE] {channel.get('name')} — {topic}")
        return result

    def batch_channel(self, channel_id, topics, skip_audio=False):
        """Produce multiple videos for a single channel."""
        results = []
        for i, topic in enumerate(topics, 1):
            print(f"\n{'#' * 64}")
            print(f"  BATCH [{i}/{len(topics)}]")
            print(f"{'#' * 64}")
            result = self.produce_for_channel(channel_id, topic, skip_audio=skip_audio)
            results.append(result)

            # Rate limit buffer between productions
            delay = CHANNELS.get("automation", {}).get("batch_delay_seconds", 30)
            if i < len(topics):
                print(f"\n[Batch] Waiting {delay}s before next production...")
                time.sleep(delay)

        return results

    def batch_channels(self, tier="priority", count_per_channel=2, skip_audio=False):
        """
        Produce content across multiple channels by tier.

        Tiers: priority, secondary, growth (from automation config).
        """
        auto_cfg = CHANNELS.get("automation", {}).get("scheduling", {})
        tier_channels = auto_cfg.get(f"{tier}_channels", [])

        if not tier_channels:
            print(f"[ERROR] No channels in tier '{tier}'")
            print(f"[INFO] Available tiers: priority, secondary, growth")
            return []

        print(f"\n{'=' * 64}")
        print(f"  MULTI-CHANNEL BATCH — Tier: {tier}")
        print(f"  Channels: {len(tier_channels)} x {count_per_channel} videos each")
        print(f"{'=' * 64}\n")

        all_results = []
        for ch_id in tier_channels:
            channel = get_channel(ch_id)
            print(f"\n[Channel] {channel.get('name')} — generating topics...")

            topics = self.researcher.generate_topics(channel, count=count_per_channel)
            print(f"[Topics] {len(topics)} topics generated:")
            for t in topics:
                print(f"  - {t}")

            results = self.batch_channel(ch_id, topics, skip_audio=skip_audio)
            all_results.extend(results)

        # Save batch report
        report_path = OUTPUT_DIR / f"batch_report_{tier}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
        print(f"\n[Report] Saved: {report_path}")

        return all_results


# ---------------------------------------------------------------------------
# Weekly Schedule Generator
# ---------------------------------------------------------------------------

def generate_weekly_schedule():
    """Generate a full week's content schedule across all active channels."""
    channels = CHANNELS.get("channels", {})
    auto_cfg = CHANNELS.get("automation", {}).get("scheduling", {})

    all_tiers = []
    for tier_name in ["priority_channels", "secondary_channels", "growth_channels"]:
        all_tiers.extend(auto_cfg.get(tier_name, []))

    schedule = {}
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for day in days:
        schedule[day] = {"long_form": [], "shorts": []}

    for ch_id in all_tiers:
        ch = channels.get(ch_id, {})
        if not ch or not ch.get("faceless", True):
            continue

        posting = ch.get("posting", {})
        name = ch.get("name", ch_id)

        # Parse long-form frequency
        lf = posting.get("long_form", "")
        if "3x" in lf:
            lf_days = random.sample(days[:5], 3)  # Weekdays
        elif "2x" in lf:
            lf_days = random.sample(days[:5], 2)
        elif "1x" in lf:
            lf_days = random.sample(days, 1)
        else:
            lf_days = []

        for day in lf_days:
            schedule[day]["long_form"].append({"channel": name, "id": ch_id})

        # Shorts
        shorts = posting.get("shorts", "")
        if "3x/day" in shorts:
            for day in days:
                schedule[day]["shorts"].extend([{"channel": name, "id": ch_id}] * 3)
        elif "daily" in shorts:
            for day in days:
                schedule[day]["shorts"].append({"channel": name, "id": ch_id})
        elif "3x/week" in shorts:
            for day in random.sample(days, 3):
                schedule[day]["shorts"].append({"channel": name, "id": ch_id})

    # Print schedule
    print("\n" + "=" * 64)
    print("  WEEKLY CONTENT SCHEDULE")
    print("=" * 64)

    for day in days:
        lf = schedule[day]["long_form"]
        sh = schedule[day]["shorts"]
        print(f"\n{day}:")
        if lf:
            print(f"  Long-form ({len(lf)}):")
            for item in lf:
                print(f"    - {item['channel']}")
        if sh:
            print(f"  Shorts ({len(sh)}):")
            # Group by channel
            from collections import Counter
            counts = Counter(item["channel"] for item in sh)
            for ch_name, count in counts.most_common():
                print(f"    - {ch_name} x{count}")

    total_lf = sum(len(schedule[d]["long_form"]) for d in days)
    total_sh = sum(len(schedule[d]["shorts"]) for d in days)
    print(f"\n  WEEKLY TOTAL: {total_lf} long-form + {total_sh} shorts = {total_lf + total_sh} videos")
    print("=" * 64)

    return schedule


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="faceless_pipeline",
        description="Faceless YouTube Channel Production Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
            %(prog)s list-channels
            %(prog)s topics rich_tech --count 10
            %(prog)s script rich_horror "5 True Scary Stories"
            %(prog)s audio rich_tech "Best AI Tools 2026"
            %(prog)s produce rich_tech "Budget Laptops" --format listicle
            %(prog)s batch rich_tech topics.txt
            %(prog)s batch-channels --tier priority --count 2
            %(prog)s schedule --week
            %(prog)s research rich_tech "AI trends" --engine perplexity
        """),
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # list-channels
    sub.add_parser("list-channels", help="List all configured channels")

    # topics
    p_topics = sub.add_parser("topics", help="Generate topic ideas for a channel")
    p_topics.add_argument("channel", help="Channel ID (e.g. rich_tech)")
    p_topics.add_argument("--count", type=int, default=10, help="Number of topics")

    # script
    p_script = sub.add_parser("script", help="Generate a script for a channel")
    p_script.add_argument("channel", help="Channel ID")
    p_script.add_argument("topic", help="Video topic/title")
    p_script.add_argument("--format", dest="fmt", help="Content format (listicle, explainer, etc.)")
    p_script.add_argument("--ai", action="store_true", help="Use Gemini AI for script generation")

    # audio
    p_audio = sub.add_parser("audio", help="Generate script + voiceover audio")
    p_audio.add_argument("channel", help="Channel ID")
    p_audio.add_argument("topic", help="Video topic/title")
    p_audio.add_argument("--format", dest="fmt", help="Content format")
    p_audio.add_argument("--ai", action="store_true", help="Use Gemini AI for script")

    # produce
    p_produce = sub.add_parser("produce", help="Full production: research → script → audio → SEO")
    p_produce.add_argument("channel", help="Channel ID")
    p_produce.add_argument("topic", help="Video topic/title")
    p_produce.add_argument("--format", dest="fmt", help="Content format")
    p_produce.add_argument("--skip-audio", action="store_true", help="Skip audio generation")

    # batch (single channel, multiple topics from file)
    p_batch = sub.add_parser("batch", help="Batch produce from topics file")
    p_batch.add_argument("channel", help="Channel ID")
    p_batch.add_argument("topics_file", help="Path to topics file (one per line)")
    p_batch.add_argument("--skip-audio", action="store_true", help="Skip audio generation")

    # batch-channels (multi-channel)
    p_bch = sub.add_parser("batch-channels", help="Batch produce across channel tier")
    p_bch.add_argument("--tier", default="priority", choices=["priority", "secondary", "growth"],
                        help="Channel tier to produce for")
    p_bch.add_argument("--count", type=int, default=2, help="Videos per channel")
    p_bch.add_argument("--skip-audio", action="store_true", help="Skip audio generation")

    # schedule
    p_sched = sub.add_parser("schedule", help="Generate content schedule")
    p_sched.add_argument("--week", action="store_true", help="Generate weekly schedule")

    # research
    p_research = sub.add_parser("research", help="Research a topic")
    p_research.add_argument("channel", help="Channel ID (for niche context)")
    p_research.add_argument("topic", help="Topic to research")
    p_research.add_argument("--engine", default="perplexity", choices=["perplexity", "gemini"])

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    keys = load_api_keys()

    print("=" * 64)
    print("  Faceless YouTube Channel Production Pipeline")
    print(f"  Channels: {len([c for c in CHANNELS.get('channels', {}).values() if c.get('faceless')])} faceless")
    print("=" * 64)
    print()

    # -- list-channels ---------------------------------------------------------
    if args.command == "list-channels":
        channels = CHANNELS.get("channels", {})
        faceless = {k: v for k, v in channels.items() if v.get("faceless")}
        personal = {k: v for k, v in channels.items() if not v.get("faceless")}

        if personal:
            print("PERSONAL CHANNELS:")
            for k, v in personal.items():
                print(f"  {k:25s} {v.get('name', '')} ({v.get('handle', '')})")

        print(f"\nFACELESS CHANNELS ({len(faceless)}):")
        print(f"  {'ID':25s} {'Name':20s} {'Handle':22s} {'Niche'}")
        print(f"  {'-'*25} {'-'*20} {'-'*22} {'-'*30}")
        for k, v in sorted(faceless.items()):
            niche_short = v.get("niche", "")[:30]
            print(f"  {k:25s} {v.get('name', ''):20s} {v.get('handle', ''):22s} {niche_short}")

        # Print tier info
        auto = CHANNELS.get("automation", {}).get("scheduling", {})
        for tier in ["priority_channels", "secondary_channels", "growth_channels"]:
            tier_chs = auto.get(tier, [])
            if tier_chs:
                print(f"\n  {tier.replace('_', ' ').title()}: {', '.join(tier_chs)}")

    # -- topics ----------------------------------------------------------------
    elif args.command == "topics":
        channel = get_channel(args.channel)
        researcher = ContentResearcher(keys)
        print(f"[{channel.get('name')}] Generating {args.count} topic ideas...\n")
        topics = researcher.generate_topics(channel, count=args.count)

        print(f"TOPIC IDEAS for {channel.get('name')}:")
        print("-" * 64)
        for i, topic in enumerate(topics, 1):
            print(f"  {i:2d}. {topic}")

        # Save to file
        safe_name = args.channel
        path = SCRIPTS_DIR / f"{safe_name}_topics_{datetime.now().strftime('%Y%m%d')}.txt"
        with open(path, "w", encoding="utf-8") as f:
            for topic in topics:
                f.write(topic + "\n")
        print(f"\n[Saved] {path}")

    # -- script ----------------------------------------------------------------
    elif args.command == "script":
        channel = get_channel(args.channel)
        fmt = args.fmt or channel.get("formats", ["listicle"])[0]

        script_data = None
        if args.ai:
            script_data = generate_ai_faceless_script(channel, args.topic, fmt, keys)

        if not script_data:
            writer = FacelessScriptWriter(channel, args.topic, fmt)
            script_data = writer.generate()

        # Save
        safe_topic = re.sub(r'[^\w\s-]', '', args.topic).strip().replace(' ', '_')[:50]
        ch_name = channel.get("handle", "ch").lstrip("@")
        path = SCRIPTS_DIR / f"{ch_name}_{safe_topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(script_data["raw_text"])
        print(f"\n[Saved] {path}")

        print(f"\n{'-' * 64}")
        print(f"SCRIPT for {channel.get('name')} — {args.topic}")
        print(f"Format: {fmt} | Words: {script_data['metadata']['word_count']} | ~{script_data['metadata']['estimated_seconds']}s")
        print(f"{'-' * 64}")
        print(script_data["raw_text"][:2000])
        if len(script_data["raw_text"]) > 2000:
            print(f"\n... ({len(script_data['raw_text']) - 2000} more chars — see saved file)")

    # -- audio -----------------------------------------------------------------
    elif args.command == "audio":
        if not keys.get("elevenlabs_api_key"):
            print("[ERROR] ELEVENLABS_API_KEY not set in .env")
            sys.exit(1)

        channel = get_channel(args.channel)
        fmt = args.fmt or channel.get("formats", ["listicle"])[0]

        script_data = None
        if args.ai:
            script_data = generate_ai_faceless_script(channel, args.topic, fmt, keys)
        if not script_data:
            writer = FacelessScriptWriter(channel, args.topic, fmt)
            script_data = writer.generate()

        producer = FacelessAudioProducer(
            api_key=keys["elevenlabs_api_key"],
            voice_id=keys.get("elevenlabs_voice_id", "HHOfU1tpMpxmIjLlpy34"),
        )
        audio_path = producer.generate(script_data["annotated_text"], channel, args.topic)

        if audio_path:
            print(f"\n[SUCCESS] Audio: {audio_path}")
        else:
            print("\n[FAILED] Audio generation failed.")
            sys.exit(1)

    # -- produce ---------------------------------------------------------------
    elif args.command == "produce":
        producer = BatchProducer(keys)
        result = producer.produce_for_channel(
            args.channel, args.topic,
            format_type=args.fmt,
            skip_audio=args.skip_audio,
        )
        print(f"\n[RESULT] {json.dumps(result, indent=2)}")

    # -- batch -----------------------------------------------------------------
    elif args.command == "batch":
        topics_path = Path(args.topics_file)
        if not topics_path.exists():
            print(f"[ERROR] Topics file not found: {args.topics_file}")
            sys.exit(1)

        topics = [line.strip() for line in topics_path.read_text().splitlines()
                  if line.strip() and not line.startswith("#")]
        print(f"[Batch] Loaded {len(topics)} topics")

        producer = BatchProducer(keys)
        results = producer.batch_channel(args.channel, topics, skip_audio=args.skip_audio)
        print(f"\n[BATCH COMPLETE] {len(results)} videos produced")

    # -- batch-channels --------------------------------------------------------
    elif args.command == "batch-channels":
        producer = BatchProducer(keys)
        results = producer.batch_channels(
            tier=args.tier,
            count_per_channel=args.count,
            skip_audio=args.skip_audio,
        )
        print(f"\n[BATCH COMPLETE] {len(results)} total videos across {args.tier} channels")

    # -- schedule --------------------------------------------------------------
    elif args.command == "schedule":
        generate_weekly_schedule()

    # -- research --------------------------------------------------------------
    elif args.command == "research":
        channel = get_channel(args.channel)
        researcher = ContentResearcher(keys)
        print(f"[Research] Topic: {args.topic}")
        print(f"[Research] Engine: {args.engine}\n")

        if args.engine == "perplexity":
            result = researcher.research_topic(args.topic, channel.get("niche", ""))
        else:
            result = None
            topics = researcher.generate_topics(channel, count=1)
            if topics:
                result = f"Generated angle: {topics[0]}"

        if result:
            print("-" * 64)
            print(result)
            print("-" * 64)
        else:
            print("[Research] No results.")


if __name__ == "__main__":
    main()
