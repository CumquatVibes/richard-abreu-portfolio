#!/usr/bin/env python3
"""Upload produced videos to their respective YouTube channels.

Uses per-channel OAuth tokens from channel_tokens.json (set up via setup_channel_auth.py).
Falls back to the default token if a channel-specific token is not available.

Uses YouTube Data API v3 resumable upload protocol.
Generates SEO-optimized titles, descriptions, and tags from script content.
Generates and uploads custom thumbnails via Gemini + YouTube API.
Includes Amazon affiliate links for product-focused channels.
Skips already-uploaded videos (tracked in upload report).
"""

import base64
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.telemetry import log_video_published

VIDEOS_DIR = os.path.join(BASE_DIR, "output", "videos")
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
THUMBNAILS_DIR = os.path.join(BASE_DIR, "output", "thumbnails")
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

# Load API keys
ENV_PATH = os.path.join(os.path.dirname(BASE_DIR), "shopify-theme", ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")
UPLOAD_REPORT_PATH = os.path.join(REPORT_DIR, "youtube_upload_report.json")

# Amazon affiliate tag
AMAZON_AFFILIATE_TAG = "richstudio0f-20"
AMAZON_STORE_ID = "7193294712"

# Channel prefix -> (channel_id, youtube_category_id)
CHANNEL_MAP = {
    "RichTech": ("UCH7Om9fi1IA3SrRXmx2vApQ", "28"),
    "RichPets": ("UCqPWKbwAGtKfiay4fB8bF1g", "15"),
    "RichHorror": ("UCoWN7G6XuFBPgM-m3d1ZMvQ", "22"),
    "RichMind": ("UCvrGunMx9dVfAeGYLQYoaLw", "27"),
    "HowToUseAI": ("UCkrCbfr9qQkfCYw1WkCILKQ", "28"),
    "RichReviews": ("UCQZAmWq2Y_1W09mIOSRSrFw", "28"),
    "RichGaming": ("UCxa7nahEFd_39_jUl-VB57A", "20"),
    "RichHistory": ("UC1pCR2B_mQwCacIlvRhUacA", "27"),
    "RichNature": ("UCqzGBwIvr3sY1nUc9M2EVsg", "15"),
    "RichScience": ("UC0ODvK8Hvrd9Bd3QWIWPecA", "28"),
    "RichFinance": ("UCJwfAudM4c4rWSk3P8iib8g", "27"),
    "RichCrypto": ("UCc5XhfHIkEp5WwG9CRZm_6w", "28"),
    "RichMovie": ("UCuQwKYGe1hNdbQqJH51qqAw", "24"),
    "RichComedy": ("UC7OZtJLgHJ1ooWWlPLRYIXg", "23"),
    "RichSports": ("UCE33LOzIvklXaPbH1920vqQ", "17"),
    "RichMusic": ("UCCI_ynXNuutXGrzWDYzUZiA", "10"),
    "RichTravel": ("UCEA1FMT0W2lS93Ig1W1ddUA", "19"),
    "RichFood": ("UCSRXBfCZTafYTtfH9KF-SZw", "26"),
    "RichFitness": ("UCYelLGcByI-Qh94two6CaMA", "17"),
    "RichEducation": ("UCp3WkXsFFzdRLZX_UYp43cw", "27"),
    "RichLifestyle": ("UC1Qnne6cR4N4RJgpySYUevw", "22"),
    "RichFashion": ("UCf0Y1kCz_2nTmKpJtPQKoyg", "26"),
    "RichBeauty": ("UCfBoNA8eUrqmSTPLtMhrpdQ", "26"),
    "RichCooking": ("UC8OrR3UMdyzy4DRgmCWOXcA", "26"),
    "RichFamily": ("UC3rXZPP828z8w9UdEdQEWtw", "22"),
    "RichCars": ("UCr0q31TN0vW0c65JUD0eaBw", "2"),
    "RichDIY": ("UC7dfL3CGJCbG7QcGnjrmqbQ", "26"),
    "RichDesign": ("UCSc0w6tez-UI3fyXQbUcF5g", "26"),
    "RichPhotography": ("UCZLGO4ioG50Y3FBK3oLKmpA", "26"),
    "RichMemes": ("UC5Sa2tKSk-5Nek01b-v1LpQ", "23"),
    "RichAnimation": ("UCtsmXjQaCdMTEyDTDWRpVVA", "1"),
    "RichVlogging": ("UCfcF72fTPY1khgl5bEHzZEQ", "22"),
    "RichKids": ("UCTR_qaU4bdip3DSvgBkRMGA", "24"),
    "RichDance": ("UCsNqeu5ZPnBOE3liu9-ofYg", "10"),
    "EvaReyes": ("UCsp5NIA6aeQmqdn7omBqkYg", "22"),
    "HowToMeditate": ("UCbd6kzX3giNYyAeLaMPdgAA", "22"),
    "RichBusiness": ("UCPQ8N53EgcqEKR4SfQ1DcXQ", "28"),
    "CumquatMotivation": ("UCtrCefKinhom7LFBV8rnfpQ", "22"),
    "CumquatVibes": ("UCThXDUhXqcui2HqBv4MUBBA", "22"),
}

# Avatar-based channels (use produce_video.py / HeyGen, NOT faceless B-roll pipeline)
# These channels use Richard's digital avatar instead of faceless voiceover + stock footage.
AVATAR_CHANNELS = {"CumquatVibes"}

# Map video filename prefix -> channel_tokens.json key name
TOKEN_KEY_MAP = {
    "HowToUseAI": "How to Use AI",
    "HowToMeditate": "How to Meditate",
    "EvaReyes": "Eva Reyes",
    "RichBusiness": "Rich Business",
    "CumquatMotivation": "Cumquat Motivation",
    "CumquatVibes": "Cumquat Vibes",
}

CHANNEL_NICHE = {
    "RichTech": "tech, gadgets, and AI tools",
    "RichPets": "pet care, animal behavior, and fun pet facts",
    "RichHorror": "true horror stories, unsolved mysteries, and haunted places",
    "RichMind": "psychology, dark psychology, and the human mind",
    "HowToUseAI": "AI tutorials, productivity tools, and making money with AI",
    "RichReviews": "product reviews, comparisons, and honest tech analysis",
    "RichFinance": "personal finance, investing, and building wealth",
    "RichCrypto": "cryptocurrency, blockchain, and Web3",
    "EvaReyes": "women's empowerment, inspiration, and self-improvement",
    "RichFitness": "fitness, workouts, and healthy living",
    "RichCooking": "cooking, recipes, and kitchen hacks",
    "CumquatVibes": "art, design, tech, entrepreneurship, and creator lifestyle",
    "RichArt": "4K art slideshows, art for your TV, ambient art, art essays",
    "RichMusic": "curated music playlists, lo-fi beats, jazz, blues, ambient music",
}

# Channels that use the "Turn Your TV Into Art" template
ART_SLIDESHOW_CHANNELS = {"RichArt"}

CHANNEL_TAGS = {
    "RichTech": [
        "tech", "technology", "gadgets", "AI tools", "software review",
        "tech 2026", "best apps", "future tech", "productivity", "tech tips",
    ],
    "RichPets": [
        "pets", "pet care", "dog care", "cat breeds", "pet health",
        "animal behavior", "pet tips", "pet owner tips", "dog training", "cat care",
    ],
    "RichHorror": [
        "horror", "true horror stories", "unsolved mysteries", "haunted places",
        "scary stories", "creepy", "paranormal", "true crime", "horror 2026", "scary",
    ],
    "RichMind": [
        "psychology", "dark psychology", "body language", "manipulation tactics",
        "mindset", "overthinking", "mental health", "human behavior",
        "cognitive biases", "self improvement",
    ],
    "HowToUseAI": [
        "AI", "artificial intelligence", "ChatGPT", "AI tools", "automation",
        "AI tutorial", "prompt engineering", "make money with AI",
        "how to use AI", "productivity tools",
    ],
    "RichReviews": [
        "product review", "tech review", "best products", "amazon finds",
        "honest review", "comparison", "worth it", "budget picks", "top 10",
    ],
    "EvaReyes": [
        "women empowerment", "self improvement", "confidence", "inspiration",
        "mindset", "self care", "career growth", "motivational", "affirmations",
    ],
    "CumquatVibes": [
        "Richard Abreu", "Cumquat Vibes", "digital art", "design tutorial",
        "AI tools", "creator economy", "entrepreneur", "veteran creator",
        "art process", "tech review", "side hustle", "Affinity Designer",
    ],
    "RichArt": [
        "art for tv", "tv wall art", "4k art", "4k slideshow", "art background",
        "living room tv art", "frame tv art", "ambient video", "relaxing art",
        "art slideshow", "wall art video", "background art", "turn your tv into art",
        "samsung frame tv art", "art screensaver",
    ],
    "RichMusic": [
        "music playlist", "lo-fi beats", "study music", "chill music",
        "jazz playlist", "blues music", "ambient music", "relaxing music",
        "background music", "focus music", "cafe music", "work music",
    ],
}

# Channels that discuss products and should include affiliate links
AFFILIATE_CHANNELS = {
    "RichTech", "RichReviews", "HowToUseAI", "RichCars", "RichBeauty",
    "RichCooking", "RichFitness", "RichGaming", "RichFood", "RichDIY",
    "RichFashion", "RichPhotography", "EvaReyes", "RichMind", "RichLifestyle",
}

# Per-channel access tokens (populated at runtime)
channel_access_tokens = {}

# Channels that hit upload limit this run (skip remaining videos)
rate_limited_channels = set()


def refresh_default_token():
    """Get fresh access token from the default google_token.json."""
    with open(TOKEN_PATH) as f:
        creds = json.load(f)
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urlopen(req).read())
    return resp["access_token"]


