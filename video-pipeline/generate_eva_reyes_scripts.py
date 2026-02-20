#!/usr/bin/env python3
"""Generate Eva Reyes - Inspire & Empower channel scripts via Gemini API.

Eva Reyes is a FACELESS women's empowerment channel using a FEMALE voice.
Topics optimized for high search volume and CTR.
"""

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

EMOTION_ADDON = """

IMPORTANT — ElevenLabs Emotion Tags:
Add emotion audio tags to make the voiceover more expressive. Use tags like [cheerfully], [confident], [tender], [excited], [pauses], [softly], [firmly] at the START of sentences.
This is a WARM FEMALE VOICE — confident, empowering, like a supportive best friend who happens to be a life coach.
Use ellipses (...) for dramatic pauses. Use CAPS for 1-2 key emphasis words per paragraph.
Emotional arc: hook with relatable vulnerability → build with empowering insight → deliver with confidence → close with warmth.
Maximum 1-2 tags per paragraph — don't over-tag."""

HOOK_RULES = """

HOOK & RETENTION (CRITICAL — this determines whether people stay or leave):
- The FIRST 15 SECONDS must contain a bold, relatable statement that makes the viewer think "that's me"
- Do NOT start with "welcome to..." or slow intros. Pattern-interrupt IMMEDIATELY.
- Example: "You've been told your whole life to be nice, stay quiet, and not make waves. And that advice? It's been DESTROYING you."
- After the hook, preview what's coming: "In the next 8 minutes, you'll learn the 7 habits..."
- Include 2-3 retention hooks throughout ("but the next one changed everything for me")
- Add [CHAPTER: section name] markers at each major section for YouTube chapter timestamps
- For listicles, lead with the 2nd most powerful item, save #1 for last
- Target 1500+ words for 8-12 minute optimal video length
"""

