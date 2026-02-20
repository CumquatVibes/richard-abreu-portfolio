#!/usr/bin/env python3
"""
produce_video.py - Richard Abreu's End-to-End YouTube Video Production Pipeline

Generates emotion-tagged scripts optimised for viewer retention, then produces
videos via HeyGen's digital avatar API or audio via ElevenLabs voice clone.
Reads brand configuration from brand_config.json for consistent branding.

Usage:
    python produce_video.py script "Topic" --tone professional --duration medium
    python produce_video.py video "Topic" --tone casual --format shorts
    python produce_video.py audio "Topic" --tone energetic
    python produce_video.py from-script script.txt --output video
    python produce_video.py seo "Topic" --pillar tech
    python produce_video.py batch topics.txt --output video --format shorts
    python produce_video.py music "lo-fi chill beat for art tutorial"
    python produce_video.py sfx "transition_whoosh"
    python produce_video.py upload ~/Downloads/video.mp4 --title "My Video" --pillar art
    python produce_video.py produce "Topic" --pillar art --format landscape
    python produce_video.py produce "Topic" --pillar tech --skip-compose --no-music
    python produce_video.py thumbnail "Topic" --pillar art
    python produce_video.py image broll --pillar tech --count 3 --model nano-banana
    python produce_video.py image thumbnail "Topic" --text "GAME CHANGER" --model nano-banana-pro
    python produce_video.py image models
    python produce_video.py setup-auth

All API keys are read from the shopify-theme .env file.
Brand settings are read from brand_config.json.
"""

import argparse
import json
import os
import random
import re
import shutil
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PIPELINE_DIR = Path(__file__).resolve().parent
BRAND_CONFIG_PATH = PIPELINE_DIR / "brand_config.json"
ENV_PATH = PIPELINE_DIR.parent / "shopify-theme" / ".env"
DOWNLOADS_DIR = Path.home() / "Downloads"

# ---------------------------------------------------------------------------
# Brand Config Loader
# ---------------------------------------------------------------------------

