#!/usr/bin/env python3
"""Generate RichMind and How to Use AI scripts via Gemini API."""

import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not set")
    sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "scripts")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Emotion engine prompt addon — appended to all script generation prompts
EMOTION_ADDON = """

IMPORTANT: Add ElevenLabs emotion audio tags to make the voiceover more expressive. Use tags like [whispers], [pauses], [excited], [curious], [gasps], [sighs], [confident], [softly], [firmly], [urgently] at the START of sentences to guide vocal delivery. Use ellipses (...) for dramatic pauses. Use CAPS for 1-2 key emphasis words per paragraph. Match the emotional arc: hook with intrigue, build tension/curiosity, deliver with confidence, close with energy. Maximum 1-2 tags per paragraph — don't over-tag."""

SCRIPTS = [
    # RichMind scripts
    {
        "channel": "RichMind",
        "topic": "7 Dark Psychology Tricks That Manipulators Use on You Every Day",
        "format": "Listicle",
        "words": 1200,
        "duration": "8-10 minutes",
        "prompt": """Write a YouTube video script for the channel "RichMind" — a faceless psychology channel.

Topic: 7 Dark Psychology Tricks That Manipulators Use on You Every Day
Format: Listicle (count down from 7 to 1, with #1 being the most powerful)
Target: ~1200 words, 8-10 minutes when spoken
Tone: Mysterious, authoritative narrator. Use dramatic pauses (...), rhetorical questions, and tension-building.
Voice: Deep, confident storyteller — NOT casual or chatty. Think documentary narrator.

Requirements:
- Start with a strong hook that creates curiosity and urgency
- Each trick should include: the name, how it works, a real-life example, and how to defend against it
- Include 6-8 [VISUAL: ...] directions throughout for dark/moody imagery, silhouettes, brain graphics
- Include a [CROSS-PROMO] block near the end referencing sister channels "RichHorror" (for more unsettling content) and "How to Use AI" (for AI-powered self-improvement)
- End with a CTA: like, subscribe, hit bell, check description links
- Add a metadata header block at the top:
  # Channel: RichMind
  # Topic: {topic}
  # Format: Listicle
  # Words: ~1200
  # Est Duration: 8-10 minutes
  # Generated: {timestamp}

Do NOT use casual greetings like "hey guys". Start with atmosphere and intrigue."""
    },
    {
        "channel": "RichMind",
        "topic": "Why You Can't Stop Overthinking (The Psychology Behind It)",
        "format": "Explainer",
        "words": 1500,
        "duration": "10-12 minutes",
        "prompt": """Write a YouTube video script for the channel "RichMind" — a faceless psychology channel.

Topic: Why You Can't Stop Overthinking (The Psychology Behind It)
Format: Explainer (deep dive into the psychology of overthinking)
Target: ~1500 words, 10-12 minutes when spoken
Tone: Mysterious, authoritative narrator. Use dramatic pauses (...), rhetorical questions, and tension-building.
Voice: Deep, confident storyteller — NOT casual or chatty. Think documentary narrator.

Requirements:
- Start with a strong hook about how the viewer's own brain is working against them
- Cover: what overthinking actually is neurologically, the anxiety-overthinking loop, cognitive distortions that fuel it, evolutionary psychology behind it, and practical techniques to break free
- Include 6-8 [VISUAL: ...] directions for brain imagery, neural pathways, dark moody graphics, anxiety visualizations
- Include a [CROSS-PROMO] block referencing sister channels "How to Meditate" (for mindfulness techniques) and "RichHorror" (for more content about what keeps you up at night)
- End with a CTA: like, subscribe, hit bell, check description
- Add a metadata header block at the top:
  # Channel: RichMind
  # Topic: {topic}
  # Format: Explainer
  # Words: ~1500
  # Est Duration: 10-12 minutes
  # Generated: {timestamp}

Do NOT use casual greetings. Start with atmosphere and intrigue."""
    },
    {
        "channel": "RichMind",
        "topic": "5 Body Language Signs Someone Is Lying to Your Face",
        "format": "Listicle",
        "words": 1200,
        "duration": "8-10 minutes",
        "prompt": """Write a YouTube video script for the channel "RichMind" — a faceless psychology channel.

Topic: 5 Body Language Signs Someone Is Lying to Your Face
Format: Listicle (count down from 5 to 1, #1 is the most reliable indicator)
Target: ~1200 words, 8-10 minutes when spoken
Tone: Mysterious, authoritative narrator. Use dramatic pauses (...), rhetorical questions.
Voice: Deep, confident storyteller — NOT casual or chatty. Think documentary narrator.

Requirements:
- Start with a hook about how everyone you know has lied to you — and you probably missed it
- Each sign should include: the behavior, the psychology behind it, a real-world scenario, and a caveat (to avoid armchair psychology)
- Include 6-8 [VISUAL: ...] directions for close-up facial expressions, body language demos, split-screen comparisons
- Include a [CROSS-PROMO] block referencing "RichHorror" (for true crime stories with deceptive suspects) and "Eva Reyes - Inspire & Empower" (for building authentic relationships)
- End with a CTA: like, subscribe, hit bell, check description
- Add a metadata header block at the top:
  # Channel: RichMind
  # Topic: {topic}
  # Format: Listicle
  # Words: ~1200
  # Est Duration: 8-10 minutes
  # Generated: {timestamp}

Do NOT use casual greetings. Start with atmosphere and intrigue."""
    },
    # How to Use AI scripts
    {
        "channel": "HowToUseAI",
        "topic": "ChatGPT Prompt Engineering: The Complete Beginner's Guide",
        "format": "Tutorial",
        "words": 1500,
        "duration": "12-15 minutes",
        "prompt": """Write a YouTube video script for the channel "How to Use AI" — a faceless AI tutorial channel.

Topic: ChatGPT Prompt Engineering: The Complete Beginner's Guide
Format: Tutorial (step-by-step with examples)
Target: ~1500 words, 12-15 minutes when spoken
Tone: Confident, knowledgeable, friendly but professional. Like a cool tech mentor.
Voice: Clear, energetic male narrator.

Requirements:
- Start with a hook about how most people use ChatGPT wrong and leave 90% of its power on the table
- Cover: what prompt engineering is, the anatomy of a perfect prompt (role, context, task, format, constraints), 5 practical prompt frameworks with before/after examples, common mistakes
- Include 8-10 [VISUAL: ...] directions for screen recordings of ChatGPT, side-by-side prompt comparisons, animated diagrams
- Include a [CROSS-PROMO] block referencing sister channels "RichTech" (for latest AI hardware) and "RichBusiness" (for AI business strategies)
- End with a CTA: like, subscribe, hit bell, free prompt engineering cheat sheet in description
- Add a metadata header block at the top:
  # Channel: How to Use AI
  # Topic: {topic}
  # Format: Tutorial
  # Words: ~1500
  # Est Duration: 12-15 minutes
  # Generated: {timestamp}"""
    },
    {
        "channel": "HowToUseAI",
        "topic": "10 AI Tools That Will Save You 10 Hours Every Week",
        "format": "Listicle",
        "words": 1200,
        "duration": "8-10 minutes",
        "prompt": """Write a YouTube video script for the channel "How to Use AI" — a faceless AI tutorial channel.

Topic: 10 AI Tools That Will Save You 10 Hours Every Week
Format: Listicle (rapid-fire, 10 tools with practical use cases)
Target: ~1200 words, 8-10 minutes when spoken
Tone: Confident, knowledgeable, friendly but professional. Excited about the tools.
Voice: Clear, energetic male narrator.

Requirements:
- Start with a hook about how you're wasting hours on tasks AI can do in seconds
- Each tool should include: name, what it does, a specific use case, and approximate time saved per week
- Mix of categories: writing, design, scheduling, email, coding, social media, data analysis, video, research, automation
- Include 8-10 [VISUAL: ...] directions for screen recordings of each tool, before/after workflows, time-saved graphics
- Include a [CROSS-PROMO] block referencing "RichTech" (for hardware to run AI tools) and "RichDesign" (for AI design tools deep dives)
- End with a CTA: like, subscribe, hit bell, all tools linked in description
- Add a metadata header block at the top:
  # Channel: How to Use AI
  # Topic: {topic}
  # Format: Listicle
  # Words: ~1200
  # Est Duration: 8-10 minutes
  # Generated: {timestamp}"""
    },
    {
        "channel": "HowToUseAI",
        "topic": "How to Build an AI Automation That Makes Money While You Sleep",
        "format": "Explainer",
        "words": 1500,
        "duration": "10-12 minutes",
        "prompt": """Write a YouTube video script for the channel "How to Use AI" — a faceless AI tutorial channel.

Topic: How to Build an AI Automation That Makes Money While You Sleep
Format: Explainer (concept + step-by-step implementation)
Target: ~1500 words, 10-12 minutes when spoken
Tone: Confident, knowledgeable, slightly hype but backed by substance. Like a tech entrepreneur mentor.
Voice: Clear, energetic male narrator.

Requirements:
- Start with a hook about passive income being real when you pair AI with automation
- Cover: the concept of AI automation funnels, 3 specific automation examples (content repurposing pipeline, AI customer service bot, automated lead generation), tools needed (Make.com, Zapier, ChatGPT API, etc.), realistic income expectations
- Include 8-10 [VISUAL: ...] directions for workflow diagrams, screen recordings of automation platforms, income dashboards
- Include a [CROSS-PROMO] block referencing "RichBusiness" (for business strategy) and "RichFinance" (for managing your AI income)
- End with a CTA: like, subscribe, hit bell, free automation template in description
- Add a metadata header block at the top:
  # Channel: How to Use AI
  # Topic: {topic}
  # Format: Explainer
  # Words: ~1500
  # Est Duration: 10-12 minutes
  # Generated: {timestamp}"""
    },
]