SCRIPTS = [
    {
        "channel": "EvaReyes",
        "topic": "7 Signs You're a Stronger Woman Than You Think",
        "format": "Listicle",
        "prompt": f"""Write a YouTube video script for the channel "Eva Reyes - Inspire & Empower" — a FACELESS women's empowerment channel.

Topic: 7 Signs You're a Stronger Woman Than You Think
Format: Listicle (count down from 7 to 1, with #1 being the most powerful sign)
Target: ~1500 words, 8-10 minutes when spoken
Tone: Warm, confident, empowering. Like a supportive best friend who believes in you.
Voice: Warm FEMALE narrator — NOT male. Confident, nurturing, occasionally playful.

Requirements:
- This is a FACELESS channel — NO references to "me", "my face", "as you can see"
- Use "you", "we", "let's" — speak directly to the viewer
- Start with a POWERFUL hook in the first 15 seconds — a relatable statement that makes women think "that's me"
- Each sign should include: the behavior, why it signals strength, a real-life scenario women will recognize, and an affirmation
- Include 8-10 [VISUAL: ...] directions for empowering imagery — sunrise, mountain tops, confident women silhouettes, journaling, mirror reflections
- Include a [CROSS-PROMO] block near the end referencing sister channels "RichMind" (for psychology of confidence) and "How to Meditate" (for mindfulness practices)
- End with a warm, empowering CTA: like, subscribe, share with a woman who needs to hear this
- Add [CHAPTER: section name] markers at each major section for YouTube timestamps
- Add a metadata header block at the top:
  # Channel: Eva Reyes - Inspire & Empower
  # Topic: {{topic}}
  # Format: Listicle
  # Words: ~1500
  # Est Duration: 8-10 minutes
  # Generated: {{timestamp}}
  # Voice: warm_female

Do NOT use casual "hey guys" or "hey girl" greetings. Start with power and vulnerability.
{HOOK_RULES}"""
    },
    {
        "channel": "EvaReyes",
        "topic": "5 Toxic Habits Women Need to Stop Normalizing in 2026",
        "format": "Listicle",
        "prompt": f"""Write a YouTube video script for the channel "Eva Reyes - Inspire & Empower" — a FACELESS women's empowerment channel.

Topic: 5 Toxic Habits Women Need to Stop Normalizing in 2026
Format: Listicle (count down from 5 to 1, #1 is the most damaging habit)
Target: ~1500 words, 8-10 minutes when spoken
Tone: Warm but FIRM. Honest, no-BS empowerment. Think: tough love from someone who genuinely cares.
Voice: Warm FEMALE narrator — NOT male. Confident, direct, compassionate.

Requirements:
- This is a FACELESS channel — NO self-references
- Start with a BOLD hook in first 15 seconds: something like "There are 5 things women do every single day that are slowly killing their confidence... and most don't even realize it."
- Each habit should include: the behavior, why it's toxic (backed by psychology), how to recognize it in yourself, and a specific replacement behavior
- Habits to cover: people-pleasing at the expense of self, apologizing for existing, comparing on social media, staying in relationships out of fear, ignoring your own needs
- Include 8-10 [VISUAL: ...] directions — broken mirror, woman walking away from toxic situation, phone scrolling, journaling, sunrise fresh start
- Include a [CROSS-PROMO] block referencing "RichMind" (for psychology of breaking patterns) and "RichFitness" (for building physical and mental strength)
- End with empowering CTA: "share this with someone who needs to hear it"
- Add [CHAPTER: section name] markers at each major section
- Add metadata header:
  # Channel: Eva Reyes - Inspire & Empower
  # Topic: {{topic}}
  # Format: Listicle
  # Words: ~1500
  # Est Duration: 8-10 minutes
  # Generated: {{timestamp}}
  # Voice: warm_female

Do NOT use "hey girl" or "welcome back queens." Start with impact.
{HOOK_RULES}"""
    },
    {
        "channel": "EvaReyes",
        "topic": "How to Build Unshakeable Confidence as a Woman (Even If You Feel Invisible)",
        "format": "Explainer",
        "prompt": f"""Write a YouTube video script for the channel "Eva Reyes - Inspire & Empower" — a FACELESS women's empowerment channel.

Topic: How to Build Unshakeable Confidence as a Woman (Even If You Feel Invisible)
Format: Explainer (deep dive into building genuine confidence)
Target: ~1800 words, 10-12 minutes when spoken
Tone: Warm, deeply empathetic, building to powerful and confident. Think: TEDx talk energy.
Voice: Warm FEMALE narrator — NOT male. Vulnerable at first, building to confident and inspiring.

Requirements:
- This is a FACELESS channel — NO self-references
- Start with a VULNERABLE, relatable hook in first 15 seconds: "Have you ever walked into a room... and felt like you were completely invisible? Like no one noticed you were even there?"
- Cover these sections: why women specifically struggle with confidence (societal conditioning), the neuroscience of self-doubt, 3 practical daily practices that rewire confidence, the difference between real confidence and fake-it-til-you-make-it, and a powerful closing affirmation
- Include 8-10 [VISUAL: ...] directions — woman standing alone in crowd, brain neural pathways lighting up, mirror affirmation scene, woman power-posing, sunrise over mountains
- Include specific actionable techniques: morning affirmation script, the "5-second rule" for social courage, body language power poses
- Include a [CROSS-PROMO] block referencing "How to Meditate" (for mindfulness confidence practices) and "RichMind" (for understanding the psychology of self-worth)
- End with a POWERFUL affirmation the viewer can repeat, then CTA
- Add [CHAPTER: section name] markers at each major section
- Add metadata header:
  # Channel: Eva Reyes - Inspire & Empower
  # Topic: {{topic}}
  # Format: Explainer
  # Words: ~1800
  # Est Duration: 10-12 minutes
  # Generated: {{timestamp}}
  # Voice: warm_female

Do NOT start with greetings. Start with vulnerability that hooks immediately.
{HOOK_RULES}"""
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
            "maxOutputTokens": 8192
        }
    }).encode("utf-8")

    req = Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=90) as resp:
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
    print("Eva Reyes - Inspire & Empower")
    print("Generating scripts via Gemini API...")
    print(f"Voice: warm_female (dedicated female narrator)")
    print(f"Timestamp: {TIMESTAMP}\n")

    generated = []

    for i, script_cfg in enumerate(SCRIPTS, 1):
        channel = script_cfg["channel"]
        topic = script_cfg["topic"]
        slug = slugify(topic)
        filename = f"{channel}_{slug}_{TIMESTAMP}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        print(f"[{i}/{len(SCRIPTS)}] {topic}")

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
            time.sleep(2)

    print(f"\nDone! Generated {len(generated)}/{len(SCRIPTS)} scripts.")
    for g in generated:
        print(f"  {g['channel']}: {g['topic']} ({g['words']} words)")

    if generated:
        print(f"\nNext steps:")
        print(f"  1. Generate voiceovers: python3 generate_voiceovers.py")
        print(f"  2. Generate B-roll: python3 generate_broll.py output/scripts/{generated[0]['file']}")
        print(f"  3. Assemble video: python3 assemble_video.py")
        print(f"  4. Upload: python3 upload_to_youtube.py")


if __name__ == "__main__":
    main()