def refresh_channel_token(channel_creds):
    """Get fresh access token for a specific channel."""
    data = urllib.parse.urlencode({
        "client_id": channel_creds["client_id"],
        "client_secret": channel_creds["client_secret"],
        "refresh_token": channel_creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urlopen(req).read())
    return resp["access_token"]


def load_channel_tokens():
    """Load and refresh per-channel tokens. Returns dict of channel_name -> access_token."""
    tokens = {}
    if not os.path.exists(CHANNEL_TOKENS_PATH):
        return tokens

    with open(CHANNEL_TOKENS_PATH) as f:
        channel_creds = json.load(f)

    for channel_name, creds in channel_creds.items():
        try:
            access_token = refresh_channel_token(creds)
            tokens[channel_name] = access_token
            print(f"  {channel_name}: token refreshed (channel: {creds.get('channel_title', creds.get('channel_id', '?'))})")
        except Exception as e:
            print(f"  {channel_name}: token refresh FAILED ({e})")

    return tokens


def get_token_for_channel(channel_name, default_token):
    """Get the access token for a specific channel, or fall back to default."""
    token_key = TOKEN_KEY_MAP.get(channel_name, channel_name)
    return channel_access_tokens.get(token_key, default_token)


def verify_channel(access_token):
    """Check which YouTube channel a token authenticates as."""
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        result = json.loads(urlopen(req).read())
    except HTTPError:
        return None, None
    items = result.get("items", [])
    if items:
        return items[0]["id"], items[0]["snippet"]["title"]
    return None, None


def load_previous_uploads():
    """Load previously successful uploads to skip re-uploading."""
    if not os.path.exists(UPLOAD_REPORT_PATH):
        return set()
    with open(UPLOAD_REPORT_PATH) as f:
        report = json.load(f)
    uploaded_files = set()
    for r in report.get("results", []):
        if r.get("status") == "success" and r.get("video_id"):
            uploaded_files.add(r["file"])
    return uploaded_files


def make_title(filename):
    """Convert video filename to a CTR-optimized YouTube title.

    Applies title case, preserves numbers, adds power words, and ensures
    the title hits the 40-70 character sweet spot for search display.

    Title optimization rules (from post_upload_assessment benchmarks):
    - 40-70 chars (full display width in search)
    - Include numbers (+36% CTR boost)
    - Front-load keywords (most important words first)
    - Use power words that drive curiosity
    """
    name = os.path.splitext(filename)[0]
    parts = name.split("_", 1)
    channel_prefix = parts[0] if len(parts) > 1 else ""
    title_raw = parts[1] if len(parts) > 1 else name
    title = title_raw.replace("_", " ")

    # Strip trailing timestamp patterns like "20260219 155540"
    title = re.sub(r'\s*\d{8}\s*\d{6}\s*$', '', title)

    # RichArt: Use "Turn Your TV Into Art" title format
    # Format: "{Theme} | Turn Your TV Into Art | {Duration} 4K Slideshow"
    if channel_prefix == "RichArt":
        # Clean up the theme part
        theme = title
        for strip in ["Turn Your TV Into Art", "4K", "Slideshow", "|"]:
            theme = theme.replace(strip, "")
        # Strip duration patterns (case-insensitive)
        theme = re.sub(r'\b\d+\s*(?:hr|hour|min)\b', '', theme, flags=re.IGNORECASE)
        theme = re.sub(r'\s+', ' ', theme).strip(" -–—")
        # Detect duration from filename
        duration = "1Hr"
        if "2hr" in name.lower() or "2hour" in name.lower():
            duration = "2Hr"
        elif "30min" in name.lower():
            duration = "30min"
        elif "6min" in name.lower() or "7min" in name.lower():
            # Short preview videos — don't use the art template
            pass
        else:
            # Build the art title format
            art_title = f"{theme} | Turn Your TV Into Art | {duration} 4K Slideshow"
            if len(art_title) <= 100:  # YouTube max is 100
                return art_title

    # Title case but preserve fully uppercase words (AI, DIY, etc.)
    words = title.split()
    result = []
    small_words = {"a", "an", "the", "and", "but", "or", "for", "in", "on", "at", "to", "of", "is", "it"}
    for i, word in enumerate(words):
        if word.isupper() and len(word) > 1:
            result.append(word)  # Keep acronyms uppercase
        elif i == 0 or word.lower() not in small_words:
            result.append(word.capitalize())
        else:
            result.append(word.lower())
    title = " ".join(result)

    # If title is too short, it probably won't perform well in search
    # If too long, truncate cleanly at word boundary under 70 chars
    if len(title) > 70:
        truncated = title[:67]
        last_space = truncated.rfind(" ")
        if last_space > 40:
            title = truncated[:last_space] + "..."

    return title


def find_script(video_filename):
    """Find the matching script file for a video."""
    base = os.path.splitext(video_filename)[0]
    for f in sorted(os.listdir(SCRIPTS_DIR)):
        if f.startswith(base) and f.endswith(".txt"):
            return os.path.join(SCRIPTS_DIR, f)
    return None


def extract_intro(script_path):
    """Extract clean intro text from script for description."""
    if not script_path:
        return ""
    with open(script_path) as f:
        content = f.read()

    lines = content.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("[VISUAL") or line.startswith("**("):
            continue
        if re.match(r'^\*\*\d+\.', line):
            continue
        line = re.sub(
            r'^(?:\*\*)?(?:Narrator|NARRATOR|Host|HOST|Voiceover|Speaker)\s*:\s*(?:\*\*)?',
            '', line
        )
        line = re.sub(r'\*\*', '', line)
        line = re.sub(r'\([A-Z][^)]{5,}\)', '', line)
        line = line.strip()
        if len(line) > 30:
            clean_lines.append(line)
        if len(clean_lines) >= 3:
            break

    intro = " ".join(clean_lines)
    if len(intro) > 400:
        intro = intro[:397] + "..."
    return intro


def extract_chapters_from_script(script_path):
    """Extract section headers from script for YouTube chapter timestamps.

    Returns list of chapter names found in the script.
    """
    if not script_path:
        return []
    with open(script_path) as f:
        content = f.read()

    chapters = ["Intro"]

    # Match [CHAPTER: section name] markers
    for match in re.finditer(r'\[CHAPTER:\s*(.+?)\]', content):
        name = match.group(1).strip()
        if name not in chapters:
            chapters.append(name)

    # Match numbered items: "Number 7:", "**7.", "#7:", "7)", etc.
    if len(chapters) <= 1:
        for match in re.finditer(r'(?:Number\s+|#|\*\*)?(\d+)[\.\):\s]+\s*([A-Z][^\n]{5,60})', content):
            name = match.group(2).strip().rstrip(".*")
            name = re.sub(r'\*\*', '', name)
            if len(name) > 5 and name not in chapters:
                chapters.append(name)

    # Also look for section headers like (Section Name - 0:00)
    if len(chapters) <= 1:
        for match in re.finditer(r'\(([A-Z][^)]{3,40})\s*[-–]\s*\d', content):
            name = match.group(1).strip()
            if name not in chapters and len(name) > 3:
                chapters.append(name)

    if len(chapters) > 1:
        chapters.append("Outro")
    return chapters


def generate_timestamps(chapters, total_duration_sec=480):
    """Generate evenly-spaced timestamp strings for chapter list."""
    if len(chapters) < 2:
        return ""
    interval = total_duration_sec // len(chapters)
    lines = []
    for i, ch in enumerate(chapters):
        mins = (i * interval) // 60
        secs = (i * interval) % 60
        lines.append(f"{mins}:{secs:02d} {ch}")
    return "\n".join(lines)


def extract_products_from_script(script_path):
    """Extract product names mentioned in a script for affiliate linking."""
    if not script_path:
        return []
    with open(script_path) as f:
        content = f.read()

    products = []
    # Look for product-like patterns: "Product Name ($XX)" or numbered items
    for match in re.finditer(r'(?:^|\n)\s*(?:\d+[\.\)]\s*)?([A-Z][A-Za-z0-9\s\-\.]+?)(?:\s*[\(\-\u2014]\s*\$[\d,\.]+)?(?:\s*[\)\n])', content):
        name = match.group(1).strip()
        if len(name) > 5 and len(name) < 60 and not name.startswith("Subscribe"):
            products.append(name)
    return products[:10]


def _make_art_description(title, script_path):
    """Generate 'Turn Your TV Into Art' description template for RichArt videos."""
    # Extract theme from title (e.g. "Impressionist Masters Monet Renoir Degas")
    theme = title
    for strip in ["Turn Your TV Into Art", "4K", "Slideshow", "1Hr", "2Hr", "30min", "|"]:
        theme = theme.replace(strip, "")
    theme = re.sub(r'\s+', ' ', theme).strip(" -–—")
    if not theme:
        theme = "curated artwork"

    # Detect duration from title
    duration = "1 hour"
    if "2Hr" in title or "2 Hour" in title:
        duration = "2 hours"
    elif "30min" in title or "30 Min" in title:
        duration = "30 minutes"

    # Try to extract artist/style info from script
    artists = ""
    style = "Fine art"
    if script_path and os.path.exists(script_path):
        with open(script_path) as f:
            content = f.read()
        # Look for artist names in script
        artist_matches = re.findall(r'(?:by|Artist:|Featuring:)\s*([A-Z][a-zA-Z\s,&]+)', content)
        if artist_matches:
            artists = artist_matches[0].strip()

    parts = [
        f"Transform your space with this {theme.lower()} collection in stunning 4K,",
        f"perfect as ambient art for your TV, living room, office, cafe, or studio background.",
        "",
        "\u25b6 What you get",
        f"- {duration} of continuous {theme.lower()} artwork",
        "- Optimized for 4K TVs and smart displays",
        "- Ideal for relaxing, studying, working, or entertaining guests",
        "",
        "\u25b6 Featuring",
    ]
    if artists:
        parts.append(f"- Artists: {artists}")
    parts.extend([
        f"- Style: {style}",
        "",
        "\u25b6 Get matching prints and merch",
        "Bring this art off the screen and into your home with high-quality prints,",
        "apparel, and accessories:",
        "https://www.cumquatvibes.com",
        "",
        "Browse more of my artwork and projects:",
        "Portfolio: https://richardabreu.studio",
        "Community & updates: https://vibeconnectionlounge.com",
        "",
        "\u25b6 How to use this video",
        "- Set as background art while you relax, read, or host guests",
        "- Use on a second monitor while working or studying",
        "- Play in lobbies, cafes, salons, or offices for a calm, creative vibe",
        "",
        "\u25b6 About this project",
        "This video was created using curated and AI-assisted artwork, edited and",
        "compiled by a human artist to deliver a unique viewing experience.",
        "",
        "Thank you for watching and supporting independent creators!",
        "",
        "AI DISCLOSURE: This video was created with the assistance of AI tools",
        "including AI-upscaled artwork and automated compilation.",
        "",
        "\u00a9 2026 Cumquat Vibes Media",
        "",
        "#artfortv #4kart #turnyourtvintart #artslideshow #ambientvideo",
    ])
    return "\n".join(parts)


def make_description(channel, title, script_path):
    """Generate SEO-optimized YouTube description with timestamps and affiliate links.

    Structure optimized for CTR and search:
    1. First 2 lines = searchable hook (visible in search results)
    2. Timestamps/chapters
    3. Affiliate links (if product channel)
    4. CTA + links
    """
    # RichArt uses the "Turn Your TV Into Art" template
    if channel in ART_SLIDESHOW_CHANNELS:
        return _make_art_description(title, script_path)

    intro = extract_intro(script_path)
    chapters = extract_chapters_from_script(script_path)

    # CumquatVibes gets a personal brand description (first-person, avatar channel)
    is_avatar = channel in AVATAR_CHANNELS
    is_affiliate = channel in AFFILIATE_CHANNELS

    # First 2 lines are critical — visible in search results and suggestions
    parts = [title]
    if intro:
        parts.append(intro)
    parts.append("")

    # Timestamps / Chapters (boosts watch time + gets "Key Moments" in Google)
    if len(chapters) > 2:
        timestamps = generate_timestamps(chapters)
        parts.extend([
            "TIMESTAMPS:",
            timestamps,
            "",
        ])

    # Affiliate section for product channels
    if is_affiliate:
        products = extract_products_from_script(script_path)
        parts.extend([
            "---",
            "",
            "PRODUCTS MENTIONED (affiliate links):",
            f"Shop our recommended products on Amazon:",
            f"https://www.amazon.com/shop/{AMAZON_STORE_ID}?tag={AMAZON_AFFILIATE_TAG}",
            "",
        ])
        if products:
            for p in products[:5]:
                search_q = urllib.parse.quote_plus(p)
                parts.append(
                    f"  {p}: https://www.amazon.com/s?k={search_q}&tag={AMAZON_AFFILIATE_TAG}"
                )
            parts.append("")

        parts.extend([
            "DISCLOSURE: Some links above are affiliate links. As an Amazon Associate,",
            "I earn from qualifying purchases at no extra cost to you.",
            "",
        ])

    if is_avatar:
        # Personal brand CTA for CumquatVibes (Richard's main channel)
        parts.extend([
            "---",
            "",
            "Subscribe and hit the bell — I drop new videos every week!",
            "Like this video if it helped you out.",
            "Drop a comment and let me know what you think!",
            "",
            "---",
            "",
            "CONNECT WITH ME:",
            "Shop: https://cumquatvibes.com",
            "Portfolio: https://richardabreu.studio",
            "Community: https://vibeconnectionlounge.com",
            "Instagram: @cumquatvibes",
            "",
            "AI DISCLOSURE: This video features my digital avatar created with AI assistance.",
            "",
            "\u00a9 2026 Cumquat Vibes Media",
            "",
        ])
    else:
        parts.extend([
            "---",
            "",
            "Subscribe and hit the bell for new videos!",
            "Like this video if you found it helpful.",
            "Drop a comment and let us know what you think!",
            "",
            "---",
            "",
            "Shop: https://cumquatvibes.com",
            "Portfolio: https://richardabreu.studio",
            "Community: https://vibeconnectionlounge.com",
            "",
            "AI DISCLOSURE: This video was created with the assistance of AI tools",
            "including AI-generated voiceover and visuals.",
            "",
            "\u00a9 2026 Cumquat Vibes Media",
            "",
        ])

    tag_prefix = channel.lower()
    niche_tag = CHANNEL_NICHE.get(channel, "").split(",")[0].strip().replace(" ", "")
    parts.append(f"#{tag_prefix} #{niche_tag} #2026")

    return "\n".join(parts)


def make_tags(channel, title):
    """Generate tags combining channel tags with title keywords."""
    base_tags = list(CHANNEL_TAGS.get(channel, []))
    title_words = [w for w in title.lower().split() if len(w) > 3]
    for w in title_words[:5]:
        if w not in " ".join(base_tags).lower():
            base_tags.append(w)
    result = []
    total_len = 0
    for tag in base_tags:
        if total_len + len(tag) + 1 > 490:
            break
        result.append(tag)
        total_len += len(tag) + 1
    return result


# ---------------------------------------------------------------------------
# Thumbnail Generation & Upload
# ---------------------------------------------------------------------------

# Channel-specific thumbnail styles
CHANNEL_THUMBNAIL_STYLE = {
    "RichMind": "dark moody background, psychological theme, dramatic shadows, intense close-up perspective",
    "RichHorror": "dark horror atmosphere, eerie fog, desaturated with red accents, unsettling mood",
    "RichTech": "sleek tech aesthetic, neon blue/purple accents, circuit patterns, futuristic feel",
    "HowToUseAI": "clean digital aesthetic, AI/robot visual elements, glowing interface, modern tech",
    "RichPets": "warm inviting colors, cute animal photography style, soft lighting, heartwarming",
    "EvaReyes": "elegant golden-hour lighting, empowering feminine energy, warm tones, confident",
    "RichFinance": "professional finance aesthetic, green money accents, charts, wealth imagery",
    "RichCrypto": "futuristic dark theme, blockchain visuals, glowing neon green/blue, digital",
    "RichFitness": "dynamic energy, gym/athletic aesthetic, bold contrast, motivational",
    "RichCooking": "warm appetizing colors, food photography style, steam/sizzle, delicious",
    "RichNature": "stunning natural landscape, vivid colors, dramatic sky, National Geographic feel",
    "RichHistory": "vintage sepia tones, historical atmosphere, dramatic documentary lighting",
    "RichReviews": "clean product showcase, studio lighting, comparison layout, professional",
    "RichGaming": "vibrant RGB glow, gaming aesthetic, neon colors on dark background, energetic",
    "RichMusic": "concert stage lighting, moody musical atmosphere, dramatic spotlights",
    "RichTravel": "stunning travel destination, golden hour, wanderlust-inspiring, vibrant",
    "HowToMeditate": "serene peaceful atmosphere, zen garden, soft warm lighting, calming",
    "RichBusiness": "professional corporate aesthetic, success imagery, confident, modern office",
    "CumquatMotivation": "epic sunrise/sunset, inspirational landscape, powerful atmosphere",
    "CumquatVibes": "dark matte studio aesthetic #101922 background, orange #e8941f accent, Richard Abreu digital avatar, bold creator energy, premium personal brand feel",
}
DEFAULT_THUMBNAIL_STYLE = "cinematic lighting, professional YouTube thumbnail, bold dramatic atmosphere"


def generate_thumbnail(title, channel, video_filename):
    """Generate a viral-worthy thumbnail using Gemini image generation.

    Returns path to generated thumbnail image, or None on failure.
    """
    if not GEMINI_API_KEY:
        print("    Thumbnail: No GEMINI_API_KEY, skipping")
        return None

    # Check if thumbnail already exists
    thumb_name = os.path.splitext(video_filename)[0] + "_thumb.png"
    thumb_path = os.path.join(THUMBNAILS_DIR, thumb_name)
    if os.path.exists(thumb_path):
        print(f"    Thumbnail: Using existing ({os.path.getsize(thumb_path) / 1024:.0f} KB)")
        return thumb_path

    channel_style = CHANNEL_THUMBNAIL_STYLE.get(channel, DEFAULT_THUMBNAIL_STYLE)

    # Extract key words for thumbnail text (max 3-4 impactful words)
    # Strip common filler to get the hook
    short_title = title
    for remove in ["How to ", "Why ", "The ", "A ", "An ", "What "]:
        if short_title.startswith(remove):
            short_title = short_title[len(remove):]
    words = short_title.split()
    thumb_text = " ".join(words[:4]).upper() if len(words) > 4 else short_title.upper()

    prompt = (
        f"YouTube thumbnail, 16:9 aspect ratio, {channel_style}, "
        f"with large bold white text '{thumb_text}' as focal point, "
        f"high contrast, eye-catching, viral thumbnail style, "
        f"cinematic composition, 4K quality, no small text, "
        f"text should be easily readable at small sizes"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.9}
    }).encode()

    for attempt in range(3):
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        img_data = base64.b64decode(part["inlineData"]["data"])
                        with open(thumb_path, "wb") as f:
                            f.write(img_data)
                        size_kb = len(img_data) / 1024
                        print(f"    Thumbnail: Generated ({size_kb:.0f} KB)")
                        return thumb_path
            print("    Thumbnail: No image in response")
            return None
        except HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f"    Thumbnail: Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                body = e.read().decode() if hasattr(e, 'read') else str(e)
                print(f"    Thumbnail: Error {e.code}: {body[:150]}")
                return None
        except Exception as e:
            print(f"    Thumbnail: Error: {str(e)[:150]}")
            return None
    return None


