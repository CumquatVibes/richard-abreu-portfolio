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
    python produce_video.py thumbnail "Topic" --pillar art
    python produce_video.py setup-auth

All API keys are read from the shopify-theme .env file.
Brand settings are read from brand_config.json.
"""

import argparse
import json
import os
import random
import re
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
HEYGEN_AVATAR_ID = _avatar_cfg.get("avatar_id", "1edeaab5994541c9a5df49d8353c2b9c")
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

# ElevenLabs endpoints
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_MUSIC_URL = "https://api.elevenlabs.io/v1/music"
ELEVENLABS_SFX_URL = "https://api.elevenlabs.io/v1/sound-generation"

# Music and SFX presets from brand config
MUSIC_PRESETS = BRAND.get("music_presets", {})
SFX_PRESETS = BRAND.get("sound_effects", {})

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

    def generate_video(self, script_text, title="video",
                       video_format="landscape", tone="professional",
                       test_mode=False, is_shorts=False):
        """
        Submit a video generation job to HeyGen.

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
        """
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]

        # If script is short enough, single scene
        if len(paragraphs) <= 2:
            return [self._make_scene("\n\n".join(paragraphs), speed, emotion)]

        # Multi-scene: group paragraphs into 2-3 scenes
        bg_keys = list(HEYGEN_BACKGROUNDS.keys()) if HEYGEN_BACKGROUNDS else ["default"]
        scenes = []
        chunk_size = max(1, len(paragraphs) // 3)
        for i in range(0, len(paragraphs), chunk_size):
            chunk = paragraphs[i:i + chunk_size]
            text = " ".join(chunk)
            if text:
                # Cycle through background options for visual variety
                bg_key = bg_keys[len(scenes) % len(bg_keys)]
                bg = HEYGEN_BACKGROUNDS.get(bg_key, {"type": "color", "value": BACKGROUND_COLOR})
                scenes.append(self._make_scene(text, speed, emotion, bg))

        return scenes if scenes else [self._make_scene(script_text, speed, emotion)]

    def _make_scene(self, text, speed, emotion=None, background=None):
        """Create a single HeyGen scene dict with emotion and background."""
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
        print("[ElevenLabs] Generating audio...")

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
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

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
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
                "redirect_uris": ["http://localhost:8080/"],
            }
        }

        print("[YouTube] Starting OAuth2 consent flow...")
        print("[YouTube] A browser window will open. Sign in and grant YouTube upload access.")

        flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)
        credentials = flow.run_local_server(port=8080, prompt="consent")

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

    # -- produce ------------------------------------------------------------
    produce_parser = subparsers.add_parser(
        "produce",
        help="Full pipeline: script -> video -> SEO -> upload (end-to-end)",
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

        tone = resolve_tone(args)
        is_shorts = args.duration == "short" or args.video_format == "shorts"
        pillar = getattr(args, "pillar", None)

        print(f"[Mode] FULL PIPELINE: Script -> Video -> SEO -> Upload")
        print(f"[Topic] {args.topic}")
        print(f"[Tone] {tone}  |  [Duration] {args.duration}  |  [Format] {args.video_format}")
        if pillar:
            print(f"[Pillar] {pillar}")
        print(f"[Privacy] {args.privacy}")
        if args.test:
            print("[Test Mode] ON")
        if args.skip_upload:
            print("[Upload] SKIPPED")
        print()

        # Step 1: Generate script
        print("=" * 64)
        print("  STEP 1/4: Generating Script")
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

        # Step 2: Generate video via HeyGen
        print()
        print("=" * 64)
        print("  STEP 2/4: Producing Video (HeyGen)")
        print("=" * 64)

        heygen = HeyGenClient(keys["heygen_api_key"])
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

        # Step 3: Generate SEO metadata
        print()
        print("=" * 64)
        print("  STEP 3/4: Generating SEO Metadata")
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

        # Step 4: Upload to YouTube
        print()
        print("=" * 64)
        print("  STEP 4/4: Uploading to YouTube")
        print("=" * 64)

        if args.skip_upload:
            print("[Upload] Skipped (--skip-upload flag)")
        elif not keys.get("google_client_id"):
            print("[Upload] Skipped (no Google OAuth credentials)")
        else:
            uploader = YouTubeUploader(keys["google_client_id"], keys["google_client_secret"])
            category_id = YouTubeUploader.CATEGORY_MAP.get(pillar, "22") if pillar else "22"

            video_id = uploader.upload(
                video_path=video_path,
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
        print("  PIPELINE COMPLETE")
        print("=" * 64)
        print(f"  Script:    {raw_path}")
        print(f"  Annotated: {annotated_path}")
        print(f"  Video:     {video_path}")
        print(f"  SEO:       {seo_path}")
        print(f"  Title:     {best_title}")
        print("=" * 64)

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