def call_gemini(prompt, topic, timestamp):
    """Call Gemini API and return generated text."""
    prompt = prompt.replace("{timestamp}", timestamp).replace("{topic}", topic)
    prompt += EMOTION_ADDON

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 4096
        }
    }).encode("utf-8")

    req = Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        print(f"  API Error {e.code}: {error_body[:200]}")
        return None


def slugify(text):
    """Convert text to filename-safe slug."""
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '_', text.strip())
    return text


def main():
    print(f"Generating {len(SCRIPTS)} scripts via Gemini API...")
    print(f"Timestamp: {TIMESTAMP}\n")

    generated = []

    for i, script_cfg in enumerate(SCRIPTS, 1):
        channel = script_cfg["channel"]
        topic = script_cfg["topic"]
        slug = slugify(topic)
        filename = f"{channel}_{slug}_{TIMESTAMP}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        print(f"[{i}/{len(SCRIPTS)}] {channel}: {topic}")

        text = call_gemini(script_cfg["prompt"], topic, TIMESTAMP)

        if text:
            with open(filepath, "w") as f:
                f.write(text)
            word_count = len(text.split())
            print(f"  -> Saved ({word_count} words): {filename}")
            generated.append({"channel": channel, "topic": topic, "file": filename, "words": word_count})
        else:
            print(f"  -> FAILED")

        if i < len(SCRIPTS):
            time.sleep(1)

    print(f"\nDone! Generated {len(generated)}/{len(SCRIPTS)} scripts.")
    for g in generated:
        print(f"  {g['channel']}: {g['topic']} ({g['words']} words)")


if __name__ == "__main__":
    main()