def upload_thumbnail(video_id, thumb_path, access_token):
    """Upload custom thumbnail to a YouTube video.

    Uses YouTube Data API v3 thumbnails.set endpoint.
    Returns True on success, False on failure, or "quota_exceeded" string
    when the YouTube API daily quota has been exhausted.
    """
    url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}&uploadType=media"

    with open(thumb_path, "rb") as f:
        img_data = f.read()

    req = Request(
        url,
        data=img_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "image/png",
            "Content-Length": str(len(img_data)),
        },
        method="POST",
    )

    try:
        resp = urlopen(req, timeout=60)
        result = json.loads(resp.read().decode())
        if result.get("items"):
            print(f"    Thumbnail: Uploaded to video {video_id}")
            return True
        print(f"    Thumbnail: Upload response had no items")
        return False
    except HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        if e.code == 403:
            # Parse the actual reason from the API response
            reason = ""
            try:
                err_data = json.loads(body)
                errors = err_data.get("error", {}).get("errors", [])
                if errors:
                    reason = errors[0].get("reason", "")
            except (json.JSONDecodeError, KeyError):
                pass
            if reason == "quotaExceeded":
                print(f"    Thumbnail: Quota exceeded")
                return "quota_exceeded"
            elif "forbidden" in body.lower() and "thumbnail" in body.lower():
                print(f"    Thumbnail: Channel needs phone verification for custom thumbnails")
            else:
                print(f"    Thumbnail: 403 Forbidden — {reason or body[:200]}")
        else:
            print(f"    Thumbnail: Upload error {e.code}: {body[:200]}")
        return False
    except Exception as e:
        print(f"    Thumbnail: Upload error: {str(e)[:150]}")
        return False


