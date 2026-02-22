"""B-roll image generation via Gemini API.

Shared module for channel-aware B-roll generation with rate limiting and retry.
"""

import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROLL_DIR = os.path.join(BASE_DIR, "output", "broll")

# API config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_MODEL = "gemini-2.5-flash-image"

# Rate limiting
_last_api_call = 0
MIN_DELAY = 5  # seconds between API calls
BACKOFF_429 = 30  # base seconds to wait after rate limit

# Channel-specific B-roll styles
CHANNEL_BROLL_TEMPLATES = {
    "RichMind": {
        "prefix": "Cinematic 16:9 aspect ratio, dark moody aesthetic, high contrast, professional video B-roll shot.",
        "suffix": "Ultra-realistic, photographic quality, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichHorror": {
        "prefix": "Cinematic 16:9, horror atmosphere, desaturated colors, deep shadows, eerie lighting.",
        "suffix": "Photorealistic, unsettling, no text, no gore, psychological horror aesthetic.",
        "segment_duration": 6,
    },
    "RichTech": {
        "prefix": "Clean modern 16:9, tech aesthetic, neon accents, sleek minimalist design.",
        "suffix": "Professional product photography style, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "HowToUseAI": {
        "prefix": "Clean modern 16:9, tech aesthetic, digital workflow visualization.",
        "suffix": "Professional, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichPets": {
        "prefix": "Warm natural 16:9, soft lighting, friendly atmosphere, professional pet photography.",
        "suffix": "Photorealistic, heartwarming, cute, no text, no watermarks.",
        "segment_duration": 8,
    },
    "EvaReyes": {
        "prefix": "Cinematic 16:9, warm golden-hour lighting, empowering feminine aesthetic, elegant and confident mood.",
        "suffix": "Photorealistic, inspiring, soft bokeh background, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichFinance": {
        "prefix": "Clean 16:9, professional finance aesthetic, neutral tones, charts and modern office environments.",
        "suffix": "Professional, corporate photography style, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichCrypto": {
        "prefix": "Futuristic 16:9, blockchain aesthetic, dark background with glowing blue/green digital elements.",
        "suffix": "High-tech, cinematic, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichFitness": {
        "prefix": "Dynamic 16:9, gym/outdoor fitness aesthetic, high energy, natural lighting, athletic environment.",
        "suffix": "Photorealistic, motivational, action-oriented, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichCooking": {
        "prefix": "Warm 16:9, food photography aesthetic, overhead kitchen shots, natural warm lighting, appetizing colors.",
        "suffix": "Food magazine quality, appetizing, sharp focus, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichNature": {
        "prefix": "Cinematic 16:9, nature documentary aesthetic, vivid natural colors, golden hour or dramatic skies.",
        "suffix": "National Geographic quality, breathtaking, sharp focus, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichScience": {
        "prefix": "Clean 16:9, science visualization, laboratory or space aesthetic, cool blue tones.",
        "suffix": "Educational, professional, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichHistory": {
        "prefix": "Cinematic 16:9, historical atmosphere, sepia and muted earth tones, dramatic lighting.",
        "suffix": "Documentary-grade, evocative, period-appropriate, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichReviews": {
        "prefix": "Clean modern 16:9, product showcase aesthetic, studio lighting, white/neutral background.",
        "suffix": "Product photography quality, crisp detail, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichGaming": {
        "prefix": "Vibrant 16:9, gaming aesthetic, RGB lighting, neon accents, dark background with colorful highlights.",
        "suffix": "High-energy, dynamic, sharp focus, no text, no watermarks.",
        "segment_duration": 6,
    },
    "RichMusic": {
        "prefix": "Cinematic 16:9, music/concert aesthetic, dramatic stage lighting, moody atmosphere.",
        "suffix": "Concert photography quality, atmospheric, vibrant, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichTravel": {
        "prefix": "Cinematic 16:9, travel photography, vibrant colors, golden hour, scenic landscapes and architecture.",
        "suffix": "Travel magazine quality, wanderlust-inspiring, sharp focus, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichDIY": {
        "prefix": "Warm 16:9, workshop aesthetic, natural lighting, hands-on crafting environment, organized workspace.",
        "suffix": "Instructional quality, clear detail, sharp focus, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichDesign": {
        "prefix": "Clean modern 16:9, design studio aesthetic, minimalist, creative workspace, color palettes.",
        "suffix": "Design portfolio quality, artistic, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "HowToMeditate": {
        "prefix": "Serene 16:9, meditation aesthetic, soft natural lighting, peaceful nature scenes, zen atmosphere.",
        "suffix": "Calming, tranquil, soft focus edges, no text, no watermarks.",
        "segment_duration": 10,
    },
    "RichBusiness": {
        "prefix": "Professional 16:9, business aesthetic, modern office, confident entrepreneurial environment.",
        "suffix": "Corporate photography quality, professional, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "CumquatMotivation": {
        "prefix": "Cinematic 16:9, motivational aesthetic, sunrise/sunset lighting, powerful and uplifting atmosphere.",
        "suffix": "Inspiring, epic composition, sharp focus, no text, no watermarks.",
        "segment_duration": 8,
    },
    "RichMovie": {
        "prefix": "Cinematic 16:9, film aesthetic, dramatic lighting, movie-poster style compositions.",
        "suffix": "Hollywood production quality, cinematic, sharp focus, no text, no watermarks.",
        "segment_duration": 7,
    },
    "RichComedy": {
        "prefix": "Bright 16:9, comedic aesthetic, vibrant saturated colors, playful lighting, fun atmosphere.",
        "suffix": "Energetic, entertaining, sharp focus, no text, no watermarks.",
        "segment_duration": 6,
    },
    "CumquatVibes": {
        "prefix": "Cinematic 16:9, dark matte studio #101922 background, orange #e8941f accent lighting, premium creator brand aesthetic, art and design focus.",
        "suffix": "Personal brand quality, artistic, bold creator energy, sharp focus, no text, no watermarks.",
        "segment_duration": 8,
    },
}

DEFAULT_TEMPLATE = {
    "prefix": "Cinematic 16:9 aspect ratio, professional video B-roll shot, high quality lighting.",
    "suffix": "Ultra-realistic, photographic quality, no text, no watermarks.",
    "segment_duration": 7,
}


def get_broll_template(channel):
    """Get B-roll template config for a channel.

    Returns dict with keys: prefix, suffix, segment_duration
    """
    return CHANNEL_BROLL_TEMPLATES.get(channel, DEFAULT_TEMPLATE)


def extract_visuals(script_path):
    """Extract visual directions from a script.

    Supports both formats:
    - [VISUAL: description] (standard)
    - **(Visual: description)** (fix_overthinking format)
    """
    with open(script_path) as f:
        content = f.read()

    # Try standard format first
    visuals = re.findall(r'\[VISUAL:\s*(.+?)\]', content)
    if visuals:
        return visuals

    # Fallback to alternative format
    visuals = re.findall(r'\*\*\((?:.*?Visual:\s*)(.+?)\)\*\*', content)
    return visuals


def _rate_limit():
    """Ensure minimum delay between API calls."""
    global _last_api_call
    elapsed = time.time() - _last_api_call
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)
    _last_api_call = time.time()


def generate_image(prompt, output_path, channel=None, model=None,
                   api_key=None, retries=3, delay_on_429=None):
    """Generate a single B-roll image via Gemini API.

    Args:
        prompt: Visual description
        output_path: Where to save the PNG
        channel: Channel name for style template lookup
        model: Gemini model ID (default: gemini-2.5-flash-image)
        api_key: API key override
        retries: Max retry attempts
        delay_on_429: Base seconds for rate limit backoff (default: BACKOFF_429)

    Returns:
        float: Image size in KB, or 0 on failure
    """
    key = api_key or GEMINI_API_KEY
    mdl = model or DEFAULT_MODEL
    backoff = delay_on_429 or BACKOFF_429

    template = get_broll_template(channel) if channel else DEFAULT_TEMPLATE
    enhanced = f"{template['prefix']} {prompt}. {template['suffix']}"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": enhanced}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.8}
    }).encode()

    for attempt in range(retries):
        _rate_limit()
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        img_data = base64.b64decode(part["inlineData"]["data"])
                        with open(output_path, "wb") as f:
                            f.write(img_data)
                        return len(img_data) / 1024
            return 0
        except HTTPError as e:
            if e.code == 429:
                wait = backoff * (attempt + 1)
                print(f"      Rate limited (attempt {attempt+1}/{retries}), waiting {wait}s...")
                time.sleep(wait)
            else:
                err = e.read().decode() if hasattr(e, 'read') else str(e)
                print(f"      Error {e.code}: {err[:150]}")
                if attempt < retries - 1:
                    time.sleep(5)
                else:
                    return 0
        except Exception as e:
            print(f"      Error: {str(e)[:150]}")
            return 0
    return 0


def generate_broll(script_path, channel=None, model=None, api_key=None,
                   retries=3, delay_between=None, delay_on_429=None,
                   on_progress=None):
    """Generate all B-roll images for a script.

    Args:
        script_path: Path to script .txt file
        channel: Channel name (auto-detected from filename if None)
        model: Gemini model override
        api_key: API key override
        retries: Max retries per image
        delay_between: Seconds between images (default: MIN_DELAY)
        delay_on_429: Base backoff for 429 errors
        on_progress: Callback(i, total, visual, success) for progress tracking

    Returns:
        tuple: (broll_dir, generated_count, failed_count)
    """
    basename = os.path.splitext(os.path.basename(script_path))[0]
    if channel is None:
        channel = basename.split("_")[0]

    broll_out = os.path.join(BROLL_DIR, basename)
    os.makedirs(broll_out, exist_ok=True)

    visuals = extract_visuals(script_path)
    if not visuals:
        print(f"    No visual directions found")
        return broll_out, 0, 0

    generated = 0
    failed = 0

    for i, visual in enumerate(visuals, 1):
        filepath = os.path.join(broll_out, f"broll_{i:02d}.png")
        if os.path.exists(filepath):
            generated += 1
            if on_progress:
                on_progress(i, len(visuals), visual, True)
            continue

        print(f"    [{i}/{len(visuals)}] {visual[:55]}...")
        size_kb = generate_image(
            visual, filepath,
            channel=channel, model=model, api_key=api_key,
            retries=retries, delay_on_429=delay_on_429
        )
        if size_kb:
            print(f"      -> broll_{i:02d}.png ({size_kb:.0f} KB)")
            generated += 1
        else:
            print(f"      -> FAILED")
            failed += 1

        if on_progress:
            on_progress(i, len(visuals), visual, bool(size_kb))

    return broll_out, generated, failed


def generate_broll_parallel(script_path, channel=None, model=None, api_key=None,
                            retries=3, max_workers=3, on_progress=None):
    """Generate B-roll images in parallel using ThreadPoolExecutor.

    Faster than sequential generation but uses more API quota concurrently.
    Best for batch/overnight runs where speed matters.

    Args:
        script_path: Path to script .txt file
        channel: Channel name (auto-detected from filename if None)
        model: Gemini model override
        api_key: API key override
        retries: Max retries per image
        max_workers: Number of parallel threads (default 3)
        on_progress: Callback(i, total, visual, success)

    Returns:
        tuple: (broll_dir, generated_count, failed_count)
    """
    basename = os.path.splitext(os.path.basename(script_path))[0]
    if channel is None:
        channel = basename.split("_")[0]

    broll_out = os.path.join(BROLL_DIR, basename)
    os.makedirs(broll_out, exist_ok=True)

    visuals = extract_visuals(script_path)
    if not visuals:
        print(f"    No visual directions found")
        return broll_out, 0, 0

    # Filter to only visuals that need generation
    tasks = []
    already_generated = 0
    for i, visual in enumerate(visuals, 1):
        filepath = os.path.join(broll_out, f"broll_{i:02d}.png")
        if os.path.exists(filepath):
            already_generated += 1
        else:
            tasks.append((i, visual, filepath))

    if not tasks:
        print(f"    All {len(visuals)} B-roll images already exist")
        return broll_out, already_generated, 0

    print(f"    Generating {len(tasks)} images in parallel (workers={max_workers})...")

    generated = already_generated
    failed = 0

    def _gen(idx, visual, filepath):
        return idx, visual, generate_image(
            visual, filepath,
            channel=channel, model=model, api_key=api_key,
            retries=retries
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_gen, idx, visual, filepath): (idx, visual)
            for idx, visual, filepath in tasks
        }
        for future in as_completed(futures):
            idx, visual = futures[future]
            try:
                _, _, size_kb = future.result()
                if size_kb:
                    print(f"      [{idx}/{len(visuals)}] broll_{idx:02d}.png ({size_kb:.0f} KB)")
                    generated += 1
                else:
                    print(f"      [{idx}/{len(visuals)}] FAILED: {visual[:40]}...")
                    failed += 1
            except Exception as e:
                print(f"      [{idx}/{len(visuals)}] ERROR: {str(e)[:80]}")
                failed += 1

            if on_progress:
                on_progress(idx, len(visuals), visual, bool(size_kb))

    return broll_out, generated, failed