def load_brand_config():
    """Load brand configuration from brand_config.json."""
    if not BRAND_CONFIG_PATH.exists():
        print(f"[WARN] brand_config.json not found at {BRAND_CONFIG_PATH}, using defaults")
        return {}
    with open(BRAND_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


BRAND = load_brand_config()

# ---------------------------------------------------------------------------
# Configuration from brand_config.json
# ---------------------------------------------------------------------------

# HeyGen avatar + voice (proven working IDs from brand config)
_avatar_cfg = BRAND.get("avatar", {}).get("heygen", {})
HEYGEN_AVATAR_ID = _avatar_cfg.get("avatar_id", "79027ba724c74f059691d110b87d5b82")
HEYGEN_LOOK_ID = _avatar_cfg.get("look_id", "108f69581cf740a0aac1437e3dd9105e")
HEYGEN_AVATAR_STYLE = _avatar_cfg.get("avatar_style", "normal")
HEYGEN_EMOTION_BY_TONE = _avatar_cfg.get("emotion_by_tone", {})
HEYGEN_CAPTION_ENABLED = _avatar_cfg.get("caption_enabled", True)
HEYGEN_BACKGROUNDS = _avatar_cfg.get("background_options", {})

_voice_cfg = BRAND.get("voice", {}).get("heygen", {})
HEYGEN_VOICE_ID = _voice_cfg.get("voice_id", "d6056fe3944d4b7e9c21601b8fd893f8")
HEYGEN_SPEED_DEFAULT = _voice_cfg.get("speed_default", 1.0)
HEYGEN_SPEED_ENERGETIC = _voice_cfg.get("speed_energetic", 1.1)
HEYGEN_SPEED_CALM = _voice_cfg.get("speed_calm", 0.95)
HEYGEN_SPEED_SHORTS = _voice_cfg.get("speed_shorts", 1.15)

# ElevenLabs voice presets per tone (from brand config)
_el_cfg = BRAND.get("voice", {}).get("elevenlabs", {})
ELEVENLABS_MODEL = _el_cfg.get("model", "eleven_multilingual_v2")
ELEVENLABS_PRESETS = _el_cfg.get("presets", {})

# Video formats from brand config
_formats = BRAND.get("video_formats", {})
VIDEO_FORMATS = {
    "landscape": _formats.get("youtube_landscape", {"width": 1920, "height": 1080}),
    "shorts": _formats.get("youtube_shorts", {"width": 1080, "height": 1920}),
    "square": _formats.get("youtube_square", {"width": 1080, "height": 1080}),
}

# Visual identity
_visual = BRAND.get("visual_identity", {})
BACKGROUND_COLOR = _visual.get("background_color", "#101922")

# Content pillars
CONTENT_PILLARS = {p["id"]: p for p in BRAND.get("content_pillars", [])}

# SEO templates
SEO_TEMPLATES = BRAND.get("seo_templates", {})

# Hook library
HOOK_LIBRARY = BRAND.get("hook_library", {})

# Retention tactics
RETENTION_TACTICS = BRAND.get("retention_tactics", {})

# HeyGen endpoints
HEYGEN_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
HEYGEN_STATUS_URL = "https://api.heygen.com/v1/video_status.get"
HEYGEN_AGENT_URL = "https://api.heygen.com/v1/video_agent/generate"
HEYGEN_ASSET_UPLOAD_URL = "https://upload.heygen.com/v1/asset"

# ElevenLabs endpoints
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_MUSIC_URL = "https://api.elevenlabs.io/v1/music"
ELEVENLABS_SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"

# Music and SFX presets from brand config
MUSIC_PRESETS = BRAND.get("music_presets", {})
SFX_PRESETS = BRAND.get("sound_effects", {})

# Composition settings from brand config
_comp_cfg = BRAND.get("composition", {})
COMP_MUSIC_VOLUME = _comp_cfg.get("background_music_volume", 0.15)
COMP_BROLL_DURATION = _comp_cfg.get("broll_duration_each", 5)
COMP_CROSSFADE = _comp_cfg.get("crossfade_duration", 0.5)
COMP_TEXT_FONT = _comp_cfg.get("text_overlay_font", "Arial-Bold")
COMP_TEXT_COLOR = _comp_cfg.get("text_overlay_color", "#FFFFFF")
COMP_TEXT_BG = _comp_cfg.get("text_overlay_bg_color", "rgba(16, 25, 34, 0.7)")
COMP_INTRO_DURATION = _comp_cfg.get("intro_card_duration", 3)
COMP_OUTRO_DURATION = _comp_cfg.get("outro_card_duration", 5)

# B-roll directory
BROLL_DIR = PIPELINE_DIR / "broll"

# Duration targets (approximate word counts -- ~150 words per minute for TTS)
DURATION_WORD_TARGETS = {
    "short": 75,       # ~30 seconds (Shorts)
    "medium": 150,     # ~60 seconds
    "long": 450,       # ~3 minutes
    "extra-long": 900, # ~6 minutes
}

# HeyGen voice speed mapping by tone
HEYGEN_SPEED_BY_TONE = {
    "professional": HEYGEN_SPEED_DEFAULT,
    "casual": HEYGEN_SPEED_DEFAULT,
    "energetic": HEYGEN_SPEED_ENERGETIC,
    "educational": HEYGEN_SPEED_CALM,
    "storytelling": HEYGEN_SPEED_CALM,
}

# Override for Shorts (slightly faster pace keeps viewers engaged)
HEYGEN_SPEED_SHORTS_OVERRIDE = HEYGEN_SPEED_SHORTS


def load_api_keys():
    """Load API keys from the shared .env file."""
    if not ENV_PATH.exists():
        print(f"[ERROR] .env file not found at {ENV_PATH}")
        print("Expected keys: HEYGEN_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID")
        sys.exit(1)

    load_dotenv(ENV_PATH)

    keys = {
        "heygen_api_key": os.getenv("HEYGEN_API_KEY"),
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID", _el_cfg.get("voice_id", "HHOfU1tpMpxmIjLlpy34")),
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "google_client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "youtube_channel_id": os.getenv("YOUTUBE_CHANNEL_ID"),
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "perplexity_api_key": os.getenv("PERPLEXITY_API_KEY"),
    }

    return keys


# ---------------------------------------------------------------------------
# Script Writer  --  brand-config-driven with ElevenLabs v3 audio tags
# ---------------------------------------------------------------------------

class ScriptWriter:
    """
    Generates YouTube-optimised scripts with ElevenLabs v3 audio tags,
    natural pacing, and viewer-retention patterns. Entirely template-driven.

    Supports both long-form and Shorts-optimised script structures.
    """

    # -- Hooks: the first line the viewer hears (grab in 3-5 seconds) -------

    HOOKS = {
        "professional": [
            "Here's something most people overlook about {topic}.",
            "If you've been struggling with {topic}, this is for you.",
            "Let me break down {topic} in a way that actually makes sense.",
            "The biggest mistake people make with {topic}... and how to fix it.",
            "{topic}. Let's get straight to the point.",
        ],
        "casual": [
            "Okay, so... {topic}. Let's talk about it.",
            "What's up! Today we're diving into {topic}, and trust me, you'll want to hear this.",
            "So I've been thinking a lot about {topic} lately...",
            "Alright, real talk... {topic} is something everyone should know about.",
            "You ever wonder about {topic}? Yeah, me too. Let's figure it out.",
        ],
        "energetic": [
            "Let's GO! Today we're tackling {topic} and it's going to be awesome!",
            "Buckle up because {topic} is about to change the way you think!",
            "This is the video about {topic} that the internet NEEDS right now!",
            "I am SO excited to talk about {topic} today!",
            "Stop scrolling! {topic} is about to blow your mind!",
        ],
        "educational": [
            "Did you know that {topic} is one of the most misunderstood subjects out there?",
            "Today, I'm going to teach you everything you need to know about {topic}.",
            "By the end of this video, you'll understand {topic} better than most experts.",
            "Let me walk you through {topic}, step by step.",
            "Want to master {topic}? This is where you start.",
        ],
        "storytelling": [
            "So the other day, something happened that made me think about {topic}...",
            "Let me tell you a story about {topic} that changed my perspective.",
            "Picture this... you're sitting there, and suddenly {topic} becomes crystal clear.",
            "I wasn't going to make this video, but {topic} hit different recently.",
            "There's a story behind {topic} that nobody talks about.",
        ],
    }

    # -- Shorts-specific hooks (optimised for 3-second hold) ----------------

    SHORTS_HOOKS = {
        "professional": [
            "Stop. Here's the {topic} trick nobody taught you.",
            "One {topic} tip that changed everything.",
            "{topic} in 60 seconds. Watch this.",
        ],
        "casual": [
            "Bro, wait... this {topic} hack is insane.",
            "POV: you just discovered {topic}.",
            "Tell me you don't know about {topic} without telling me.",
        ],
        "energetic": [
            "{topic}! Let's GO!",
            "You NEED to see this {topic} trick!",
            "This {topic} secret is going to blow up!",
        ],
        "educational": [
            "Learn {topic} in under a minute.",
            "Quick {topic} lesson you'll actually remember.",
            "Here's the {topic} cheat sheet nobody shares.",
        ],
        "storytelling": [
            "The moment {topic} clicked for me...",
            "I wish someone showed me this about {topic} sooner.",
            "This changed how I see {topic} forever.",
        ],
    }

    # -- Intros: brief channel mention after the hook -----------------------

    INTROS = [
        "I'm Richard Abreu, and on this channel we break things down so they actually click.",
        "Welcome back to the channel. I'm Richard, and let's get into it.",
        "If you're new here, I'm Richard Abreu. Hit subscribe so you don't miss the next one.",
        "I'm Richard Abreu. If you find this helpful, drop a like. It helps more than you know.",
        "Richard Abreu here. Let's not waste any time.",
    ]

    SERIES_INTROS = [
        "This is part of my {series} series, so if you haven't seen the other episodes, I'll link them below.",
        "Welcome to another episode of {series}. Let's keep building on what we've covered.",
        "We're back with {series}. If you've been following along, you know the drill.",
    ]

    # -- Transitions: connecting script sections smoothly -------------------

    TRANSITIONS = [
        "Now, here's where it gets interesting...",
        "So, moving on...",
        "Here's the thing...",
        "Okay, next up...",
        "And this is the part most people miss...",
        "Stay with me here...",
        "Now let me show you...",
        "This brings us to the next point...",
        "Alright, so...",
        "But wait, there's more to it...",
        "Let me break this down further...",
        "Pay attention to this part...",
    ]

    # -- Engagement questions: keep viewers watching ------------------------

    ENGAGEMENT_QUESTIONS = [
        "Have you ever experienced this?",
        "Does this sound familiar?",
        "Want to know the best part?",
        "Can you guess what happens next?",
        "Let me know in the comments if you agree.",
        "Sound good so far?",
        "Are you following along?",
        "Makes sense, right?",
        "Pretty cool, right?",
        "What do you think?",
    ]

    # -- CTAs: call-to-action closers --------------------------------------

    CTAS = [
        (
            "If this video helped you out, smash that like button and subscribe. "
            "Drop a comment below telling me what you want to see next. "
            "I'll see you in the next one... peace."
        ),
        (
            "That's it for today. If you got value from this, hit subscribe and "
            "ring the bell so you don't miss the next video. "
            "Leave a comment... I read every single one. See you next time."
        ),
        (
            "Thanks for watching all the way through. Seriously, it means a lot. "
            "Like, subscribe, and share this with someone who needs to hear it. "
            "Until next time... take care."
        ),
        (
            "And that's a wrap. If you enjoyed this, you'll love what's coming next. "
            "Subscribe so you're the first to know. "
            "Drop your thoughts in the comments. I'll catch you later."
        ),
    ]

    # Shorts CTAs (shorter, punchier)
    SHORTS_CTAS = [
        "Follow for more. Drop a comment if this helped.",
        "Like and subscribe for daily tips like this.",
        "Save this for later. You'll thank me.",
        "Share this with someone who needs to hear it.",
    ]

    # -- Recap starters ----------------------------------------------------

    RECAP_STARTERS = [
        "So let's quickly recap what we covered.",
        "To sum it all up...",
        "Alright, here's the quick summary.",
        "Let's wrap this up with the key takeaways.",
        "Before we go, let me run through the highlights.",
    ]

    # -- Content body sentence templates (topic-agnostic) ------------------

    BODY_SENTENCE_TEMPLATES = [
        "The first thing you need to understand about {topic} is that it's all about {aspect}.",
        "When it comes to {topic}, most people focus on the wrong things.",
        "Here's a simple way to think about {aspect} in the context of {topic}.",
        "One of the biggest myths about {topic} is that {myth}. That's just not true.",
        "The key to {topic} really comes down to {aspect}.",
        "If you remember nothing else from this video, remember this about {topic}.",
        "What I've learned from working with {topic} is that {insight}.",
        "A lot of people ask me about {topic}, and my answer is always the same.",
        "The secret to {topic} is simpler than you think.",
        "Once you understand {aspect}, everything else about {topic} falls into place.",
        "Think of {topic} like this...",
        "I made so many mistakes with {topic} before I figured out {insight}.",
        "This is the framework I use for {topic} every single time.",
        "You don't need to be an expert to get started with {topic}.",
        "The difference between good and great when it comes to {topic} is {aspect}.",
        "Let me give you a real-world example of {topic} in action.",
        "Here's what nobody tells you about {topic}.",
        "I wish someone had told me this about {topic} years ago.",
        "If you're just starting out with {topic}, start here.",
        "The number one rule of {topic}? {insight}.",
    ]

    # -- Generic fill-in elements -----------------------------------------

    GENERIC_ASPECTS = [
        "consistency", "the fundamentals", "having a clear plan",
        "understanding your audience", "taking action", "simplicity",
        "patience", "the right mindset", "practice", "strategy",
        "timing", "preparation", "attention to detail", "focus",
    ]

    GENERIC_MYTHS = [
        "you need to be talented to succeed",
        "it takes years to see results",
        "you need expensive tools",
        "there's only one right way to do it",
        "it's too late to start",
        "you have to do everything yourself",
    ]

    GENERIC_INSIGHTS = [
        "consistency beats perfection every time",
        "start before you're ready",
        "simple beats complicated",
        "the basics matter more than the advanced stuff",
        "progress is better than perfection",
        "showing up is half the battle",
    ]

    # -- Pillar-specific body templates (more educational, less generic) ----

    PILLAR_BODY_TEMPLATES = {
        "art": [
            "The first tool you'll want to grab is {tool}. It's going to be your best friend for {topic}.",
            "Here's the technique: start with {step1}, then layer in {step2}. Most people skip that second step.",
            "The color trick here is to use complementary colors. So if you're working with blues, add a touch of orange.",
            "In Affinity Designer, hit {shortcut} to access this. It saves so much time.",
            "When I first started with {topic}, I was doing everything manually. Then I discovered this workflow.",
            "The resolution matters. For print, go 300 DPI minimum. For web, 72 DPI saves file size.",
            "Layer management is everything. Name your layers, group them, use masks instead of erasing.",
            "Pro tip: zoom to 100% before finalizing. What looks good at 50% might look rough at full scale.",
        ],
        "tech": [
            "First, open your terminal and run this command. I'll put it in the description below.",
            "The API endpoint you need is right here. You'll send a POST request with your key in the header.",
            "Here's the JSON structure you need. Keep it simple — just the required fields to start.",
            "The most common error you'll hit is a 401 Unauthorized. That means your API key isn't set correctly.",
            "For authentication, you've got two options: API key in the header, or OAuth2 for more security.",
            "Let me show you the n8n workflow. You drag a webhook trigger here, connect it to an HTTP request node.",
            "The rate limit on this API is usually around 100 requests per minute. So batch your calls.",
            "Version your .env files. Never commit API keys to git. Use environment variables instead.",
        ],
        "business": [
            "The first thing I did was validate the idea before spending any money. Here's how you do that.",
            "On Shopify, go to Settings, then Shipping. This is where most new store owners mess up.",
            "My pricing formula is simple: production cost times 3, then round to a .99 price point.",
            "For print-on-demand, the margins are thinner than you think. I typically see 30 to 40 percent.",
            "SEO is free marketing. Optimize your product titles with keywords people actually search for.",
            "The email list is your most valuable asset. Own your audience, don't rent it from social media.",
            "Track your conversion rate weekly. If it drops below 2 percent, something needs fixing.",
            "Start with one sales channel. Master it. Then expand. Don't spread yourself thin on day one.",
        ],
        "wellness": [
            "What most people don't realize is that creativity and mental health are deeply connected.",
            "The morning routine that changed everything for me starts with just 5 minutes of stillness.",
            "As a veteran, the transition to civilian life taught me more about resilience than anything else.",
            "Here's my journaling prompt: 'What would I create today if I had no fear?'",
            "The 2-minute reset: close your eyes, take 3 deep breaths, then write down one intention.",
            "Burnout is real for creators. The fix isn't working harder — it's working with more intention.",
            "I schedule creative blocks like meetings. If it's not on the calendar, it doesn't happen.",
            "The best investment I made wasn't a tool or a course. It was protecting my creative energy.",
        ],
        "products": [
            "This design started as a sketch on my iPad. Let me show you how it became a product.",
            "The color palette for this collection was inspired by {inspiration}.",
            "On Printful, I tested this on 3 different materials before picking the final one.",
            "The mockup is important, but the real test is ordering a sample. Always order samples.",
            "This is our best seller this month. I think it resonates because {reason}.",
            "Limited edition means limited — once it's gone, it's gone. That's what makes it special.",
            "I design everything in Affinity Designer, export at 300 DPI, and upload directly to Printful.",
            "Behind every product is a story. This one is about {story}.",
        ],
    }

    PILLAR_FILL_ELEMENTS = {
        "art": {
            "tools": ["the Pen Tool", "the Node Tool", "the Shape Builder", "the Gradient Tool",
                      "the Color Picker", "Pixel Persona", "the Export Persona"],
            "shortcuts": ["Ctrl+G to group", "V to switch to Move", "A for the Node Tool",
                          "Ctrl+Shift+K for Place", "Space to pan"],
            "steps": ["blocking in the basic shapes", "refining the curves",
                      "adding the color fill", "applying the final effects"],
        },
        "tech": {
            "tools": ["n8n", "Postman", "VS Code", "the terminal", "Chrome DevTools"],
            "formats": ["JSON", "XML", "CSV"],
            "methods": ["GET", "POST", "PUT", "DELETE"],
        },
        "business": {
            "metrics": ["conversion rate", "average order value", "customer lifetime value",
                        "return rate", "traffic sources"],
            "platforms": ["Shopify", "Etsy", "Instagram", "TikTok Shop", "Amazon"],
        },
        "wellness": {
            "practices": ["journaling", "meditation", "breathwork", "creative visualization",
                          "morning walks", "digital detox"],
        },
        "products": {
            "inspirations": ["nature", "urban architecture", "vintage typography",
                             "abstract patterns", "cultural heritage"],
            "reasons": ["it captures a feeling people relate to",
                        "the colors are calming and versatile",
                        "it tells a story without words"],
            "stories": ["my first deployment", "a sunset I photographed in Hawaii",
                        "a conversation with my grandmother"],
        },
    }

    def __init__(self, topic, tone="professional", duration="medium",
                 series=None, pillar=None, is_shorts=False):
        self.topic = topic
        self.tone = tone if tone in self.HOOKS else "professional"
        self.duration = duration
        self.series = series
        self.pillar = pillar
        self.is_shorts = is_shorts or duration == "short"
        self.target_words = DURATION_WORD_TARGETS.get(duration, 150)

        # If pillar specified and no series, pick one from the pillar
        if pillar and not series and pillar in CONTENT_PILLARS:
            pillar_data = CONTENT_PILLARS[pillar]
            self.series = random.choice(pillar_data.get("series", [None]))

    def _pick(self, collection):
        """Pick a random item from a list."""
        return random.choice(collection)

    def _fill(self, template, **extra):
        """Fill a template string with topic and random/pillar-specific elements."""
        pillar_elems = self.PILLAR_FILL_ELEMENTS.get(self.pillar, {})

        return template.format(
            topic=self.topic,
            aspect=extra.get("aspect", self._pick(self.GENERIC_ASPECTS)),
            myth=extra.get("myth", self._pick(self.GENERIC_MYTHS)),
            insight=extra.get("insight", self._pick(self.GENERIC_INSIGHTS)),
            series=self.series or "",
            n=extra.get("n", random.randint(3, 5)),
            tool=self._pick(pillar_elems.get("tools", ["this tool"])),
            shortcut=self._pick(pillar_elems.get("shortcuts", ["this shortcut"])),
            step1=self._pick(pillar_elems.get("steps", ["the basics"])),
            step2=self._pick(pillar_elems.get("steps", ["the details"])),
            inspiration=self._pick(pillar_elems.get("inspirations", ["my surroundings"])),
            reason=self._pick(pillar_elems.get("reasons", ["it resonates"])),
            story=self._pick(pillar_elems.get("stories", ["a personal moment"])),
        )

    def generate(self):
        """
        Build a complete script with emotion tags and pacing cues.

        Returns a dict with:
            - raw_text: plain text for HeyGen TTS
            - annotated_text: text with ElevenLabs v3 audio tags
            - sections: list of dicts with section name and text
            - metadata: topic, tone, duration, word count, timestamp
        """
        if self.is_shorts:
            return self._generate_shorts()
        return self._generate_long_form()

    def _generate_long_form(self):
        """Generate a long-form YouTube script."""
        sections = []

        # 1. Hook
        hook = self._fill(self._pick(self.HOOKS[self.tone]))
        sections.append({"name": "hook", "text": hook})

        # 2. Intro
        intro_parts = [self._pick(self.INTROS)]
        if self.series:
            intro_parts.append(self._fill(self._pick(self.SERIES_INTROS)))
        intro = " ".join(intro_parts)
        sections.append({"name": "intro", "text": intro})

        # 3. Open loop (retention tactic from brand config)
        open_loops = RETENTION_TACTICS.get("open_loops", [])
        if open_loops:
            loop = self._fill(self._pick(open_loops))
            sections.append({"name": "open_loop", "text": loop})

        # 4. Body -- scale number of points to target duration
        if self.duration == "medium":
            num_points = 3
        elif self.duration == "long":
            num_points = 5
        else:
            num_points = 7

        used_templates = []
        for i in range(num_points):
            body_lines = []

            # Transition (skip before the very first point)
            if i > 0:
                body_lines.append(self._pick(self.TRANSITIONS))

            # Pattern interrupt from brand config every 2-3 points
            pattern_interrupts = RETENTION_TACTICS.get("pattern_interrupts", [])
            if i > 0 and i % 2 == 0 and pattern_interrupts:
                body_lines.append(self._pick(pattern_interrupts))

            # Pick body sentences per point depending on duration
            # Prefer pillar-specific templates (more educational) over generic ones
            sentences_per_point = 2 if self.duration == "medium" else 3
            pillar_templates = self.PILLAR_BODY_TEMPLATES.get(self.pillar, [])

            # Mix: 1 pillar-specific + rest generic for variety
            available_pillar = [t for t in pillar_templates if t not in used_templates]
            available_generic = [t for t in self.BODY_SENTENCE_TEMPLATES if t not in used_templates]

            if available_pillar and sentences_per_point > 1:
                # One pillar-specific, rest generic
                p_chosen = random.sample(available_pillar, min(1, len(available_pillar)))
                remaining = sentences_per_point - len(p_chosen)
                if len(available_generic) < remaining:
                    available_generic = self.BODY_SENTENCE_TEMPLATES[:]
                g_chosen = random.sample(available_generic, min(remaining, len(available_generic)))
                chosen = p_chosen + g_chosen
            else:
                available = available_generic if available_generic else self.BODY_SENTENCE_TEMPLATES[:]
                chosen = random.sample(available, min(sentences_per_point, len(available)))

            used_templates.extend(chosen)

            for tpl in chosen:
                body_lines.append(self._fill(tpl))

            # Engagement question every other point
            if i % 2 == 1:
                body_lines.append(self._pick(self.ENGAGEMENT_QUESTIONS))

            # Engagement prompt from brand config
            engagement_prompts = RETENTION_TACTICS.get("engagement_prompts", [])
            if i == num_points - 2 and engagement_prompts:
                body_lines.append(self._pick(engagement_prompts))

            sections.append({
                "name": f"point_{i + 1}",
                "text": " ".join(body_lines),
            })

        # 5. Recap
        recap = self._pick(self.RECAP_STARTERS)
        recap_bullets = []
        for i in range(min(num_points, 3)):
            recap_bullets.append(
                f"Number {i + 1}... {self._fill('{aspect} is essential for {topic}.', aspect=self._pick(self.GENERIC_ASPECTS))}"
            )
        recap_full = recap + " " + " ".join(recap_bullets)
        sections.append({"name": "recap", "text": recap_full})

        # 6. CTA
        cta = self._pick(self.CTAS)
        sections.append({"name": "cta", "text": cta})

        return self._build_output(sections)

    def _generate_shorts(self):
        """Generate a YouTube Shorts-optimised script (30-60s, punchy)."""
        sections = []

        # 1. Shorts hook (3-second hold, pattern interrupt style)
        shorts_hooks = self.SHORTS_HOOKS.get(self.tone, self.SHORTS_HOOKS["professional"])
        hook = self._fill(self._pick(shorts_hooks))
        sections.append({"name": "hook", "text": hook})

        # 2. Body -- 2-3 quick points, no intro needed for Shorts
        num_points = 2 if self.target_words <= 75 else 3
        used_templates = []

        for i in range(num_points):
            body_lines = []
            # Prefer pillar-specific templates for Shorts (more specific = more valuable)
            pillar_templates = self.PILLAR_BODY_TEMPLATES.get(self.pillar, [])
            available_pillar = [t for t in pillar_templates if t not in used_templates]
            available_generic = [t for t in self.BODY_SENTENCE_TEMPLATES if t not in used_templates]

            if available_pillar:
                chosen = random.sample(available_pillar, 1)
            elif available_generic:
                chosen = random.sample(available_generic, 1)
            else:
                chosen = random.sample(self.BODY_SENTENCE_TEMPLATES, 1)

            used_templates.extend(chosen)
            body_lines.append(self._fill(chosen[0]))

            sections.append({
                "name": f"point_{i + 1}",
                "text": " ".join(body_lines),
            })

        # 3. Shorts CTA (short and punchy)
        cta = self._pick(self.SHORTS_CTAS)
        sections.append({"name": "cta", "text": cta})

        return self._build_output(sections)

    def _build_output(self, sections):
        """Assemble raw text, annotated text, and metadata from sections."""
        raw_lines = [s["text"] for s in sections]
        raw_text = "\n\n".join(raw_lines)

        # Annotated version with ElevenLabs v3 audio tags
        annotated = self._annotate_v3(sections)

        word_count = len(raw_text.split())

        metadata = {
            "topic": self.topic,
            "tone": self.tone,
            "duration": self.duration,
            "series": self.series,
            "pillar": self.pillar,
            "is_shorts": self.is_shorts,
            "word_count": word_count,
            "estimated_seconds": round(word_count / 2.5),
            "generated_at": datetime.now().isoformat(),
        }

        return {
            "raw_text": raw_text,
            "annotated_text": annotated,
            "sections": sections,
            "metadata": metadata,
        }

    def _annotate_v3(self, sections):
        """
        Produce ElevenLabs v3 audio-tag annotated script.

        Uses actual v3 audio tags that the model interprets:
            [excited] - higher energy, enthusiasm
            [calm] - lower energy, measured
            [whispers] - whispered delivery
            [sighs] - audible sigh
            [laughs] - light laughter
            [pause] - natural pause (via ellipsis)

        Punctuation controls:
            ... (ellipsis) - natural pause / trailing off
            CAPS - emphasis on words
            ! - excitement / energy
            ? - curiosity / engagement
        """
        lines = []

        for section in sections:
            name = section["name"]
            text = section["text"]

            if name == "hook":
                if self.tone == "energetic":
                    lines.append(f"[excited] {text}")
                elif self.tone == "storytelling":
                    lines.append(f"[sighs] {text}")
                elif self.tone == "casual":
                    lines.append(f"[laughs] {text}")
                else:
                    lines.append(f"[excited] {text}")
                lines.append("...")

            elif name == "intro":
                lines.append(f"[calm] {text}")
                lines.append("......")

            elif name == "open_loop":
                lines.append(f"[whispers] {text}")
                lines.append("...")

            elif name.startswith("point_"):
                sentences = re.split(r'(?<=[.!?])\s+', text)
                annotated_sentences = []
                for j, sent in enumerate(sentences):
                    if sent.strip() == "...":
                        annotated_sentences.append("...")
                    elif "?" in sent:
                        annotated_sentences.append(f"[excited] {sent}")
                    elif j == 0:
                        annotated_sentences.append(f"[calm] {sent}")
                    else:
                        annotated_sentences.append(sent)
                lines.append(" ".join(annotated_sentences))
                lines.append("...")

            elif name == "recap":
                lines.append("......")
                lines.append(f"[calm] {text}")
                lines.append("...")

            elif name == "cta":
                lines.append("......")
                lines.append(f"[excited] {text}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SEO Metadata Generator
# ---------------------------------------------------------------------------

class SEOGenerator:
    """Generates YouTube SEO metadata from brand_config.json templates."""

    def __init__(self, topic, pillar=None, tone=None):
        self.topic = topic
        self.pillar = pillar
        self.tone = tone

    def generate(self):
        """Generate title options, description, and tags."""
        titles = self._generate_titles()
        description = self._generate_description()
        tags = self._generate_tags()

        return {
            "titles": titles,
            "description": description,
            "tags": tags,
            "topic": self.topic,
            "pillar": self.pillar,
        }

    def _generate_titles(self):
        """Generate 5 title options from SEO templates."""
        formulas = SEO_TEMPLATES.get("title_formulas", [])
        if not formulas:
            return [f"{self.topic} - Richard Abreu"]

        titles = []
        year = datetime.now().year
        for formula in random.sample(formulas, min(5, len(formulas))):
            title = formula.replace("{topic}", self.topic)
            title = title.replace("{year}", str(year))
            title = title.replace("{number}", str(random.choice([3, 5, 7, 10])))
            title = title.replace("{result}", "transformed my workflow")
            title = title.replace("{audience}", "creators")
            titles.append(title)
        return titles

    def _generate_description(self):
        """Generate a YouTube description from the template."""
        template = SEO_TEMPLATES.get("description_template", "")
        if not template:
            return f"Video about {self.topic} by Richard Abreu."

        # Build hook sentence
        hooks = HOOK_LIBRARY.get("curiosity_gap", [])
        hook_sentence = ""
        if hooks:
            hook_sentence = hooks[0].replace("{topic}", self.topic).replace("{result}", "approach everything")

        desc = template.replace("{hook_sentence}", hook_sentence)
        desc = desc.replace("{topic_summary}", f"everything you need to know about {self.topic}")
        desc = desc.replace("{chapters}", "0:00 Intro\n0:15 Key Concepts\n1:00 Deep Dive\n2:30 Takeaways")
        desc = desc.replace("{hashtags}", self._hashtag_string())

        return desc

    def _generate_tags(self):
        """Generate tags combining default + pillar-specific."""
        tags = list(SEO_TEMPLATES.get("default_tags", []))

        # Add topic as tag
        tags.append(self.topic)

        # Add pillar-specific tags
        if self.pillar and self.pillar in CONTENT_PILLARS:
            pillar_tags = CONTENT_PILLARS[self.pillar].get("tags", [])
            tags.extend(pillar_tags)

        # Deduplicate while preserving order
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag.lower() not in seen:
                seen.add(tag.lower())
                unique_tags.append(tag)

        return unique_tags[:30]  # YouTube allows up to 500 chars, ~30 tags

    def _hashtag_string(self):
        """Build hashtag string for description (pillar-specific only, base tags are in template)."""
        tags = []
        if self.pillar and self.pillar in CONTENT_PILLARS:
            for tag in CONTENT_PILLARS[self.pillar].get("tags", [])[:4]:
                tags.append(f"#{tag.replace(' ', '')}")
        return " ".join(tags)


# ---------------------------------------------------------------------------
# HeyGen Video Generation
# ---------------------------------------------------------------------------

class HeyGenClient:
    """Handles video generation and polling via the HeyGen v2 API."""

    POLL_INTERVAL = 15
    MAX_POLL_TIME = 600

    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def upload_audio(self, audio_path):
        """
        Upload an audio file to HeyGen's asset storage for lip-sync.

        Args:
            audio_path: Path to an .mp3 or .wav audio file.

        Returns:
            Asset URL string on success, None on failure.
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            print(f"[HeyGen] Audio file not found: {audio_path}")
            return None

        content_type = "audio/mpeg" if audio_file.suffix == ".mp3" else "audio/wav"
        size_mb = audio_file.stat().st_size / (1024 * 1024)
        print(f"[HeyGen] Uploading audio asset: {audio_file.name} ({size_mb:.2f} MB)")

        try:
            with open(audio_file, "rb") as f:
                resp = requests.post(
                    HEYGEN_ASSET_UPLOAD_URL,
                    headers={
                        "X-Api-Key": self.api_key,
                        "Content-Type": content_type,
                    },
                    data=f,
                    timeout=120,
                )
                resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[HeyGen] Audio upload failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[HeyGen] Response: {exc.response.text}")
            return None

        data = resp.json()
        asset_url = data.get("data", {}).get("url") or data.get("url")
        if not asset_url:
            # Try alternate response formats
            asset_url = data.get("data", {}).get("asset_url") or data.get("data", {}).get("file_url")

        if asset_url:
            print(f"[HeyGen] Audio asset uploaded: {asset_url[:80]}...")
            return asset_url
        else:
            print(f"[HeyGen] Upload response (no URL found): {json.dumps(data, indent=2)}")
            return None

    def generate_video_with_audio(self, audio_path, title="video",
                                  video_format="landscape", tone="professional",
                                  test_mode=False):
        """
        Generate a lip-synced avatar video using pre-recorded audio.

        This produces much more natural results than HeyGen's built-in TTS
        because the audio comes from ElevenLabs voice clone.

        Args:
            audio_path: Path to .mp3 audio file (from ElevenLabs).
            title: Used for the downloaded filename.
            video_format: "landscape", "shorts", or "square".
            tone: Tone (affects avatar emotion).
            test_mode: If True, use HeyGen test mode.

        Returns:
            Path to the downloaded video file, or None on failure.
        """
        # Step 1: Upload audio to HeyGen
        audio_url = self.upload_audio(audio_path)
        if not audio_url:
            print("[HeyGen] Cannot generate lip-sync video without audio upload.")
            return None

        # Step 2: Build single scene with audio mode
        fmt = VIDEO_FORMATS.get(video_format, VIDEO_FORMATS["landscape"])
        emotion = HEYGEN_EMOTION_BY_TONE.get(tone)

        scene = self._make_scene(text=None, speed=None, emotion=emotion, audio_url=audio_url)

        payload = {
            "video_inputs": [scene],
            "dimension": {
                "width": fmt["width"],
                "height": fmt["height"],
            },
            "test": test_mode,
        }

        if HEYGEN_CAPTION_ENABLED:
            payload["caption"] = True

        print(f"[HeyGen] Format: {video_format} ({fmt['width']}x{fmt['height']})")
        print(f"[HeyGen] Mode: Audio lip-sync (ElevenLabs voice)")
        if emotion:
            print(f"[HeyGen] Emotion: {emotion}")
        print(f"[HeyGen] Captions: {'ON' if HEYGEN_CAPTION_ENABLED else 'OFF'}")
        print("[HeyGen] Submitting lip-sync video generation request...")

        try:
            resp = requests.post(
                HEYGEN_GENERATE_URL,
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[HeyGen] Request failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[HeyGen] Response body: {exc.response.text}")
            return None

        data = resp.json()
        if data.get("error"):
            print(f"[HeyGen] API error: {data['error']}")
            return None

        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            print(f"[HeyGen] No video_id in response: {json.dumps(data, indent=2)}")
            return None

        print(f"[HeyGen] Video ID: {video_id}")
        print(f"[HeyGen] Polling for completion (max {self.MAX_POLL_TIME}s)...")

        return self._poll_and_download(video_id, title)

    def generate_video(self, script_text, title="video",
                       video_format="landscape", tone="professional",
                       test_mode=False, is_shorts=False):
        """
        Submit a video generation job to HeyGen (text-to-speech mode).

        Args:
            script_text: The plain-text script for TTS.
            title: Used for the downloaded filename.
            video_format: "landscape", "shorts", or "square".
            tone: Script tone (affects voice speed and emotion).
            test_mode: If True, use HeyGen test mode (no credits).
            is_shorts: If True, use faster pace for Shorts.

        Returns:
            Path to the downloaded video file, or None on failure.
        """
        fmt = VIDEO_FORMATS.get(video_format, VIDEO_FORMATS["landscape"])
        speed = HEYGEN_SPEED_BY_TONE.get(tone, HEYGEN_SPEED_DEFAULT)
        if is_shorts:
            speed = HEYGEN_SPEED_SHORTS_OVERRIDE
        emotion = HEYGEN_EMOTION_BY_TONE.get(tone)

        # Split into scenes for multi-scene support
        scenes = self._build_scenes(script_text, speed, emotion)

        payload = {
            "video_inputs": scenes,
            "dimension": {
                "width": fmt["width"],
                "height": fmt["height"],
            },
            "test": test_mode,
        }

        # Enable captions if configured
        if HEYGEN_CAPTION_ENABLED:
            payload["caption"] = True

        print(f"[HeyGen] Format: {video_format} ({fmt['width']}x{fmt['height']})")
        print(f"[HeyGen] Voice speed: {speed}x")
        if emotion:
            print(f"[HeyGen] Emotion: {emotion}")
        print(f"[HeyGen] Captions: {'ON' if HEYGEN_CAPTION_ENABLED else 'OFF'}")
        print(f"[HeyGen] Scenes: {len(scenes)}")
        print("[HeyGen] Submitting video generation request...")

        try:
            resp = requests.post(
                HEYGEN_GENERATE_URL,
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[HeyGen] Request failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[HeyGen] Response body: {exc.response.text}")
            return None

        data = resp.json()
        if data.get("error"):
            print(f"[HeyGen] API error: {data['error']}")
            return None

        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            print(f"[HeyGen] No video_id in response: {json.dumps(data, indent=2)}")
            return None

        print(f"[HeyGen] Video ID: {video_id}")
        print(f"[HeyGen] Polling for completion (max {self.MAX_POLL_TIME}s)...")

        return self._poll_and_download(video_id, title)

    def _build_scenes(self, script_text, speed, emotion=None):
        """
        Build HeyGen scene array from script text.

        Splits on double-newlines to create multiple scenes with the same
        avatar but varied background colours for visual interest.
        Enforces 4800-char limit per scene (HeyGen max is 5000).
        """
        MAX_SCENE_CHARS = 4800  # Leave buffer below HeyGen's 5000 limit
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]

        # If total text is short enough, single scene
        full_text = "\n\n".join(paragraphs)
        if len(full_text) <= MAX_SCENE_CHARS:
            return [self._make_scene(full_text, speed, emotion)]

        # Group paragraphs into scenes respecting the char limit
        bg_keys = list(HEYGEN_BACKGROUNDS.keys()) if HEYGEN_BACKGROUNDS else ["default"]
        scenes = []
        current_chunk = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para) + (2 if current_chunk else 0)  # +2 for separator
            if current_len + para_len > MAX_SCENE_CHARS and current_chunk:
                # Flush current chunk as a scene
                text = " ".join(current_chunk)
                bg_key = bg_keys[len(scenes) % len(bg_keys)]
                bg = HEYGEN_BACKGROUNDS.get(bg_key, {"type": "color", "value": BACKGROUND_COLOR})
                scenes.append(self._make_scene(text, speed, emotion, bg))
                current_chunk = []
                current_len = 0
            current_chunk.append(para)
            current_len += para_len

        # Flush remaining
        if current_chunk:
            text = " ".join(current_chunk)
            bg_key = bg_keys[len(scenes) % len(bg_keys)]
            bg = HEYGEN_BACKGROUNDS.get(bg_key, {"type": "color", "value": BACKGROUND_COLOR})
            scenes.append(self._make_scene(text, speed, emotion, bg))

        return scenes if scenes else [self._make_scene(script_text[:MAX_SCENE_CHARS], speed, emotion)]

    def _make_scene(self, text, speed, emotion=None, background=None, audio_url=None):
        """Create a single HeyGen scene dict with text TTS or audio lip-sync."""
        if audio_url:
            # Audio lip-sync mode: avatar mouths along to pre-recorded audio
            voice_config = {
                "type": "audio",
                "audio_url": audio_url,
            }
        else:
            # Text-to-speech mode: HeyGen generates speech from text
            voice_config = {
                "type": "text",
                "input_text": text,
                "voice_id": HEYGEN_VOICE_ID,
                "speed": speed,
            }
        if emotion:
            voice_config["emotion"] = emotion

        bg = background or {"type": "color", "value": BACKGROUND_COLOR}

        return {
            "character": {
                "type": "avatar",
                "avatar_id": HEYGEN_AVATAR_ID,
                "avatar_style": HEYGEN_AVATAR_STYLE,
            },
            "voice": voice_config,
            "background": bg,
        }

    def _poll_and_download(self, video_id, title):
        """Poll the status endpoint until the video is ready, then download."""
        elapsed = 0

        while elapsed < self.MAX_POLL_TIME:
            time.sleep(self.POLL_INTERVAL)
            elapsed += self.POLL_INTERVAL

            try:
                resp = requests.get(
                    HEYGEN_STATUS_URL,
                    headers=self.headers,
                    params={"video_id": video_id},
                    timeout=30,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                print(f"[HeyGen] Poll error: {exc}")
                continue

            data = resp.json().get("data", {})
            status = data.get("status", "unknown")
            print(f"[HeyGen] Status: {status} ({elapsed}s elapsed)")

            if status == "completed":
                video_url = data.get("video_url")
                if not video_url:
                    print("[HeyGen] Completed but no video_url found.")
                    return None
                return self._download(video_url, title)

            elif status == "failed":
                error_msg = data.get("error", "Unknown error")
                print(f"[HeyGen] Video generation failed: {error_msg}")
                return None

        print("[HeyGen] Timed out waiting for video completion.")
        return None

    def _download(self, url, title):
        """Download the finished video to ~/Downloads/."""
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.mp4"
        filepath = DOWNLOADS_DIR / filename

        print(f"[HeyGen] Downloading video to {filepath}...")
        try:
            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"[HeyGen] Download complete: {filepath} ({size_mb:.1f} MB)")
            return str(filepath)

        except requests.RequestException as exc:
            print(f"[HeyGen] Download failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# ElevenLabs Audio Generation
# ---------------------------------------------------------------------------

class ElevenLabsClient:
    """Generates audio from text using ElevenLabs TTS API with v3 audio tags."""

    def __init__(self, api_key, voice_id):
        self.api_key = api_key
        self.voice_id = voice_id

    def generate_audio(self, text, title="audio", tone="professional",
                       stability=None, similarity_boost=None, style=None,
                       output_format="mp3_44100_128"):
        """
        Generate speech audio from text via ElevenLabs.

        If tone is specified and a matching preset exists in brand_config,
        those voice settings are used automatically.
        """
        # Use brand config presets if available
        preset = ELEVENLABS_PRESETS.get(tone, {})
        _stability = stability if stability is not None else preset.get("stability", 0.5)
        _similarity = similarity_boost if similarity_boost is not None else preset.get("similarity_boost", 0.75)
        _style = style if style is not None else preset.get("style", 0.3)
        _speaker_boost = preset.get("use_speaker_boost", True)

        # Clean text: keep v3 audio tags but remove old-style annotation brackets
        # v3 tags like [excited], [whispers], [sighs], [laughs] are kept as-is
        # Old annotation pairs like [/excited] are stripped
        clean_text = re.sub(r'\[/(?:pause|long pause|emphasis|excited|calm)\]', '', text)
        clean_text = re.sub(r'\[(?:pause|long pause)\]', '...', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        url = f"{ELEVENLABS_TTS_URL}/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": clean_text,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": _stability,
                "similarity_boost": _similarity,
                "style": _style,
                "use_speaker_boost": _speaker_boost,
            },
        }

        print(f"[ElevenLabs] Model: {ELEVENLABS_MODEL}")
        print(f"[ElevenLabs] Tone preset: {tone}")
        print(f"[ElevenLabs] Settings: stability={_stability}, similarity={_similarity}, style={_style}")

        # Auto-chunk if text exceeds ElevenLabs 10K char limit
        MAX_CHARS = 9500  # Leave buffer below 10K limit
        if len(clean_text) > MAX_CHARS:
            return self._generate_audio_chunked(
                clean_text, title, url, headers, payload, MAX_CHARS
            )

        print("[ElevenLabs] Generating audio...")

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[ElevenLabs] Request failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[ElevenLabs] Response: {exc.response.text}")
            return None

        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.mp3"
        filepath = DOWNLOADS_DIR / filename

        with open(filepath, "wb") as f:
            f.write(resp.content)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"[ElevenLabs] Audio saved: {filepath} ({size_mb:.2f} MB)")
        return str(filepath)

    def _generate_audio_chunked(self, text, title, url, headers, payload_template, max_chars):
        """Split long text into chunks and generate audio for each, saving as separate files."""
        # Split at sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = []
        current_len = 0

        for sent in sentences:
            if current_len + len(sent) + 1 > max_chars and current:
                chunks.append(" ".join(current))
                current = []
                current_len = 0
            current.append(sent)
            current_len += len(sent) + 1

        if current:
            chunks.append(" ".join(current))

        print(f"[ElevenLabs] Text is {len(text)} chars — splitting into {len(chunks)} chunks")

        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_parts = []

        for i, chunk in enumerate(chunks):
            part_num = i + 1
            print(f"[ElevenLabs] Generating part {part_num}/{len(chunks)} ({len(chunk)} chars)...")
            chunk_payload = dict(payload_template)
            chunk_payload["text"] = chunk

            try:
                resp = requests.post(url, headers=headers, json=chunk_payload, timeout=180)
                resp.raise_for_status()
            except requests.RequestException as exc:
                print(f"[ElevenLabs] Part {part_num} failed: {exc}")
                if hasattr(exc, "response") and exc.response is not None:
                    print(f"[ElevenLabs] Response: {exc.response.text}")
                continue

            filename = f"{safe_title}_part{part_num}_{timestamp}.mp3"
            filepath = DOWNLOADS_DIR / filename
            with open(filepath, "wb") as f:
                f.write(resp.content)
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"[ElevenLabs] Part {part_num} saved: {filepath} ({size_mb:.2f} MB)")
            saved_parts.append(str(filepath))

        if saved_parts:
            print(f"[ElevenLabs] All {len(saved_parts)} parts saved. Combine in your editor.")
            return saved_parts[0]  # Return first part path
        return None

    def generate_music(self, prompt, duration_ms=30000, title="music"):
        """
        Generate background music via ElevenLabs Music API.

        Args:
            prompt: Natural language description of the music.
            duration_ms: Length in milliseconds (3000-600000).
            title: Filename prefix.

        Returns:
            Path to the downloaded music file, or None on failure.
        """
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "prompt": prompt,
            "duration_ms": max(3000, min(600000, duration_ms)),
        }

        print(f"[ElevenLabs Music] Prompt: {prompt}")
        print(f"[ElevenLabs Music] Duration: {duration_ms}ms")
        print("[ElevenLabs Music] Generating...")

        try:
            resp = requests.post(
                ELEVENLABS_MUSIC_URL,
                headers=headers,
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[ElevenLabs Music] Request failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[ElevenLabs Music] Response: {exc.response.text}")
            return None

        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"music_{safe_title}_{timestamp}.mp3"
        filepath = DOWNLOADS_DIR / filename

        with open(filepath, "wb") as f:
            f.write(resp.content)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"[ElevenLabs Music] Saved: {filepath} ({size_mb:.2f} MB)")
        return str(filepath)

    def generate_sfx(self, prompt, duration_seconds=2.0, title="sfx"):
        """
        Generate a sound effect via ElevenLabs Sound Generation API.

        Args:
            prompt: Natural language description of the sound effect.
            duration_seconds: Duration in seconds (max 30).
            title: Filename prefix.

        Returns:
            Path to the downloaded audio file, or None on failure.
        """
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": prompt,
            "duration_seconds": min(30.0, max(0.5, duration_seconds)),
        }

        print(f"[ElevenLabs SFX] Prompt: {prompt}")
        print(f"[ElevenLabs SFX] Duration: {duration_seconds}s")
        print("[ElevenLabs SFX] Generating...")

        try:
            resp = requests.post(
                ELEVENLABS_SFX_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[ElevenLabs SFX] Request failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[ElevenLabs SFX] Response: {exc.response.text}")
            return None

        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sfx_{safe_title}_{timestamp}.mp3"
        filepath = DOWNLOADS_DIR / filename

        with open(filepath, "wb") as f:
            f.write(resp.content)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"[ElevenLabs SFX] Saved: {filepath} ({size_mb:.2f} MB)")
        return str(filepath)


# ---------------------------------------------------------------------------
# YouTube Upload (OAuth2 + YouTube Data API v3)
# ---------------------------------------------------------------------------

class YouTubeUploader:
    """Handles YouTube video uploads via the YouTube Data API v3 with OAuth2."""

    SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.upload"]
    TOKEN_PATH = PIPELINE_DIR / "youtube_token.json"
    UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
    MAX_RETRIES = 3

    CATEGORY_MAP = {
        "art": "22",          # People & Blogs (art content)
        "tech": "28",         # Science & Technology
        "business": "22",     # People & Blogs
        "wellness": "22",     # People & Blogs
        "products": "22",     # People & Blogs
    }

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self._credentials = None

    def setup_auth(self):
        """Run the one-time OAuth2 consent flow and save the refresh token."""
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            print("[YouTube] google-auth-oauthlib not installed.")
            print("[YouTube] Run: pip install google-auth-oauthlib google-api-python-client")
            return False

        client_config = {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost/"],
            }
        }

        print("[YouTube] Starting OAuth2 consent flow...")
        print("[YouTube] A browser window will open. Sign in and grant YouTube upload access.")

        flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)
        credentials = flow.run_local_server(
            port=8090, open_browser=True, prompt="consent"
        )

        # Save token for future use
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes),
        }
        with open(self.TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)

        print(f"[YouTube] Auth token saved to {self.TOKEN_PATH}")
        print("[YouTube] You can now use the 'upload' and 'produce' commands.")
        return True

    def _get_credentials(self):
        """Load and refresh OAuth2 credentials."""
        if self._credentials:
            return self._credentials

        if not self.TOKEN_PATH.exists():
            print("[YouTube] No auth token found. Run: python produce_video.py setup-auth")
            return None

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
        except ImportError:
            print("[YouTube] google-auth not installed.")
            print("[YouTube] Run: pip install google-auth-oauthlib google-api-python-client")
            return None

        with open(self.TOKEN_PATH, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        credentials = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )

        if credentials.expired and credentials.refresh_token:
            print("[YouTube] Refreshing access token...")
            credentials.refresh(Request())
            # Update saved token
            token_data["token"] = credentials.token
            with open(self.TOKEN_PATH, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)

        self._credentials = credentials
        return credentials

    def upload(self, video_path, title, description="", tags=None,
               category_id="22", privacy="private", is_shorts=False,
               notify_subscribers=True):
        """
        Upload a video to YouTube.

        Args:
            video_path: Path to the .mp4 file.
            title: Video title (max 100 chars).
            description: Video description (max 5000 chars).
            tags: List of tags.
            category_id: YouTube category ID.
            privacy: "private", "unlisted", or "public".
            is_shorts: If True, prepend #Shorts to title.
            notify_subscribers: Whether to notify subscribers.

        Returns:
            YouTube video ID on success, None on failure.
        """
        credentials = self._get_credentials()
        if not credentials:
            return None

        video_file = Path(video_path)
        if not video_file.exists():
            print(f"[YouTube] Video file not found: {video_path}")
            return None

        # Shorts: add #Shorts tag
        if is_shorts and "#Shorts" not in title:
            title = f"{title} #Shorts"

        # Truncate to YouTube limits
        title = title[:100]
        description = description[:5000]
        tags = (tags or [])[:500]

        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
                "notifySubscribers": notify_subscribers,
            },
        }

        print(f"[YouTube] Uploading: {video_file.name}")
        print(f"[YouTube] Title: {title}")
        print(f"[YouTube] Privacy: {privacy}")
        print(f"[YouTube] Tags: {len(tags)} tags")
        size_mb = video_file.stat().st_size / (1024 * 1024)
        print(f"[YouTube] File size: {size_mb:.1f} MB")

        headers = {
            "Authorization": f"Bearer {credentials.token}",
        }

        # Step 1: Start resumable upload
        init_headers = {
            **headers,
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_file.stat().st_size),
        }

        params = {
            "uploadType": "resumable",
            "part": "snippet,status",
            "notifySubscribers": str(notify_subscribers).lower(),
        }

        try:
            resp = requests.post(
                self.UPLOAD_URL,
                headers=init_headers,
                params=params,
                json=metadata,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[YouTube] Upload init failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[YouTube] Response: {exc.response.text}")
            return None

        upload_url = resp.headers.get("Location")
        if not upload_url:
            print("[YouTube] No upload URL received.")
            return None

        # Step 2: Upload video file
        print("[YouTube] Uploading video data...")
        try:
            with open(video_file, "rb") as f:
                resp = requests.put(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {credentials.token}",
                        "Content-Type": "video/mp4",
                    },
                    data=f,
                    timeout=600,
                )
                resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[YouTube] Upload failed: {exc}")
            if hasattr(exc, "response") and exc.response is not None:
                print(f"[YouTube] Response: {exc.response.text}")
            return None

        data = resp.json()
        video_id = data.get("id")
        if video_id:
            yt_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"[YouTube] Upload complete!")
            print(f"[YouTube] Video ID: {video_id}")
            print(f"[YouTube] URL: {yt_url}")
            return video_id
        else:
            print(f"[YouTube] Upload response: {json.dumps(data, indent=2)}")
            return None


# ---------------------------------------------------------------------------
# B-Roll Management
# ---------------------------------------------------------------------------

class BRollManager:
    """Manages a local library of B-roll video clips organized by content pillar."""

    def __init__(self, broll_dir=None):
        self.broll_dir = Path(broll_dir) if broll_dir else BROLL_DIR

    def get_clips(self, pillar=None, count=3):
        """
        Get random B-roll clips for a content pillar.

        Args:
            pillar: Content pillar name (art, tech, business, etc.).
            count: Number of clips to return.

        Returns:
            List of Path objects to video clips. May be empty if no clips exist.
        """
        search_dirs = []

        if pillar:
            pillar_dir = self.broll_dir / pillar
            if pillar_dir.exists():
                search_dirs.append(pillar_dir)

        # Also check generic folder
        generic_dir = self.broll_dir / "generic"
        if generic_dir.exists():
            search_dirs.append(generic_dir)

        if not search_dirs:
            return []

        # Collect all video files
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        all_clips = []
        for d in search_dirs:
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in video_exts:
                    all_clips.append(f)

        if not all_clips:
            return []

        return random.sample(all_clips, min(count, len(all_clips)))

    def list_clips(self, pillar=None):
        """List all available B-roll clips, optionally filtered by pillar."""
        if pillar:
            target = self.broll_dir / pillar
            if not target.exists():
                return []
            dirs = [target]
        else:
            dirs = [d for d in self.broll_dir.iterdir() if d.is_dir()]

        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        clips = {}
        for d in dirs:
            pillar_name = d.name
            pillar_clips = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in video_exts]
            if pillar_clips:
                clips[pillar_name] = pillar_clips

        return clips

    def has_clips(self, pillar=None):
        """Check if any B-roll clips are available."""
        return len(self.get_clips(pillar, count=1)) > 0


# ---------------------------------------------------------------------------
# Video Compositor (MoviePy-based)
# ---------------------------------------------------------------------------

class VideoCompositor:
    """
    Composites a final video from avatar footage, B-roll, text overlays,
    and background music using MoviePy.
    """

    # Default intro/outro clip paths (set via brand_config or CLI)
    ASSETS_DIR = PIPELINE_DIR / "assets"

    def __init__(self, avatar_video_path, output_dir=None):
        self.avatar_path = Path(avatar_video_path)
        self.output_dir = Path(output_dir) if output_dir else DOWNLOADS_DIR
        self._music_path = None
        self._music_volume = COMP_MUSIC_VOLUME
        self._broll_clips = []
        self._broll_duration = COMP_BROLL_DURATION
        self._text_overlays = []
        self._intro_clip_path = None
        self._outro_clip_path = None

        # Auto-detect brand intro/outro from assets directory
        # Priority: video clip > trimmed audio clips > full song
        brand_intro_video = self.ASSETS_DIR / "brand_intro.mp4"
        brand_intro_audio = self.ASSETS_DIR / "brand_intro_8s.mp3"
        brand_outro_audio = self.ASSETS_DIR / "brand_outro_12s.mp3"

        if brand_intro_video.exists():
            self._intro_clip_path = brand_intro_video
            self._outro_clip_path = brand_intro_video
            print(f"[Compositor] Brand intro/outro video: {brand_intro_video.name}")
        else:
            if brand_intro_audio.exists():
                self._intro_clip_path = brand_intro_audio
                print(f"[Compositor] Brand intro: {brand_intro_audio.name}")
            if brand_outro_audio.exists():
                self._outro_clip_path = brand_outro_audio
                print(f"[Compositor] Brand outro: {brand_outro_audio.name}")

    def set_intro(self, clip_path):
        """Set a custom intro clip (video or audio) to prepend."""
        self._intro_clip_path = Path(clip_path) if clip_path else None
        if self._intro_clip_path:
            print(f"[Compositor] Intro clip: {self._intro_clip_path.name}")

    def set_outro(self, clip_path):
        """Set a custom outro clip (video or audio) to append."""
        self._outro_clip_path = Path(clip_path) if clip_path else None
        if self._outro_clip_path:
            print(f"[Compositor] Outro clip: {self._outro_clip_path.name}")

    def add_background_music(self, music_path, volume=None):
        """Set background music track with optional volume override."""
        self._music_path = Path(music_path)
        if volume is not None:
            self._music_volume = volume
        print(f"[Compositor] Background music: {self._music_path.name} (volume: {self._music_volume})")

    def add_broll(self, clips, duration_each=None):
        """
        Add B-roll clips to intercut with the avatar.

        Args:
            clips: List of file paths or Path objects to video clips.
            duration_each: Seconds to show each B-roll clip.
        """
        if duration_each is not None:
            self._broll_duration = duration_each
        self._broll_clips = [Path(c) for c in clips if Path(c).exists()]
        print(f"[Compositor] B-roll clips: {len(self._broll_clips)} ({self._broll_duration}s each)")

    def add_text_overlay(self, text, position="bottom", start=0, duration=3, font_size=48):
        """
        Add a text overlay (lower-third, title card, etc.).

        Args:
            text: Text string to display.
            position: "bottom", "top", or "center".
            start: Start time in seconds.
            duration: Duration in seconds.
            font_size: Font size in pixels.
        """
        self._text_overlays.append({
            "text": text,
            "position": position,
            "start": start,
            "duration": duration,
            "font_size": font_size,
        })

    def compose(self, output_title="final_video"):
        """
        Render the final composed video.

        Steps:
            1. Load avatar video as base track
            2. If B-roll clips exist, insert them at evenly-spaced intervals
            3. Layer text overlays at specified timestamps
            4. Mix background music at low volume under voice audio
            5. Export as MP4

        Returns:
            Path to the output video file, or None on failure.
        """
        try:
            from moviepy import (
                VideoFileClip, AudioFileClip, TextClip,
                CompositeVideoClip, CompositeAudioClip,
                concatenate_videoclips,
            )
        except ImportError:
            try:
                from moviepy.editor import (
                    VideoFileClip, AudioFileClip, TextClip,
                    CompositeVideoClip, CompositeAudioClip,
                    concatenate_videoclips,
                )
            except ImportError:
                print("[Compositor] moviepy not installed. Run: pip install moviepy")
                return None

        if not self.avatar_path.exists():
            print(f"[Compositor] Avatar video not found: {self.avatar_path}")
            return None

        print(f"[Compositor] Loading avatar video: {self.avatar_path.name}")
        avatar = VideoFileClip(str(self.avatar_path))
        avatar_duration = avatar.duration

        print(f"[Compositor] Avatar duration: {avatar_duration:.1f}s")

        # --- B-roll intercutting ---
        if self._broll_clips:
            final_video = self._intercut_broll(avatar, VideoFileClip, concatenate_videoclips)
        else:
            final_video = avatar

        # --- Text overlays ---
        if self._text_overlays:
            final_video = self._apply_text_overlays(final_video, TextClip, CompositeVideoClip)

        # --- Background music mixing ---
        if self._music_path and self._music_path.exists():
            final_video = self._mix_background_music(final_video, AudioFileClip, CompositeAudioClip)

        # --- Intro/Outro clips ---
        if self._intro_clip_path or self._outro_clip_path:
            final_video = self._attach_intro_outro(
                final_video, VideoFileClip, AudioFileClip,
                concatenate_videoclips, CompositeAudioClip,
            )

        # --- Export ---
        safe_title = re.sub(r'[^\w\s-]', '', output_title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"{safe_title}_composed_{timestamp}.mp4"

        print(f"[Compositor] Rendering final video to {output_path}...")
        final_video.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            fps=avatar.fps or 30,
            logger="bar",
        )

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"[Compositor] Final video: {output_path} ({size_mb:.1f} MB)")

        # Cleanup
        avatar.close()
        final_video.close()

        return str(output_path)

    def _attach_intro_outro(self, video, VideoFileClip, AudioFileClip,
                             concatenate_videoclips, CompositeAudioClip):
        """Prepend intro clip and append outro clip to the main video."""
        from moviepy import ColorClip
        segments = []

        for label, clip_path in [("Intro", self._intro_clip_path), ("Outro", self._outro_clip_path)]:
            if not clip_path or not Path(clip_path).exists():
                if label == "Intro":
                    segments.append(("main", video))
                continue

            suffix = Path(clip_path).suffix.lower()
            try:
                if suffix in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                    # Video file — resize to match main video dimensions
                    clip = VideoFileClip(str(clip_path))
                    clip = clip.resized((video.w, video.h))
                    if label == "Intro":
                        segments.append(("intro", clip))
                        segments.append(("main", video))
                    else:
                        segments.append(("outro", clip))
                    print(f"[Compositor] {label} video: {Path(clip_path).name} ({clip.duration:.1f}s)")

                elif suffix in (".mp3", ".wav", ".m4a", ".aac"):
                    # Audio-only — create a branded title card with the audio
                    audio = AudioFileClip(str(clip_path))
                    card = ColorClip(
                        size=(video.w, video.h),
                        color=(16, 25, 34),  # Brand dark background
                        duration=audio.duration,
                    )
                    card = card.with_audio(audio)
                    card = card.with_fps(video.fps or 30)
                    if label == "Intro":
                        segments.append(("intro", card))
                        segments.append(("main", video))
                    else:
                        segments.append(("outro", card))
                    print(f"[Compositor] {label} audio card: {Path(clip_path).name} ({audio.duration:.1f}s)")
            except Exception as exc:
                print(f"[Compositor] {label} clip failed: {exc}")
                if label == "Intro" and ("main", video) not in segments:
                    segments.append(("main", video))

        # Ensure main video is included
        if not any(s[0] == "main" for s in segments):
            segments.append(("main", video))

        ordered = [s[1] for s in segments]
        if len(ordered) > 1:
            return concatenate_videoclips(ordered, method="compose")
        return video

    def _intercut_broll(self, avatar, VideoFileClip, concatenate_videoclips):
        """Insert B-roll clips at evenly-spaced intervals in the avatar video."""
        num_broll = len(self._broll_clips)
        avatar_duration = avatar.duration

        # Calculate insertion points (evenly spaced)
        interval = avatar_duration / (num_broll + 1)
        segments = []
        current_time = 0

        for i, broll_path in enumerate(self._broll_clips):
            insert_at = interval * (i + 1)

            # Avatar segment before this B-roll
            if insert_at > current_time:
                seg = avatar.subclipped(current_time, min(insert_at, avatar_duration))
                segments.append(seg)

            # B-roll clip (trimmed to duration, resized to match avatar)
            try:
                broll = VideoFileClip(str(broll_path))
                broll_dur = min(self._broll_duration, broll.duration)
                broll = broll.subclipped(0, broll_dur)
                broll = broll.resized((avatar.w, avatar.h))
                # Remove B-roll's own audio (we keep avatar voice + music only)
                broll = broll.with_effects([lambda c: c.without_audio()])
                segments.append(broll)
                print(f"[Compositor] B-roll #{i+1}: {broll_path.name} ({broll_dur:.1f}s)")
            except Exception as exc:
                print(f"[Compositor] B-roll #{i+1} failed: {exc}")

            current_time = insert_at

        # Remaining avatar footage after last B-roll
        if current_time < avatar_duration:
            segments.append(avatar.subclipped(current_time, avatar_duration))

        if len(segments) > 1:
            return concatenate_videoclips(segments, method="compose")
        return avatar

    def _apply_text_overlays(self, video, TextClip, CompositeVideoClip):
        """Layer text overlays onto the video."""
        clips = [video]

        for overlay in self._text_overlays:
            try:
                pos_map = {
                    "bottom": ("center", video.h - 100),
                    "top": ("center", 50),
                    "center": ("center", "center"),
                }
                position = pos_map.get(overlay["position"], ("center", "center"))

                txt = TextClip(
                    text=overlay["text"],
                    font_size=overlay["font_size"],
                    color=COMP_TEXT_COLOR,
                    font="Arial",
                    bg_color="black",
                    size=(video.w - 100, None),
                    text_align="center",
                )
                txt = txt.with_position(position)
                txt = txt.with_start(overlay["start"])
                txt = txt.with_duration(overlay["duration"])
                clips.append(txt)
                print(f"[Compositor] Text overlay: \"{overlay['text'][:40]}...\" at {overlay['start']}s")
            except Exception as exc:
                print(f"[Compositor] Text overlay failed: {exc}")

        if len(clips) > 1:
            return CompositeVideoClip(clips)
        return video

    def _mix_background_music(self, video, AudioFileClip, CompositeAudioClip):
        """Mix background music at low volume under the video's existing audio."""
        try:
            music = AudioFileClip(str(self._music_path))

            # Loop or trim music to match video duration
            if music.duration < video.duration:
                # Loop the music
                loops_needed = int(video.duration / music.duration) + 1
                from moviepy import concatenate_audioclips
                music = concatenate_audioclips([music] * loops_needed)
            music = music.subclipped(0, video.duration)

            # Apply volume reduction
            music = music.with_volume_scaled(self._music_volume)

            if video.audio:
                mixed = CompositeAudioClip([video.audio, music])
                video = video.with_audio(mixed)
                print(f"[Compositor] Background music mixed at {self._music_volume:.0%} volume")
            else:
                video = video.with_audio(music)
                print(f"[Compositor] Background music added (no voice track to mix with)")

        except ImportError:
            # Fallback for older moviepy
            try:
                from moviepy.editor import concatenate_audioclips
                music = AudioFileClip(str(self._music_path))
                if music.duration < video.duration:
                    loops_needed = int(video.duration / music.duration) + 1
                    music = concatenate_audioclips([music] * loops_needed)
                music = music.subclipped(0, video.duration)
                music = music.volumex(self._music_volume)
                if video.audio:
                    mixed = CompositeAudioClip([video.audio, music])
                    video = video.with_audio(mixed)
                else:
                    video = video.with_audio(music)
            except Exception as exc:
                print(f"[Compositor] Music mixing failed: {exc}")
        except Exception as exc:
            print(f"[Compositor] Music mixing failed: {exc}")

        return video


# ---------------------------------------------------------------------------
# Image Generator  --  Gemini Nano Banana / Imagen for B-roll & thumbnails
# ---------------------------------------------------------------------------

class ImageGenerator:
    """
    Generates B-roll images and thumbnails using Google Gemini image models.
    Supports Nano Banana (gemini-2.5-flash-image), Nano Banana Pro
    (gemini-3-pro-image-preview), and Imagen 4 models.

    COST NOTE: Image generation may consume API credits. All methods print
    cost warnings before making API calls.
    """

    MODELS = {
        "nano-banana": "gemini-2.5-flash-image",
        "nano-banana-pro": "gemini-3-pro-image-preview",
        "imagen-4": "imagen-4.0-generate-001",
        "imagen-4-fast": "imagen-4.0-fast-generate-001",
        "imagen-4-ultra": "imagen-4.0-ultra-generate-001",
    }

    DEFAULT_MODEL = "nano-banana"

    # Pillar-specific prompt templates for B-roll generation
    BROLL_PROMPTS = {
        "art": [
            "cinematic close-up of hands painting on a digital tablet, warm amber studio lighting, shallow depth of field, professional photography, 4K",
            "wide shot of modern creative studio workspace with monitors showing colorful digital art, moody warm lighting, cinematic composition",
            "close-up of art supplies and digital tools arranged on a dark desk, dramatic side lighting, editorial photography",
            "overhead shot of a sketchbook with colorful illustrations next to a stylus and tablet, warm tones, lifestyle photography",
        ],
        "tech": [
            "close-up of glowing code on a dark monitor screen, blue and amber light reflections, cinematic bokeh, 4K",
            "futuristic minimal workspace with multiple screens showing dashboards and code, dark background, orange accent lighting, cinematic",
            "close-up of a mechanical keyboard with ambient RGB lighting, shallow depth of field, moody tech aesthetic",
            "abstract visualization of data flowing through circuits, dark background with amber and blue highlights, cinematic",
        ],
        "business": [
            "cinematic shot of entrepreneur working at laptop in modern office, golden hour window light, shallow depth of field",
            "flat lay of business tools on dark desk: laptop, notebook, coffee, phone with analytics, warm overhead lighting",
            "close-up of hands typing on laptop with financial charts on screen, warm ambient lighting, professional photography",
            "modern minimalist workspace with motivational elements, clean composition, warm natural lighting, editorial style",
        ],
        "wellness": [
            "serene meditation scene with warm candlelight, minimal composition, calming earth tones, cinematic photography",
            "close-up of hands in meditation pose, soft warm light, shallow depth of field, peaceful atmosphere",
            "nature scene with morning sunlight through trees, peaceful trail, warm golden tones, cinematic landscape",
            "minimalist wellness workspace with journal and tea, soft natural lighting, calm earth tone palette",
        ],
        "products": [
            "product photography flat lay of art prints and apparel on dark textured surface, warm studio lighting, overhead shot, 4K",
            "close-up of premium art print with visible texture and detail, dramatic side lighting, product photography",
            "lifestyle shot of wall art in modern interior setting, warm ambient lighting, editorial home decor photography",
            "creative flat lay of merchandise and packaging with brand elements, dark background, warm accent lighting",
        ],
        "generic": [
            "cinematic abstract background with warm amber and dark blue tones, smooth gradient, 4K wallpaper",
            "close-up of creative tools on a dark surface, dramatic lighting, shallow depth of field, editorial style",
            "modern minimal desk setup from above, dark theme with warm accent lighting, lifestyle photography",
        ],
    }

    def __init__(self, api_key):
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Lazy-load the Gemini client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai
        return self._client

    def generate_broll(self, pillar="generic", count=3, model=None,
                       custom_prompt=None, output_dir=None, confirm_cost=True):
        """
        Generate B-roll images for a content pillar.

        Args:
            pillar: Content pillar ID (art, tech, business, wellness, products, generic)
            count: Number of images to generate (1-4)
            model: Model key from MODELS dict (default: nano-banana)
            custom_prompt: Override pillar prompts with a custom prompt
            output_dir: Where to save images (default: broll/<pillar>/)
            confirm_cost: Print cost warning before generating

        Returns:
            List of saved image file paths
        """
        model_key = model or self.DEFAULT_MODEL
        model_id = self.MODELS.get(model_key, model_key)

        if output_dir is None:
            output_dir = BROLL_DIR / pillar
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        count = min(count, 4)

        if confirm_cost:
            print(f"[ImageGen] WARNING: About to generate {count} image(s) using {model_key}")
            print(f"[ImageGen] Model: {model_id}")
            print(f"[ImageGen] This may consume API credits on your Gemini account.")
            print(f"[ImageGen] Proceed? (y/n) ", end="", flush=True)
            answer = input().strip().lower()
            if answer not in ("y", "yes"):
                print("[ImageGen] Cancelled.")
                return []

        # Pick prompts
        if custom_prompt:
            prompts = [custom_prompt] * count
        else:
            pillar_prompts = self.BROLL_PROMPTS.get(pillar, self.BROLL_PROMPTS["generic"])
            prompts = random.sample(pillar_prompts, min(count, len(pillar_prompts)))
            # If we need more than available prompts, repeat
            while len(prompts) < count:
                prompts.append(random.choice(pillar_prompts))

        saved_paths = []
        client = self._get_client()
        is_imagen = model_id.startswith("imagen-")

        for i, prompt in enumerate(prompts):
            print(f"[ImageGen] Generating image {i + 1}/{count}...")
            print(f"[ImageGen] Prompt: {prompt[:80]}...")

            try:
                from google.genai import types

                timestamp = int(time.time())
                filename = f"broll_{pillar}_{timestamp}_{i + 1}.png"
                filepath = output_dir / filename

                if is_imagen:
                    # Imagen models use generate_images API
                    response = client.models.generate_images(
                        model=model_id,
                        prompt=prompt,
                        config=types.GenerateImagesConfig(
                            number_of_images=1,
                        ),
                    )
                    if response.generated_images:
                        response.generated_images[0].image.save(str(filepath))
                    else:
                        print(f"[ImageGen] No image returned for prompt {i + 1}")
                        continue
                else:
                    # Nano Banana models use generate_content with IMAGE modality
                    response = client.models.generate_content(
                        model=model_id,
                        contents=f"Generate an image: {prompt}",
                        config=types.GenerateContentConfig(
                            response_modalities=["TEXT", "IMAGE"],
                        ),
                    )
                    image_saved = False
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            with open(filepath, "wb") as f:
                                f.write(part.inline_data.data)
                            image_saved = True
                            break
                    if not image_saved:
                        print(f"[ImageGen] No image returned for prompt {i + 1}")
                        continue

                size_kb = filepath.stat().st_size / 1024
                print(f"[ImageGen] Saved: {filepath} ({size_kb:.0f} KB)")
                saved_paths.append(filepath)

            except Exception as exc:
                print(f"[ImageGen] Generation failed for image {i + 1}: {exc}")

        print(f"[ImageGen] Generated {len(saved_paths)}/{count} images")
        return saved_paths

    def generate_thumbnail(self, topic, pillar=None, text_overlay=None,
                           model=None, output_dir=None, confirm_cost=True):
        """
        Generate a thumbnail image for a video.

        Args:
            topic: Video topic for prompt generation
            pillar: Content pillar for style hints
            text_overlay: Text to include in the image (YouTube thumbnail text)
            model: Model key (default: nano-banana-pro for higher quality thumbnails)
            output_dir: Save location (default: ~/Downloads)

        Returns:
            Path to saved thumbnail image, or None
        """
        model_key = model or "nano-banana-pro"
        model_id = self.MODELS.get(model_key, model_key)

        if output_dir is None:
            output_dir = DOWNLOADS_DIR
        output_dir = Path(output_dir)

        # Build thumbnail prompt
        brand_colors = "dark navy (#101922) background with orange (#e8941f) accents"
        style = "YouTube thumbnail style, high contrast, bold, eye-catching, 16:9 aspect ratio"

        if text_overlay:
            prompt = (
                f"{style}, {brand_colors}, featuring bold large text '{text_overlay}' "
                f"as the focal point, related to {topic}, professional graphic design, 4K"
            )
        else:
            prompt = (
                f"{style}, {brand_colors}, cinematic visual related to {topic}, "
                f"dramatic lighting, space for text overlay on the left side, 4K"
            )

        if confirm_cost:
            print(f"[ImageGen] WARNING: About to generate 1 thumbnail image using {model_key}")
            print(f"[ImageGen] This may consume API credits on your Gemini account.")
            print(f"[ImageGen] Proceed? (y/n) ", end="", flush=True)
            answer = input().strip().lower()
            if answer not in ("y", "yes"):
                print("[ImageGen] Cancelled.")
                return None

        print(f"[ImageGen] Generating thumbnail for: {topic}")
        print(f"[ImageGen] Model: {model_id}")

        try:
            client = self._get_client()
            from google.genai import types
            is_imagen = model_id.startswith("imagen-")

            safe_topic = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')[:30]
            timestamp = int(time.time())
            filename = f"thumbnail_{safe_topic}_{timestamp}.png"
            filepath = output_dir / filename

            if is_imagen:
                response = client.models.generate_images(
                    model=model_id,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                    ),
                )
                if response.generated_images:
                    response.generated_images[0].image.save(str(filepath))
                else:
                    print("[ImageGen] No thumbnail image returned")
                    return None
            else:
                response = client.models.generate_content(
                    model=model_id,
                    contents=f"Generate an image: {prompt}",
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                image_saved = False
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        with open(filepath, "wb") as f:
                            f.write(part.inline_data.data)
                        image_saved = True
                        break
                if not image_saved:
                    print("[ImageGen] No thumbnail image returned")
                    return None

            size_kb = filepath.stat().st_size / 1024
            print(f"[ImageGen] Thumbnail saved: {filepath} ({size_kb:.0f} KB)")
            return filepath

        except Exception as exc:
            print(f"[ImageGen] Thumbnail generation failed: {exc}")
            return None

    def list_models(self):
        """List available image generation models."""
        print("[ImageGen] Available models:")
        for key, model_id in self.MODELS.items():
            marker = " (default)" if key == self.DEFAULT_MODEL else ""
            print(f"  {key}: {model_id}{marker}")


# ---------------------------------------------------------------------------
# Thumbnail Text Generator
# ---------------------------------------------------------------------------

class ThumbnailGenerator:
    """Generates high-impact thumbnail text options for YouTube videos."""

    TEMPLATES = [
        "{power_word}",
        "{power_word} {short_topic}",
        "I tried {short_topic}",
        "{short_topic} in {time}",
        "Stop doing THIS",
        "{number} {short_topic} tips",
        "This changes {short_topic}",
        "{short_topic} SECRET",
        "DON'T {mistake}",
        "How I {result}",
        "{short_topic}?!",
        "Wait... WHAT?!",
    ]

    POWER_WORDS = [
        "SHOCKING", "INSANE", "GAME CHANGER", "SECRET", "TRUTH",
        "WARNING", "FINALLY", "WOW", "NO WAY", "MUST SEE",
    ]

    def __init__(self, topic, pillar=None):
        self.topic = topic
        self.pillar = pillar

    def generate(self):
        """Generate 6 thumbnail text options (max 5 words each)."""
        short_topic = self._shorten_topic()
        options = []

        for template in random.sample(self.TEMPLATES, min(6, len(self.TEMPLATES))):
            text = template.format(
                power_word=random.choice(self.POWER_WORDS),
                short_topic=short_topic,
                time="60s",
                number=random.choice([3, 5, 7]),
                mistake="skip this",
                result="made this",
            )
            # Ensure max 5 words
            words = text.split()
            if len(words) > 5:
                text = " ".join(words[:5])
            options.append(text.upper())

        # Deduplicate
        seen = set()
        unique = []
        for opt in options:
            if opt not in seen:
                seen.add(opt)
                unique.append(opt)

        return {
            "topic": self.topic,
            "thumbnail_texts": unique,
            "style_guide": {
                "max_words": 5,
                "font_size": "30pt+",
                "show_face": True,
                "high_contrast": True,
                "accent_colors": _visual.get("thumbnail_style", {}).get(
                    "accent_colors", ["#e8941f", "#f4b88a"]
                ),
            },
        }

    def _shorten_topic(self):
        """Reduce topic to 1-3 key words."""
        stop_words = {
            "how", "to", "the", "a", "an", "in", "for", "of", "and",
            "is", "are", "was", "with", "that", "this", "from", "your",
            "my", "i", "you", "it", "on", "at", "by", "as", "do",
            "get", "started", "complete", "guide", "beginner", "need",
            "know", "explained", "seconds", "second", "minutes", "minute",
            "tips", "tricks", "tutorial", "behind", "scenes", "every",
            "single", "actually", "work", "just", "here", "what",
            "nobody", "tells", "about", "everything", "changed",
            "3", "5", "7", "10", "60", "30", "2026", "2025",
            "built", "tested", "tried", "made", "making", "new",
            "using", "scratch", "step", "most", "people", "ever",
        }
        words = self.topic.lower().split()
        key_words = [w for w in words if w not in stop_words]
        if not key_words:
            key_words = words[:2]
        return " ".join(key_words[:3]).title()


# ---------------------------------------------------------------------------
# Script File I/O
# ---------------------------------------------------------------------------

def save_script(script_data, topic):
    """Save the generated script to timestamped files in ~/Downloads/."""
    safe_topic = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save raw script (for HeyGen)
    raw_path = DOWNLOADS_DIR / f"script_{safe_topic}_{timestamp}.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(script_data["raw_text"])

    # Save annotated script (for ElevenLabs v3)
    annotated_path = DOWNLOADS_DIR / f"script_{safe_topic}_{timestamp}_annotated.txt"
    with open(annotated_path, "w", encoding="utf-8") as f:
        f.write(f"# Script: {topic}\n")
        f.write(f"# Tone: {script_data['metadata']['tone']}\n")
        f.write(f"# Duration: {script_data['metadata']['duration']}\n")
        f.write(f"# Shorts: {script_data['metadata']['is_shorts']}\n")
        f.write(f"# Pillar: {script_data['metadata'].get('pillar', 'none')}\n")
        f.write(f"# Word count: {script_data['metadata']['word_count']}\n")
        f.write(f"# Est. time: ~{script_data['metadata']['estimated_seconds']}s\n")
        f.write(f"# Generated: {script_data['metadata']['generated_at']}\n")
        f.write(f"# Audio tags: ElevenLabs v3 format\n")
        f.write("#" + "-" * 60 + "\n\n")
        f.write(script_data["annotated_text"])

    # Save metadata as JSON
    meta_path = DOWNLOADS_DIR / f"script_{safe_topic}_{timestamp}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(script_data["metadata"], f, indent=2)

    print(f"[Script] Raw script saved:       {raw_path}")
    print(f"[Script] Annotated script saved:  {annotated_path}")
    print(f"[Script] Metadata saved:          {meta_path}")

    return str(raw_path), str(annotated_path)


def generate_ai_script(topic, tone="professional", duration="medium",
                       pillar=None, is_shorts=False, series=None):
    """
    Call n8n webhook to generate an AI-powered script using Claude.

    Requires N8N_WEBHOOK_URL environment variable or the n8n workflow
    imported from n8n_video_script_workflow.json.

    Returns a dict matching ScriptWriter.generate() output, or None on failure.
    """
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if not webhook_url:
        # Try common n8n local URL
        webhook_url = "http://localhost:5678/webhook/generate-script"

    payload = {
        "topic": topic,
        "tone": tone,
        "duration": duration,
        "pillar": pillar or "art",
        "is_shorts": is_shorts,
    }

    print(f"[AI Script] Calling n8n webhook: {webhook_url}")
    print(f"[AI Script] Topic: {topic}")

    try:
        resp = requests.post(webhook_url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.ConnectionError:
        print("[AI Script] Could not connect to n8n. Is it running?")
        print("[AI Script] Start n8n with: n8n start")
        print("[AI Script] Import the workflow from: n8n_video_script_workflow.json")
        return None
    except requests.RequestException as exc:
        print(f"[AI Script] Request failed: {exc}")
        return None

    ai_text = data.get("script", "")
    if not ai_text:
        print("[AI Script] Empty response from n8n.")
        return None

    word_count = len(ai_text.split())
    print(f"[AI Script] Received {word_count} words from Claude")

    # Build annotated version (add basic v3 tags)
    sections = [{"name": f"ai_section_{i}", "text": p.strip()}
                for i, p in enumerate(ai_text.split("\n\n")) if p.strip()]
    if not sections:
        sections = [{"name": "ai_full", "text": ai_text}]

    # Create ScriptWriter just for annotation
    writer = ScriptWriter(topic=topic, tone=tone, duration=duration,
                          series=series, pillar=pillar, is_shorts=is_shorts)

    # Remap section names for annotation
    if len(sections) >= 3:
        sections[0]["name"] = "hook"
        sections[-1]["name"] = "cta"
        if len(sections) >= 4:
            sections[1]["name"] = "intro"

    annotated = writer._annotate_v3(sections)

    return {
        "raw_text": ai_text,
        "annotated_text": annotated,
        "sections": sections,
        "metadata": {
            "topic": topic,
            "tone": tone,
            "duration": duration,
            "series": series,
            "pillar": pillar,
            "is_shorts": is_shorts,
            "word_count": word_count,
            "estimated_seconds": round(word_count / 2.5),
            "generated_at": datetime.now().isoformat(),
            "ai_generated": True,
        },
    }


def load_script_from_file(filepath):
    """Load a script from a plain text file."""
    path = Path(filepath)
    if not path.exists():
        print(f"[ERROR] Script file not found: {filepath}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")

    # Strip comment header lines (lines starting with #)
    lines = text.splitlines()
    content_lines = [ln for ln in lines if not ln.startswith("#")]
    clean = "\n".join(content_lines).strip()

    if not clean:
        print(f"[ERROR] Script file is empty: {filepath}")
        sys.exit(1)

    print(f"[Script] Loaded script from {filepath} ({len(clean.split())} words)")
    return clean


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    """Build the argparse CLI."""
    parser = argparse.ArgumentParser(
        prog="produce_video",
        description="Richard Abreu's YouTube Video Production Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
            %(prog)s script "How to Start a Business"
            %(prog)s script "Python Tips" --tone casual --duration long
            %(prog)s video "Morning Routine" --tone energetic --format shorts
            %(prog)s audio "Motivation Monday" --series "Monday Motivation"
            %(prog)s seo "Affinity Designer Tips" --pillar art
            %(prog)s batch topics.txt --output video --format landscape
            %(prog)s music "lo-fi chill instrumental for art tutorial" --duration 60
            %(prog)s sfx "transition_whoosh"
            %(prog)s from-script ~/Downloads/script.txt --output video --format shorts
            %(prog)s upload ~/Downloads/video.mp4 --title "My Video" --pillar art
            %(prog)s produce "Full Tutorial" --pillar tech --format landscape
            %(prog)s produce "Quick Tip" --pillar art --format shorts --duration short
            %(prog)s thumbnail "Affinity Designer Tips" --pillar art
            %(prog)s setup-auth
        """),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- Common arguments ---------------------------------------------------

    def add_common_args(sub, include_format=True):
        sub.add_argument(
            "--tone",
            choices=["professional", "casual", "energetic", "educational", "storytelling"],
            default="professional",
            help="Tone/style of the script (default: professional)",
        )
        sub.add_argument(
            "--duration",
            choices=["short", "medium", "long", "extra-long"],
            default="medium",
            help="Target duration: short=30s, medium=60s, long=3min, extra-long=6min",
        )
        sub.add_argument(
            "--series",
            type=str,
            default=None,
            help="Series name for branding in intro (optional)",
        )
        sub.add_argument(
            "--pillar",
            choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
            default=None,
            help="Content pillar (auto-selects tone and tags if not specified)",
        )
        if include_format:
            sub.add_argument(
                "--format",
                dest="video_format",
                choices=["landscape", "shorts", "square"],
                default="landscape",
                help="Video format/dimensions (default: landscape 1920x1080)",
            )

    # -- script -------------------------------------------------------------
    script_parser = subparsers.add_parser(
        "script",
        help="Generate a YouTube script only (no video/audio)",
    )
    script_parser.add_argument("topic", help="Video topic or title")
    add_common_args(script_parser)
    script_parser.add_argument(
        "--ai", action="store_true",
        help="Use n8n + Claude AI for topic-specific content (requires n8n webhook)",
    )

    # -- video --------------------------------------------------------------
    video_parser = subparsers.add_parser(
        "video",
        help="Generate script + produce HeyGen avatar video",
    )
    video_parser.add_argument("topic", help="Video topic or title")
    add_common_args(video_parser)
    video_parser.add_argument(
        "--test",
        action="store_true",
        help="Use HeyGen test mode (no credits consumed, watermarked)",
    )

    # -- audio --------------------------------------------------------------
    audio_parser = subparsers.add_parser(
        "audio",
        help="Generate script + produce ElevenLabs audio",
    )
    audio_parser.add_argument("topic", help="Video topic or title")
    add_common_args(audio_parser, include_format=False)
    audio_parser.add_argument(
        "--stability", type=float, default=None,
        help="Override ElevenLabs voice stability 0.0-1.0",
    )
    audio_parser.add_argument(
        "--similarity", type=float, default=None,
        help="Override ElevenLabs similarity boost 0.0-1.0",
    )

    # -- seo ----------------------------------------------------------------
    seo_parser = subparsers.add_parser(
        "seo",
        help="Generate SEO metadata (titles, description, tags) for a topic",
    )
    seo_parser.add_argument("topic", help="Video topic")
    seo_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        default=None,
        help="Content pillar for tag generation",
    )

    # -- batch --------------------------------------------------------------
    batch_parser = subparsers.add_parser(
        "batch",
        help="Generate videos/audio from a topics file (one topic per line)",
    )
    batch_parser.add_argument("topics_file", help="Path to a .txt file with one topic per line")
    batch_parser.add_argument(
        "--output",
        choices=["script", "video", "audio"],
        default="script",
        help="Output type for each topic (default: script)",
    )
    add_common_args(batch_parser)

    # -- music --------------------------------------------------------------
    music_parser = subparsers.add_parser(
        "music",
        help="Generate background music via ElevenLabs Music API",
    )
    music_parser.add_argument("prompt", help="Music description or preset name (e.g. 'art_tutorial')")
    music_parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration in seconds (3-600, default: 30)",
    )

    # -- sfx ----------------------------------------------------------------
    sfx_parser = subparsers.add_parser(
        "sfx",
        help="Generate a sound effect via ElevenLabs Sound Effects API",
    )
    sfx_parser.add_argument("prompt", help="SFX description or preset name (e.g. 'transition_whoosh')")
    sfx_parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Duration in seconds (0.5-30, default: 2.0)",
    )

    # -- from-script --------------------------------------------------------
    from_script_parser = subparsers.add_parser(
        "from-script",
        help="Use an existing script file to produce video or audio",
    )
    from_script_parser.add_argument("script_file", help="Path to a .txt script file")
    from_script_parser.add_argument(
        "--output",
        choices=["video", "audio"],
        default="video",
        help="Output type: video (HeyGen) or audio (ElevenLabs)",
    )
    from_script_parser.add_argument(
        "--format",
        dest="video_format",
        choices=["landscape", "shorts", "square"],
        default="landscape",
        help="Video format (only for video output)",
    )
    from_script_parser.add_argument(
        "--tone",
        choices=["professional", "casual", "energetic", "educational", "storytelling"],
        default="professional",
        help="Tone (affects voice settings)",
    )
    from_script_parser.add_argument(
        "--stability", type=float, default=None,
        help="Override ElevenLabs stability (audio only)",
    )
    from_script_parser.add_argument(
        "--similarity", type=float, default=None,
        help="Override ElevenLabs similarity (audio only)",
    )
    from_script_parser.add_argument(
        "--test",
        action="store_true",
        help="Use HeyGen test mode (video only)",
    )

    # -- upload -------------------------------------------------------------
    upload_parser = subparsers.add_parser(
        "upload",
        help="Upload a video file to YouTube with SEO metadata",
    )
    upload_parser.add_argument("video_file", help="Path to .mp4 video file")
    upload_parser.add_argument("--title", required=True, help="Video title")
    upload_parser.add_argument(
        "--description", default="",
        help="Video description (or auto-generated if --pillar specified)",
    )
    upload_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        default=None,
        help="Content pillar for auto-generating SEO metadata",
    )
    upload_parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="private",
        help="Video privacy status (default: private for safety)",
    )
    upload_parser.add_argument(
        "--shorts", action="store_true",
        help="Mark as YouTube Shorts",
    )

    # -- produce (V2 pipeline) -----------------------------------------------
    produce_parser = subparsers.add_parser(
        "produce",
        help="Full V2 pipeline: script -> ElevenLabs audio -> HeyGen lip-sync -> compose -> upload",
    )
    produce_parser.add_argument("topic", help="Video topic or title")
    add_common_args(produce_parser)
    produce_parser.add_argument(
        "--test", action="store_true",
        help="Use HeyGen test mode (no credits consumed)",
    )
    produce_parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="private",
        help="YouTube privacy status (default: private)",
    )
    produce_parser.add_argument(
        "--skip-upload", action="store_true",
        help="Skip YouTube upload (produce video + SEO only)",
    )
    produce_parser.add_argument(
        "--skip-compose", action="store_true",
        help="Skip MoviePy composition (output raw HeyGen video)",
    )
    produce_parser.add_argument(
        "--no-music", action="store_true",
        help="Skip background music generation",
    )
    produce_parser.add_argument(
        "--broll-dir",
        type=str,
        default=None,
        help="Override B-roll clips directory (default: video-pipeline/broll/)",
    )

    # -- broll --------------------------------------------------------------
    broll_parser = subparsers.add_parser(
        "broll",
        help="Manage the B-roll clip library (list, add, download)",
    )
    broll_sub = broll_parser.add_subparsers(dest="broll_action", required=True)

    # broll list
    broll_list_parser = broll_sub.add_parser("list", help="List all B-roll clips organized by pillar")
    broll_list_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        default=None,
        help="Filter by content pillar",
    )

    # broll add
    broll_add_parser = broll_sub.add_parser("add", help="Copy a video file into a pillar directory")
    broll_add_parser.add_argument("file_path", help="Path to the video file to add")
    broll_add_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        required=True,
        help="Content pillar directory to copy the clip into",
    )

    # broll download
    broll_dl_parser = broll_sub.add_parser("download", help="Download a video from URL into a pillar directory")
    broll_dl_parser.add_argument("url", help="Direct URL to the video file")
    broll_dl_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        required=True,
        help="Content pillar directory to save the clip into",
    )

    # -- thumbnail ----------------------------------------------------------
    thumbnail_parser = subparsers.add_parser(
        "thumbnail",
        help="Generate thumbnail text suggestions for a topic",
    )
    thumbnail_parser.add_argument("topic", help="Video topic")
    thumbnail_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        default=None,
        help="Content pillar",
    )

    # -- image (Gemini Nano Banana) -----------------------------------------
    image_parser = subparsers.add_parser(
        "image",
        help="Generate images using Gemini (B-roll, thumbnails)",
    )
    image_sub = image_parser.add_subparsers(dest="image_action", required=True)

    # image broll
    image_broll_parser = image_sub.add_parser("broll", help="Generate B-roll images for a content pillar")
    image_broll_parser.add_argument(
        "--pillar",
        choices=(list(CONTENT_PILLARS.keys()) + ["generic"]) if CONTENT_PILLARS else ["generic"],
        default="generic",
        help="Content pillar for style (default: generic)",
    )
    image_broll_parser.add_argument(
        "--count", type=int, default=3,
        help="Number of images to generate (1-4, default: 3)",
    )
    image_broll_parser.add_argument(
        "--model",
        choices=list(ImageGenerator.MODELS.keys()),
        default=ImageGenerator.DEFAULT_MODEL,
        help=f"Image model (default: {ImageGenerator.DEFAULT_MODEL})",
    )
    image_broll_parser.add_argument(
        "--prompt", type=str, default=None,
        help="Custom prompt (overrides pillar default prompts)",
    )

    # image thumbnail
    image_thumb_parser = image_sub.add_parser("thumbnail", help="Generate a thumbnail image")
    image_thumb_parser.add_argument("topic", help="Video topic")
    image_thumb_parser.add_argument(
        "--text", type=str, default=None,
        help="Bold text overlay for the thumbnail",
    )
    image_thumb_parser.add_argument(
        "--pillar",
        choices=list(CONTENT_PILLARS.keys()) if CONTENT_PILLARS else None,
        default=None,
        help="Content pillar for style hints",
    )
    image_thumb_parser.add_argument(
        "--model",
        choices=list(ImageGenerator.MODELS.keys()),
        default="nano-banana-pro",
        help="Image model (default: nano-banana-pro for thumbnails)",
    )

    # image models
    image_sub.add_parser("models", help="List available image generation models")

    # -- setup-auth ---------------------------------------------------------
    subparsers.add_parser(
        "setup-auth",
        help="One-time YouTube OAuth2 setup (opens browser for consent)",
    )

    return parser


def resolve_tone(args):
    """
    If a pillar is specified but no explicit tone, use the pillar's default tone.
    """
    tone = getattr(args, "tone", "professional")
    pillar = getattr(args, "pillar", None)
    if pillar and pillar in CONTENT_PILLARS and tone == "professional":
        return CONTENT_PILLARS[pillar].get("default_tone", tone)
    return tone


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    keys = load_api_keys()

    print("=" * 64)
    print("  Richard Abreu - YouTube Video Production Pipeline")
    print("  Brand: Cumquat Vibes | cumquatvibes.com")
    print("=" * 64)
    print()

    # -- Command: script ----------------------------------------------------
    if args.command == "script":
        tone = resolve_tone(args)
        is_shorts = args.duration == "short" or getattr(args, "video_format", "") == "shorts"

        use_ai = getattr(args, "ai", False)
        print(f"[Mode] Script generation {'(AI/Claude via n8n)' if use_ai else '(template-based)'}")
        print(f"[Topic] {args.topic}")
        print(f"[Tone] {tone}  |  [Duration] {args.duration}")
        if args.pillar:
            print(f"[Pillar] {args.pillar}")
        if args.series:
            print(f"[Series] {args.series}")
        if is_shorts:
            print("[Format] YouTube Shorts (optimised)")
        print()

        script_data = None

        if use_ai:
            script_data = generate_ai_script(
                topic=args.topic,
                tone=tone,
                duration=args.duration,
                pillar=args.pillar,
                is_shorts=is_shorts,
                series=args.series,
            )
            if not script_data:
                print("[AI Script] Falling back to template-based generation.")

        if not script_data:
            writer = ScriptWriter(
                topic=args.topic,
                tone=tone,
                duration=args.duration,
                series=args.series,
                pillar=args.pillar,
                is_shorts=is_shorts,
            )
            script_data = writer.generate()

        save_script(script_data, args.topic)

        print()
        print("-" * 64)
        source = "AI-GENERATED" if script_data["metadata"].get("ai_generated") else "TEMPLATE-GENERATED"
        print(f"{source} SCRIPT (raw / HeyGen-ready):")
        print("-" * 64)
        print(script_data["raw_text"])
        print("-" * 64)
        print(f"Word count: {script_data['metadata']['word_count']}")
        print(f"Estimated time: ~{script_data['metadata']['estimated_seconds']}s")

    # -- Command: video -----------------------------------------------------
    elif args.command == "video":
        if not keys["heygen_api_key"]:
            print("[ERROR] HEYGEN_API_KEY not found in .env file.")
            sys.exit(1)

        tone = resolve_tone(args)
        is_shorts = args.duration == "short" or args.video_format == "shorts"

        print(f"[Mode] Script + HeyGen video generation")
        print(f"[Topic] {args.topic}")
        print(f"[Tone] {tone}  |  [Duration] {args.duration}")
        print(f"[Format] {args.video_format}")
        if args.pillar:
            print(f"[Pillar] {args.pillar}")
        if args.series:
            print(f"[Series] {args.series}")
        if args.test:
            print("[Test Mode] ON (no credits consumed)")
        print()

        writer = ScriptWriter(
            topic=args.topic,
            tone=tone,
            duration=args.duration,
            series=args.series,
            pillar=args.pillar,
            is_shorts=is_shorts,
        )
        script_data = writer.generate()
        raw_path, annotated_path = save_script(script_data, args.topic)

        print()
        print("-" * 64)
        print("GENERATED SCRIPT:")
        print("-" * 64)
        print(script_data["raw_text"])
        print("-" * 64)
        print()

        client = HeyGenClient(keys["heygen_api_key"])
        video_path = client.generate_video(
            script_text=script_data["raw_text"],
            title=args.topic,
            video_format=args.video_format,
            tone=tone,
            test_mode=args.test,
            is_shorts=is_shorts,
        )

        print()
        if video_path:
            print(f"[SUCCESS] Video saved to: {video_path}")
        else:
            print("[FAILED] Video generation did not complete.")
            sys.exit(1)

    # -- Command: audio -----------------------------------------------------
    elif args.command == "audio":
        if not keys["elevenlabs_api_key"]:
            print("[ERROR] ELEVENLABS_API_KEY not found in .env file.")
            sys.exit(1)

        tone = resolve_tone(args)

        print(f"[Mode] Script + ElevenLabs audio generation")
        print(f"[Topic] {args.topic}")
        print(f"[Tone] {tone}  |  [Duration] {args.duration}")
        if args.pillar:
            print(f"[Pillar] {args.pillar}")
        if args.series:
            print(f"[Series] {args.series}")
        print()

        writer = ScriptWriter(
            topic=args.topic,
            tone=tone,
            duration=args.duration,
            series=args.series,
            pillar=args.pillar,
        )
        script_data = writer.generate()
        raw_path, annotated_path = save_script(script_data, args.topic)

        print()
        print("-" * 64)
        print("GENERATED SCRIPT (annotated / ElevenLabs v3):")
        print("-" * 64)
        print(script_data["annotated_text"])
        print("-" * 64)
        print()

        client = ElevenLabsClient(
            api_key=keys["elevenlabs_api_key"],
            voice_id=keys["elevenlabs_voice_id"],
        )
        audio_path = client.generate_audio(
            text=script_data["annotated_text"],
            title=args.topic,
            tone=tone,
            stability=args.stability,
            similarity_boost=args.similarity,
        )

        print()
        if audio_path:
            print(f"[SUCCESS] Audio saved to: {audio_path}")
        else:
            print("[FAILED] Audio generation did not complete.")
            sys.exit(1)

    # -- Command: seo -------------------------------------------------------
    elif args.command == "seo":
        print(f"[Mode] SEO metadata generation")
        print(f"[Topic] {args.topic}")
        if args.pillar:
            print(f"[Pillar] {args.pillar}")
        print()

        gen = SEOGenerator(
            topic=args.topic,
            pillar=args.pillar,
        )
        seo_data = gen.generate()

        print("-" * 64)
        print("TITLE OPTIONS:")
        print("-" * 64)
        for i, title in enumerate(seo_data["titles"], 1):
            print(f"  {i}. {title}")

        print()
        print("-" * 64)
        print("DESCRIPTION:")
        print("-" * 64)
        print(seo_data["description"])

        print()
        print("-" * 64)
        print("TAGS:")
        print("-" * 64)
        print(", ".join(seo_data["tags"]))

        # Save SEO data
        safe_topic = re.sub(r'[^\w\s-]', '', args.topic).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        seo_path = DOWNLOADS_DIR / f"seo_{safe_topic}_{timestamp}.json"
        with open(seo_path, "w", encoding="utf-8") as f:
            json.dump(seo_data, f, indent=2)
        print(f"\n[SEO] Saved to: {seo_path}")

    # -- Command: batch -----------------------------------------------------
    elif args.command == "batch":
        topics_path = Path(args.topics_file)
        if not topics_path.exists():
            print(f"[ERROR] Topics file not found: {args.topics_file}")
            sys.exit(1)

        topics = [line.strip() for line in topics_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
        print(f"[Batch] Loaded {len(topics)} topics from {args.topics_file}")
        print(f"[Batch] Output: {args.output}")
        print()

        tone = resolve_tone(args)
        is_shorts = args.duration == "short" or getattr(args, "video_format", "") == "shorts"
        results = []

        for i, topic in enumerate(topics, 1):
            print(f"\n{'='*64}")
            print(f"  [{i}/{len(topics)}] {topic}")
            print(f"{'='*64}\n")

            writer = ScriptWriter(
                topic=topic,
                tone=tone,
                duration=args.duration,
                series=args.series,
                pillar=args.pillar,
                is_shorts=is_shorts,
            )
            script_data = writer.generate()
            save_script(script_data, topic)

            result = {"topic": topic, "script": True, "output": None}

            if args.output == "video":
                if not keys["heygen_api_key"]:
                    print("[ERROR] HEYGEN_API_KEY not found.")
                    result["output"] = "error: no API key"
                else:
                    client = HeyGenClient(keys["heygen_api_key"])
                    video_path = client.generate_video(
                        script_text=script_data["raw_text"],
                        title=topic,
                        video_format=getattr(args, "video_format", "landscape"),
                        tone=tone,
                    )
                    result["output"] = video_path

            elif args.output == "audio":
                if not keys["elevenlabs_api_key"]:
                    print("[ERROR] ELEVENLABS_API_KEY not found.")
                    result["output"] = "error: no API key"
                else:
                    client = ElevenLabsClient(
                        api_key=keys["elevenlabs_api_key"],
                        voice_id=keys["elevenlabs_voice_id"],
                    )
                    audio_path = client.generate_audio(
                        text=script_data["annotated_text"],
                        title=topic,
                        tone=tone,
                    )
                    result["output"] = audio_path

            results.append(result)

        # Print batch summary
        print(f"\n{'='*64}")
        print("  BATCH SUMMARY")
        print(f"{'='*64}")
        for r in results:
            status = "OK" if r.get("output") or args.output == "script" else "FAILED"
            print(f"  [{status}] {r['topic']}")
            if r.get("output"):
                print(f"         -> {r['output']}")
        print()

    # -- Command: music -----------------------------------------------------
    elif args.command == "music":
        if not keys["elevenlabs_api_key"]:
            print("[ERROR] ELEVENLABS_API_KEY not found in .env file.")
            sys.exit(1)

        # Check if prompt is a preset name
        prompt = MUSIC_PRESETS.get(args.prompt, args.prompt)
        if prompt != args.prompt:
            print(f"[Mode] Background music (preset: {args.prompt})")
        else:
            print(f"[Mode] Background music generation")
        print(f"[Prompt] {prompt}")
        print(f"[Duration] {args.duration}s")
        print()

        client = ElevenLabsClient(
            api_key=keys["elevenlabs_api_key"],
            voice_id=keys["elevenlabs_voice_id"],
        )
        music_path = client.generate_music(
            prompt=prompt,
            duration_ms=args.duration * 1000,
            title=args.prompt[:40],
        )

        print()
        if music_path:
            print(f"[SUCCESS] Music saved to: {music_path}")
        else:
            print("[FAILED] Music generation did not complete.")
            sys.exit(1)

    # -- Command: sfx -------------------------------------------------------
    elif args.command == "sfx":
        if not keys["elevenlabs_api_key"]:
            print("[ERROR] ELEVENLABS_API_KEY not found in .env file.")
            sys.exit(1)

        # Check if prompt is a preset name
        prompt = SFX_PRESETS.get(args.prompt, args.prompt)
        if prompt != args.prompt:
            print(f"[Mode] Sound effect (preset: {args.prompt})")
        else:
            print(f"[Mode] Sound effect generation")
        print(f"[Prompt] {prompt}")
        print(f"[Duration] {args.duration}s")
        print()

        client = ElevenLabsClient(
            api_key=keys["elevenlabs_api_key"],
            voice_id=keys["elevenlabs_voice_id"],
        )
        sfx_path = client.generate_sfx(
            prompt=prompt,
            duration_seconds=args.duration,
            title=args.prompt[:40],
        )

        print()
        if sfx_path:
            print(f"[SUCCESS] Sound effect saved to: {sfx_path}")
        else:
            print("[FAILED] Sound effect generation did not complete.")
            sys.exit(1)

    # -- Command: from-script -----------------------------------------------
    elif args.command == "from-script":
        script_text = load_script_from_file(args.script_file)
        title = Path(args.script_file).stem

        if args.output == "video":
            if not keys["heygen_api_key"]:
                print("[ERROR] HEYGEN_API_KEY not found in .env file.")
                sys.exit(1)

            print(f"[Mode] Existing script -> HeyGen video")
            print(f"[Format] {args.video_format}")
            if args.test:
                print("[Test Mode] ON")
            print()

            client = HeyGenClient(keys["heygen_api_key"])
            video_path = client.generate_video(
                script_text=script_text,
                title=title,
                video_format=args.video_format,
                tone=args.tone,
                test_mode=args.test,
            )

            print()
            if video_path:
                print(f"[SUCCESS] Video saved to: {video_path}")
            else:
                print("[FAILED] Video generation did not complete.")
                sys.exit(1)

        elif args.output == "audio":
            if not keys["elevenlabs_api_key"]:
                print("[ERROR] ELEVENLABS_API_KEY not found in .env file.")
                sys.exit(1)

            print(f"[Mode] Existing script -> ElevenLabs audio")
            print()

            client = ElevenLabsClient(
                api_key=keys["elevenlabs_api_key"],
                voice_id=keys["elevenlabs_voice_id"],
            )
            audio_path = client.generate_audio(
                text=script_text,
                title=title,
                tone=args.tone,
                stability=args.stability,
                similarity_boost=args.similarity,
            )

            print()
            if audio_path:
                print(f"[SUCCESS] Audio saved to: {audio_path}")
            else:
                print("[FAILED] Audio generation did not complete.")
                sys.exit(1)

    # -- Command: upload ----------------------------------------------------
    elif args.command == "upload":
        if not keys.get("google_client_id") or not keys.get("google_client_secret"):
            print("[ERROR] GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET not found in .env file.")
            sys.exit(1)

        print(f"[Mode] YouTube upload")
        print(f"[Video] {args.video_file}")
        print(f"[Title] {args.title}")
        print(f"[Privacy] {args.privacy}")
        print()

        uploader = YouTubeUploader(keys["google_client_id"], keys["google_client_secret"])

        # Auto-generate SEO if pillar specified and no description
        description = args.description
        tags = []
        category_id = "22"

        if args.pillar:
            seo_gen = SEOGenerator(topic=args.title, pillar=args.pillar)
            seo_data = seo_gen.generate()
            if not description:
                description = seo_data["description"]
            tags = seo_data["tags"]
            category_id = YouTubeUploader.CATEGORY_MAP.get(args.pillar, "22")
            print(f"[SEO] Auto-generated description and {len(tags)} tags from '{args.pillar}' pillar")

        video_id = uploader.upload(
            video_path=args.video_file,
            title=args.title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy=args.privacy,
            is_shorts=args.shorts,
        )

        if not video_id:
            print("[FAILED] Upload did not complete.")
            sys.exit(1)

    # -- Command: produce (full pipeline) -----------------------------------
    elif args.command == "produce":
        if not keys["heygen_api_key"]:
            print("[ERROR] HEYGEN_API_KEY not found in .env file.")
            sys.exit(1)
        if not keys["elevenlabs_api_key"]:
            print("[ERROR] ELEVENLABS_API_KEY not found in .env file.")
            print("[ERROR] V2 pipeline requires ElevenLabs for natural voice audio.")
            sys.exit(1)

        tone = resolve_tone(args)
        is_shorts = args.duration == "short" or args.video_format == "shorts"
        pillar = getattr(args, "pillar", None)
        skip_compose = getattr(args, "skip_compose", False)
        no_music = getattr(args, "no_music", False)
        broll_dir_override = getattr(args, "broll_dir", None)

        total_steps = 6
        if skip_compose:
            total_steps = 4  # script, audio, video, SEO+upload
        if no_music:
            total_steps -= 1

        print(f"[Mode] FULL PIPELINE V2: Script -> Audio -> Lip-Sync -> Music -> Compose -> Upload")
        print(f"[Topic] {args.topic}")
        print(f"[Tone] {tone}  |  [Duration] {args.duration}  |  [Format] {args.video_format}")
        if pillar:
            print(f"[Pillar] {pillar}")
        print(f"[Privacy] {args.privacy}")
        if args.test:
            print("[Test Mode] ON")
        if args.skip_upload:
            print("[Upload] SKIPPED")
        if skip_compose:
            print("[Compose] SKIPPED (raw HeyGen video)")
        if no_music:
            print("[Music] SKIPPED")
        print()

        step = 0

        # ============================================================
        # Step 1: Generate script
        # ============================================================
        step += 1
        print("=" * 64)
        print(f"  STEP {step}: Generating Script")
        print("=" * 64)

        writer = ScriptWriter(
            topic=args.topic,
            tone=tone,
            duration=args.duration,
            series=args.series,
            pillar=pillar,
            is_shorts=is_shorts,
        )
        script_data = writer.generate()
        raw_path, annotated_path = save_script(script_data, args.topic)

        print()
        print("-" * 40)
        print(script_data["raw_text"][:500])
        if len(script_data["raw_text"]) > 500:
            print(f"... ({script_data['metadata']['word_count']} words total)")
        print("-" * 40)

        # ============================================================
        # Step 2: Generate voice audio via ElevenLabs
        # ============================================================
        step += 1
        print()
        print("=" * 64)
        print(f"  STEP {step}: Generating Voice Audio (ElevenLabs)")
        print("=" * 64)

        el_client = ElevenLabsClient(
            api_key=keys["elevenlabs_api_key"],
            voice_id=keys["elevenlabs_voice_id"],
        )
        audio_path = el_client.generate_audio(
            text=script_data["annotated_text"],
            title=args.topic,
            tone=tone,
        )

        if not audio_path:
            print("[WARN] ElevenLabs audio failed. Falling back to HeyGen TTS.")
            audio_path = None

        # ============================================================
        # Step 3: Generate avatar video (lip-sync or TTS fallback)
        # ============================================================
        step += 1
        print()
        print("=" * 64)
        if audio_path:
            print(f"  STEP {step}: Producing Lip-Synced Avatar Video (HeyGen)")
        else:
            print(f"  STEP {step}: Producing Avatar Video (HeyGen TTS fallback)")
        print("=" * 64)

        heygen = HeyGenClient(keys["heygen_api_key"])

        if audio_path:
            # V2: Lip-sync mode with ElevenLabs audio
            video_path = heygen.generate_video_with_audio(
                audio_path=audio_path,
                title=args.topic,
                video_format=args.video_format,
                tone=tone,
                test_mode=args.test,
            )
        else:
            # Fallback: HeyGen TTS mode (original behavior)
            video_path = heygen.generate_video(
                script_text=script_data["raw_text"],
                title=args.topic,
                video_format=args.video_format,
                tone=tone,
                test_mode=args.test,
                is_shorts=is_shorts,
            )

        if not video_path:
            print("[FAILED] Video generation failed. Pipeline stopped.")
            sys.exit(1)

        # ============================================================
        # Step 4: Generate background music (optional)
        # ============================================================
        music_path = None
        if not no_music and not skip_compose:
            step += 1
            print()
            print("=" * 64)
            print(f"  STEP {step}: Generating Background Music (ElevenLabs)")
            print("=" * 64)

            # Pick music preset based on pillar
            music_prompt = MUSIC_PRESETS.get(
                f"{pillar}_tutorial" if pillar else "art_tutorial",
                MUSIC_PRESETS.get("art_tutorial", "lo-fi chill instrumental background music")
            )

            music_path = el_client.generate_music(
                prompt=music_prompt,
                duration_ms=max(30000, script_data["metadata"]["estimated_seconds"] * 1000),
                title=f"bgm_{args.topic[:30]}",
            )

            if not music_path:
                print("[WARN] Music generation failed. Continuing without background music.")

        # ============================================================
        # Step 5: Compose final video (avatar + B-roll + music + text)
        # ============================================================
        final_video_path = video_path  # Default to raw HeyGen video

        if not skip_compose:
            step += 1
            print()
            print("=" * 64)
            print(f"  STEP {step}: Compositing Final Video")
            print("=" * 64)

            compositor = VideoCompositor(video_path)

            # Add background music
            if music_path:
                compositor.add_background_music(music_path)

            # Add B-roll if available
            broll_mgr = BRollManager(broll_dir_override)
            broll_clips = broll_mgr.get_clips(pillar=pillar, count=3)
            if broll_clips:
                compositor.add_broll(broll_clips)
            else:
                print("[Compositor] No B-roll clips found. Avatar-only video.")

            # Add intro text overlay (channel name + topic)
            compositor.add_text_overlay(
                text=f"Richard Abreu  |  {args.topic}",
                position="bottom",
                start=2,
                duration=COMP_INTRO_DURATION,
                font_size=36,
            )

            composed = compositor.compose(output_title=args.topic)
            if composed:
                final_video_path = composed
            else:
                print("[WARN] Composition failed. Using raw HeyGen video.")

        # ============================================================
        # Step N: Generate SEO metadata + Upload
        # ============================================================
        step += 1
        print()
        print("=" * 64)
        print(f"  STEP {step}: SEO Metadata + YouTube Upload")
        print("=" * 64)

        seo_gen = SEOGenerator(topic=args.topic, pillar=pillar, tone=tone)
        seo_data = seo_gen.generate()

        # Pick best title
        best_title = seo_data["titles"][0] if seo_data["titles"] else args.topic

        print(f"[SEO] Title: {best_title}")
        print(f"[SEO] Tags: {len(seo_data['tags'])}")

        # Save SEO data
        safe_topic = re.sub(r'[^\w\s-]', '', args.topic).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        seo_path = DOWNLOADS_DIR / f"seo_{safe_topic}_{timestamp}.json"
        with open(seo_path, "w", encoding="utf-8") as f:
            json.dump(seo_data, f, indent=2)
        print(f"[SEO] Saved to: {seo_path}")

        # Generate thumbnail suggestions
        thumb_gen = ThumbnailGenerator(topic=args.topic, pillar=pillar)
        thumb_data = thumb_gen.generate()
        print(f"\n[Thumbnail] Text suggestions:")
        for i, text in enumerate(thumb_data["thumbnail_texts"], 1):
            print(f"  {i}. {text}")

        # Upload to YouTube
        if args.skip_upload:
            print("\n[Upload] Skipped (--skip-upload flag)")
        elif not keys.get("google_client_id"):
            print("\n[Upload] Skipped (no Google OAuth credentials)")
        else:
            uploader = YouTubeUploader(keys["google_client_id"], keys["google_client_secret"])
            category_id = YouTubeUploader.CATEGORY_MAP.get(pillar, "22") if pillar else "22"

            video_id = uploader.upload(
                video_path=final_video_path,
                title=best_title,
                description=seo_data["description"],
                tags=seo_data["tags"],
                category_id=category_id,
                privacy=args.privacy,
                is_shorts=is_shorts,
            )

            if not video_id:
                print("[WARN] Upload failed, but video was produced successfully.")

        # Print summary
        print()
        print("=" * 64)
        print("  PIPELINE V2 COMPLETE")
        print("=" * 64)
        print(f"  Script:     {raw_path}")
        print(f"  Annotated:  {annotated_path}")
        if audio_path:
            print(f"  Voice:      {audio_path}")
        print(f"  Avatar:     {video_path}")
        if music_path:
            print(f"  Music:      {music_path}")
        if final_video_path != video_path:
            print(f"  Final:      {final_video_path}")
        print(f"  SEO:        {seo_path}")
        print(f"  Title:      {best_title}")
        print("=" * 64)

    # -- Command: broll -----------------------------------------------------
    elif args.command == "broll":
        manager = BRollManager()

        if args.broll_action == "list":
            print("[BRoll] Listing clips...")
            if args.pillar:
                print(f"[BRoll] Filtering by pillar: {args.pillar}")
            print()

            clips = manager.list_clips(pillar=getattr(args, "pillar", None))
            if not clips:
                print("[BRoll] No clips found.")
            else:
                total = 0
                for pillar_name, pillar_clips in sorted(clips.items()):
                    print(f"  {pillar_name}/ ({len(pillar_clips)} clips)")
                    for clip in sorted(pillar_clips, key=lambda c: c.name):
                        size_mb = clip.stat().st_size / (1024 * 1024)
                        print(f"    - {clip.name}  ({size_mb:.1f} MB)")
                        total += 1
                    print()
                print(f"[BRoll] Total: {total} clip(s)")

        elif args.broll_action == "add":
            src = Path(args.file_path)
            if not src.exists():
                print(f"[BRoll] ERROR: File not found: {src}")
                sys.exit(1)
            if not src.is_file():
                print(f"[BRoll] ERROR: Not a file: {src}")
                sys.exit(1)

            dest_dir = BROLL_DIR / args.pillar
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name

            print(f"[BRoll] Copying {src.name} -> {dest_dir}/")
            shutil.copy2(str(src), str(dest))
            print(f"[BRoll] Added: {dest}")

        elif args.broll_action == "download":
            dest_dir = BROLL_DIR / args.pillar
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Extract filename from URL
            url_path = args.url.split("?")[0]
            filename = url_path.split("/")[-1]
            if not filename or "." not in filename:
                filename = f"broll_{args.pillar}_{int(time.time())}.mp4"
            dest = dest_dir / filename

            print(f"[BRoll] Downloading from: {args.url}")
            print(f"[BRoll] Destination: {dest}")

            try:
                resp = requests.get(args.url, stream=True, timeout=120)
                resp.raise_for_status()

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            pct = (downloaded / total_size) * 100
                            print(f"\r[BRoll] Progress: {pct:.0f}%", end="", flush=True)

                if total_size:
                    print()  # newline after progress

                size_mb = dest.stat().st_size / (1024 * 1024)
                print(f"[BRoll] Downloaded: {dest} ({size_mb:.1f} MB)")

            except requests.RequestException as e:
                print(f"[BRoll] ERROR: Download failed: {e}")
                if dest.exists():
                    dest.unlink()
                sys.exit(1)

    # -- Command: thumbnail -------------------------------------------------
    elif args.command == "thumbnail":
        print(f"[Mode] Thumbnail text generation")
        print(f"[Topic] {args.topic}")
        if args.pillar:
            print(f"[Pillar] {args.pillar}")
        print()

        gen = ThumbnailGenerator(topic=args.topic, pillar=args.pillar)
        data = gen.generate()

        print("-" * 64)
        print("THUMBNAIL TEXT OPTIONS (max 5 words, ALL CAPS):")
        print("-" * 64)
        for i, text in enumerate(data["thumbnail_texts"], 1):
            print(f"  {i}. {text}")

        print()
        print("STYLE GUIDE:")
        print(f"  Font size: {data['style_guide']['font_size']}")
        print(f"  Show face: {data['style_guide']['show_face']}")
        print(f"  Accent colors: {', '.join(data['style_guide']['accent_colors'])}")

    # -- Command: image -----------------------------------------------------
    elif args.command == "image":
        gemini_key = keys.get("gemini_api_key")
        if not gemini_key:
            print("[ERROR] GEMINI_API_KEY not found in .env file.")
            print("[ERROR] Add GEMINI_API_KEY=your_key to shopify-theme/.env")
            sys.exit(1)

        img_gen = ImageGenerator(api_key=gemini_key)

        if args.image_action == "models":
            img_gen.list_models()

        elif args.image_action == "broll":
            print(f"[Mode] B-roll image generation via Gemini")
            print(f"[Pillar] {args.pillar}")
            print(f"[Count] {args.count}")
            print(f"[Model] {args.model}")
            if args.prompt:
                print(f"[Custom prompt] {args.prompt[:80]}...")
            print()

            paths = img_gen.generate_broll(
                pillar=args.pillar,
                count=args.count,
                model=args.model,
                custom_prompt=args.prompt,
            )
            if paths:
                print()
                print(f"[ImageGen] {len(paths)} image(s) saved to: {BROLL_DIR / args.pillar}/")

        elif args.image_action == "thumbnail":
            print(f"[Mode] AI thumbnail image generation via Gemini")
            print(f"[Topic] {args.topic}")
            print(f"[Model] {args.model}")
            if args.text:
                print(f"[Text overlay] {args.text}")
            print()

            path = img_gen.generate_thumbnail(
                topic=args.topic,
                pillar=getattr(args, "pillar", None),
                text_overlay=args.text,
                model=args.model,
            )
            if path:
                print(f"\n[ImageGen] Thumbnail ready: {path}")

    # -- Command: setup-auth ------------------------------------------------
    elif args.command == "setup-auth":
        if not keys.get("google_client_id") or not keys.get("google_client_secret"):
            print("[ERROR] GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET not found in .env file.")
            sys.exit(1)

        print("[Mode] YouTube OAuth2 setup")
        print()

        uploader = YouTubeUploader(keys["google_client_id"], keys["google_client_secret"])
        if not uploader.setup_auth():
            sys.exit(1)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