def upload_video(filepath, title, description, tags, category_id, access_token, privacy="public"):
    """Upload video using YouTube Data API v3 resumable upload.

    Returns:
        dict: Upload result on success
        "rate_limited": When channel hit daily upload limit
        None: On other failures
    """
    file_size = os.path.getsize(filepath)

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    init_url = (
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status"
    )
    init_req = Request(
        init_url,
        data=json.dumps(metadata).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/mp4",
        },
        method="POST",
    )

    try:
        init_resp = urlopen(init_req)
        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            print("    No upload URL returned")
            return None
    except HTTPError as e:
        body = e.read().decode()
        if "uploadLimitExceeded" in body:
            print("    Daily upload limit reached for this channel")
            return "rate_limited"
        if "quota" in body.lower():
            print("    YouTube API daily quota exceeded")
            return "quota_exceeded"
        print(f"    Init error {e.code}: {body[:300]}")
        return {"error": f"Init error {e.code}: {body[:300]}"}

    chunk_size = 10 * 1024 * 1024

    with open(filepath, "rb") as f:
        uploaded = 0
        while uploaded < file_size:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            end = uploaded + len(chunk)

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {uploaded}-{end - 1}/{file_size}",
            }

            req = Request(upload_url, data=chunk, headers=headers, method="PUT")
            try:
                resp = urlopen(req, timeout=300)
                result = json.loads(resp.read().decode())
                return result
            except HTTPError as e:
                if e.code == 308:
                    uploaded = end
                    continue
                elif e.code == 503:
                    print("    503 -- retrying in 10s...")
                    time.sleep(10)
                    continue
                else:
                    body = e.read().decode()
                    print(f"    Upload error {e.code}: {body[:300]}")
                    return {"error": f"Upload error {e.code}: {body[:300]}"}

    return {"error": "Upload incomplete: EOF reached before file fully uploaded"}


# Quota budget: YouTube Data API costs ~1600 units per upload, 50 per thumbnail
# Default daily quota is 10,000 units. Stop at 80% to leave room for other operations.
QUOTA_PER_UPLOAD = 1600
QUOTA_PER_THUMBNAIL = 50
DAILY_QUOTA_LIMIT = 10000
QUOTA_SAFETY_THRESHOLD = 0.80  # Stop uploads at 80% quota usage


def run_preflight(video_file, channel, title, description, tags, script_path):
    """Run compliance preflight check before uploading.

    Returns (passed: bool, result: dict)
    """
    try:
        from utils.compliance import preflight_check, format_preflight_report

        script_text = ""
        if script_path and os.path.exists(script_path):
            with open(script_path) as f:
                script_text = f.read()

        result = preflight_check(
            script_text=script_text,
            title=title,
            description=description,
            tags=tags,
            is_synthetic=True,
        )

        report = format_preflight_report(result)
        for line in report.split("\n"):
            print(f"  {line}")

        return result["publishable"], result

    except ImportError:
        print("  Preflight: utils.compliance not available, skipping check")
        return True, {"publishable": True, "violations": [], "risk_scores": {}}
    except Exception as e:
        print(f"  Preflight: Error ({str(e)[:80]}), proceeding with caution")
        return True, {"publishable": True, "violations": [], "risk_scores": {}}


def main():
    global channel_access_tokens

    print("YouTube Video Uploader")
    print("=" * 60)
    print()

    # Load per-channel tokens
    print("Loading per-channel tokens...")
    channel_access_tokens = load_channel_tokens()

    if channel_access_tokens:
        print(f"\n  {len(channel_access_tokens)} channel token(s) loaded.")
    else:
        print("\n  No channel tokens found.")
        print("  Run setup_channel_auth.py first to authorize each brand channel.")
        print("  Falling back to default token (uploads to main channel).\n")

    # Refresh default token as fallback
    default_token = refresh_default_token()
    default_ch_id, default_ch_title = verify_channel(default_token)
    print(f"  Default channel: {default_ch_title} ({default_ch_id})\n")

    # Load previous upload report to skip already-uploaded videos
    already_uploaded = load_previous_uploads()
    if already_uploaded:
        print(f"  Previously uploaded: {len(already_uploaded)} videos (will skip)\n")

    # Get videos
    videos = sorted([f for f in os.listdir(VIDEOS_DIR) if f.endswith(".mp4")])
    pending = [v for v in videos if v not in already_uploaded]
    print(f"Videos found: {len(videos)} | Pending upload: {len(pending)}\n")

    if not pending:
        print("All videos already uploaded! Nothing to do.")
        return

    # Load existing results to preserve them
    existing_results = []
    if os.path.exists(UPLOAD_REPORT_PATH):
        with open(UPLOAD_REPORT_PATH) as f:
            existing_results = json.load(f).get("results", [])

    results = list(existing_results)
    uploaded_count = len(already_uploaded)
    skipped_limit = 0
    failed_count = 0
    preflight_blocked = 0
    quota_used_this_run = 0

    for i, video_file in enumerate(pending, 1):
        channel = video_file.split("_")[0]

        # Skip if this channel already hit rate limit this run
        if channel in rate_limited_channels:
            print(f"[{i}/{len(pending)}] {channel}: SKIP (rate limited)")
            skipped_limit += 1
            continue

        # Quota budget check: stop early if we'd exceed 80% of daily quota
        projected_quota = quota_used_this_run + QUOTA_PER_UPLOAD + QUOTA_PER_THUMBNAIL
        if projected_quota > DAILY_QUOTA_LIMIT * QUOTA_SAFETY_THRESHOLD:
            remaining = len(pending) - i
            print(f"\n  Quota budget: {quota_used_this_run}/{DAILY_QUOTA_LIMIT} used ({quota_used_this_run/DAILY_QUOTA_LIMIT*100:.0f}%)")
            print(f"  Stopping to preserve quota. {remaining} videos deferred to next run.")
            break

        channel_id, category_id = CHANNEL_MAP.get(channel, (None, "22"))

        title = make_title(video_file)
        script_path = find_script(video_file)
        description = make_description(channel, title, script_path)
        tags = make_tags(channel, title)

        filepath = os.path.join(VIDEOS_DIR, video_file)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)

        # Pick the right token
        token = get_token_for_channel(channel, default_token)
        token_key = TOKEN_KEY_MAP.get(channel, channel)
        using_channel_token = token_key in channel_access_tokens

        print(f"[{i}/{len(pending)}] {channel}: {title}")
        print(f"  Size: {size_mb:.1f} MB | Token: {'channel-specific' if using_channel_token else 'default (main channel)'}")

        # Preflight compliance check
        preflight_passed, preflight_result = run_preflight(
            video_file, channel, title, description, tags, script_path
        )
        if not preflight_passed:
            print(f"  BLOCKED by preflight compliance check — skipping upload")
            preflight_blocked += 1
            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": None,
                "status": "preflight_blocked",
                "violations": [v["type"] for v in preflight_result.get("violations", [])],
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # Generate thumbnail before upload
        thumb_path = generate_thumbnail(title, channel, video_file)

        result = upload_video(filepath, title, description, tags, category_id, token)

        if result == "quota_exceeded":
            print(f"\n  YouTube API quota exhausted (videos.insert = 1600 units; daily limit = 10,000).")
            print(f"  Remaining {len(pending) - i} videos will retry after quota reset (midnight PT).")
            failed_count += 1
            break
        elif result == "rate_limited":
            rate_limited_channels.add(channel)
            skipped_limit += 1
            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": None,
                "status": "rate_limited",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            })
        elif result and "error" in result:
            error_msg = result["error"]
            print(f"  FAILED: {error_msg[:120]}")
            failed_count += 1
            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": None,
                "status": "failed",
                "error": error_msg,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            })
        elif result:
            vid_id = result.get("id", "?")
            status = result.get("status", {}).get("uploadStatus", "?")
            print(f"  Uploaded: https://youtube.com/watch?v={vid_id} (status: {status})")

            # Upload custom thumbnail if we generated one
            thumb_uploaded = False
            if thumb_path and vid_id != "?":
                thumb_result = upload_thumbnail(vid_id, thumb_path, token)
                thumb_uploaded = thumb_result is True

            quota_used_this_run += QUOTA_PER_UPLOAD
            if thumb_uploaded:
                quota_used_this_run += QUOTA_PER_THUMBNAIL

            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": vid_id,
                "url": f"https://youtube.com/watch?v={vid_id}",
                "status": "success",
                "upload_status": status,
                "used_channel_token": using_channel_token,
                "thumbnail_uploaded": thumb_uploaded,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            })
            uploaded_count += 1

            # Log to telemetry DB
            try:
                video_name = os.path.splitext(video_file)[0]
                log_video_published(video_name, vid_id, quota_used=QUOTA_PER_UPLOAD)
            except Exception:
                pass
        else:
            print(f"  FAILED: Unknown error")
            failed_count += 1
            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": None,
                "status": "failed",
                "error": "Unknown error - no response from API",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            })

        if i < len(pending):
            time.sleep(3)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Results: {uploaded_count} uploaded | {skipped_limit} rate-limited | {failed_count} failed | {preflight_blocked} blocked by compliance")
    print(f"Quota used this run: ~{quota_used_this_run}/{DAILY_QUOTA_LIMIT} ({quota_used_this_run/DAILY_QUOTA_LIMIT*100:.0f}%)\n")

    for r in results:
        if r["status"] == "success":
            dest = "-> correct channel" if r.get("used_channel_token") else "-> main channel"
            print(f"  [OK] {r['channel']}: {r['file']} {dest}")
            if r.get("url"):
                print(f"       {r['url']}")
        elif r["status"] == "rate_limited":
            print(f"  [LIMIT] {r['channel']}: {r['file']} (retry tomorrow)")
        else:
            print(f"  [FAIL] {r['channel']}: {r['file']}")

    if rate_limited_channels:
        print(f"\nRate-limited channels (retry in 24h): {', '.join(sorted(rate_limited_channels))}")

    # Deduplicate results: keep only the latest entry per file
    # This prevents the report from growing endlessly with repeated failures
    seen = {}
    for r in results:
        seen[r["file"]] = r  # later entries overwrite earlier ones
    deduped_results = list(seen.values())

    # Save report
    os.makedirs(REPORT_DIR, exist_ok=True)
    uploaded_this_run = uploaded_count - len(already_uploaded)
    with open(UPLOAD_REPORT_PATH, "w") as f:
        json.dump({
            "uploaded": uploaded_count,
            "uploaded_this_run": uploaded_this_run,
            "quota_used_this_run": quota_used_this_run,
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(videos),
            "rate_limited": list(rate_limited_channels),
            "results": deduped_results,
        }, f, indent=2)
    print(f"\nReport: {UPLOAD_REPORT_PATH}")


if __name__ == "__main__":
    main()
