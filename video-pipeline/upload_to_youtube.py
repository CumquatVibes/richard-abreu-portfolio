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
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.telemetry import log_video_published, get_daily_quota, record_quota_usage

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
    "CumquatGaming": ("UCJzYsB6MJgQnakQF_S35SRw", "20"),
    "CumquatShortform": ("UCcmzxbB2cfClq_nN3P5c6ow", "22"),
    "RichArt": ("UCGOmSWqmp5LNaKNlLGTE-Nw", "22"),
    "RichTraining": ("UCcY9CwSBVjpMqCjB7oPjfRA", "27"),
}

# YouTube category IDs (reference)
# 1=Film&Animation, 2=Cars, 10=Music, 15=Pets&Animals, 17=Sports,
# 19=Travel, 20=Gaming, 22=People&Blogs, 23=Comedy, 24=Entertainment,
# 26=Howto&Style, 27=Education, 28=Science&Technology
_TITLE_CATEGORY_RULES = [
    # Keywords → category_id
    (["apple", "adobe", "software", "app", "tech review", "gadget", "ai tool",
      "python", "code", "programming", "gpu", "cpu", "pc build", "android",
      "iphone", "samsung", "windows", "linux", "cloud", "saas", "api"],          "28"),
    (["invest", "stock", "crypto", "bitcoin", "ethereum", "finance", "money",
      "budget", "wealth", "dividend", "forex", "nft", "defi", "web3"],           "27"),
    (["how to", "tutorial", "guide", "diy", "recipe", "cook", "clean",
      "organize", "setup", "install", "fix", "repair"],                           "26"),
    (["history", "ancient", "war", "empire", "civilization", "medieval",
      "world war", "president", "dynasty"],                                       "27"),
    (["science", "space", "nasa", "physics", "biology", "quantum",
      "evolution", "planet", "black hole"],                                       "28"),
    (["game", "gaming", "gameplay", "playstation", "xbox", "nintendo",
      "esport", "stream", "twitch"],                                              "20"),
    (["music", "lofi", "jazz", "ambient", "playlist", "beats", "song"],          "10"),
    (["travel", "destination", "city tour", "vacation", "country"],              "19"),
    (["fitness", "workout", "gym", "exercise", "diet", "nutrition"],             "17"),
    (["art", "painting", "artist", "gallery", "museum", "slideshow"],            "1"),
    (["comedy", "funny", "laugh", "meme", "prank"],                              "23"),
]


def detect_category_from_title(title, default_category):
    """Override channel default category based on video title keywords.

    Prevents mismatches like a tech review landing in 'People & Blogs'.
    Returns original default if no keyword match found.
    """
    t = title.lower()
    for keywords, cat_id in _TITLE_CATEGORY_RULES:
        if any(kw in t for kw in keywords):
            return cat_id
    return default_category


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
    "CumquatVibes": "CumquatVibes",
    "CumquatGaming": "CumquatGaming",
    "CumquatShortform": "CumquatShortform",
}

CHANNEL_NICHE = {
    "CumquatVibes": "4K art slideshows, creator tools, design tutorials, and tech reviews",
    "CumquatGaming": "gaming news, indie game reviews, retro gaming, and hidden gems",
    "CumquatShortForm": "viral facts, mind-blowing moments, and quick entertainment",
    "CumquatMotivation": "motivation, discipline, stoic philosophy, and success mindset",
    "RichTech": "tech, gadgets, and AI tools",
    "RichPets": "pet care, animal behavior, and fun pet facts",
    "RichHorror": "true horror stories, unsolved mysteries, and haunted places",
    "RichMind": "psychology, dark psychology, and the human mind",
    "HowToUseAI": "AI tutorials, productivity tools, and making money with AI",
    "RichReviews": "product reviews, comparisons, and honest tech analysis",
    "RichGaming": "gameplay, game reviews, and gaming news",
    "RichHistory": "ancient history, world events, and forgotten civilizations",
    "RichNature": "nature, wildlife, and amazing animal facts",
    "RichScience": "space, physics, biology, and science explained",
    "RichFinance": "personal finance, investing, and building wealth",
    "RichCrypto": "cryptocurrency, blockchain, and Web3",
    "RichMovie": "movie reviews, film analysis, and cinema breakdowns",
    "RichComedy": "comedy, humor, and funny moments",
    "RichSports": "sports news, highlights, and athletic stories",
    "RichMusic": "curated music playlists, lo-fi beats, jazz, blues, ambient music",
    "RichTravel": "travel guides, hidden destinations, and world exploration",
    "RichFood": "food reviews, street food, and culinary adventures",
    "RichFitness": "fitness, workouts, and healthy living",
    "RichEducation": "learning, study tips, and educational deep dives",
    "RichLifestyle": "lifestyle tips, productivity, and daily routines",
    "RichFashion": "fashion trends, style tips, and outfit ideas",
    "RichBeauty": "skincare, beauty tips, and dermatologist-approved routines",
    "RichCooking": "cooking, recipes, and kitchen hacks",
    "RichFamily": "parenting tips, family activities, and family life",
    "RichCars": "car reviews, comparisons, and automotive news",
    "RichDIY": "DIY projects, home improvement, and life hacks",
    "RichDesign": "graphic design, web design, UI/UX, and creative tools",
    "RichPhotography": "photography tips, camera reviews, and editing tutorials",
    "RichMemes": "meme compilations, viral memes, and internet humor",
    "RichAnimation": "animation reviews, anime, and animation breakdowns",
    "RichVlogging": "vlogging tips, creator lifestyle, and YouTube growth",
    "RichKids": "educational kids content, family-friendly fun, and learning",
    "RichDance": "dance tutorials, choreography, and dance fitness",
    "EvaReyes": "women's empowerment, inspiration, and self-improvement",
    "HowToMeditate": "meditation, mindfulness, and stress relief",
    "RichBusiness": "entrepreneurship, side hustles, and business strategy",
    "RichArt": "4K art slideshows, art for your TV, ambient art, art essays",
}

# Channels that use the "Turn Your TV Into Art" template
ART_SLIDESHOW_CHANNELS = {"RichArt"}

# Channels that use the ambient/background music description template
MUSIC_CHANNELS = {"RichMusic"}

CHANNEL_TAGS = {
    # --- CumquatVibes (personal brand) ---
    "CumquatVibes": [
        "Cumquat Vibes", "Richard Abreu", "4k art", "art for tv",
        "digital art", "design tutorial", "creator tools", "tech review",
        "AI tools", "creator economy", "art slideshow", "Affinity Designer",
        "creative business", "art screensaver", "tv wall art",
    ],
    # --- Cumquat brand channels ---
    "CumquatGaming": [
        "gaming", "indie games", "game review", "retro gaming", "PS Vita",
        "hidden gems", "top games", "gaming news", "Nintendo", "PlayStation",
        "gaming 2026", "best games", "game recommendations",
    ],
    "CumquatShortForm": [
        "shorts", "viral facts", "mind blowing", "did you know",
        "satisfying", "amazing facts", "quick facts", "fun facts",
    ],
    "CumquatMotivation": [
        "motivation", "discipline", "stoic philosophy", "morning routine",
        "success mindset", "self improvement", "military mindset", "hustle",
        "motivational speech", "stoicism", "mental toughness", "daily motivation",
    ],
    # --- Rich brand channels ---
    "RichTech": [
        "tech", "technology", "gadgets", "AI tools", "software review",
        "tech 2026", "best apps", "future tech", "productivity", "tech tips",
        "tech news", "best gadgets", "app review",
    ],
    "RichPets": [
        "pets", "pet care", "dog care", "cat breeds", "pet health",
        "animal behavior", "pet tips", "pet owner tips", "dog training", "cat care",
        "cute animals", "pet advice",
    ],
    "RichHorror": [
        "horror", "true horror stories", "unsolved mysteries", "haunted places",
        "scary stories", "creepy", "paranormal", "true crime", "horror 2026", "scary",
        "ghost stories", "dark stories",
    ],
    "RichMind": [
        "psychology", "dark psychology", "body language", "manipulation tactics",
        "mindset", "overthinking", "mental health", "human behavior",
        "cognitive biases", "self improvement", "stoicism", "emotional intelligence",
    ],
    "HowToUseAI": [
        "AI", "artificial intelligence", "ChatGPT", "AI tools", "automation",
        "AI tutorial", "prompt engineering", "make money with AI",
        "how to use AI", "productivity tools", "AI 2026", "Claude AI", "Gemini AI",
    ],
    "RichReviews": [
        "product review", "tech review", "best products", "amazon finds",
        "honest review", "comparison", "worth it", "budget picks", "top 10",
        "product comparison", "buying guide",
    ],
    "RichGaming": [
        "gaming", "gameplay", "game review", "best games", "gaming news",
        "PlayStation", "Xbox", "Nintendo", "PC gaming", "esports",
        "gaming 2026", "game tips",
    ],
    "RichHistory": [
        "history", "ancient history", "world history", "historical events",
        "war history", "civilization", "medieval history", "history documentary",
        "forgotten history", "history explained", "history facts",
    ],
    "RichNature": [
        "nature", "wildlife", "animals", "nature documentary", "ocean life",
        "endangered species", "national parks", "planet earth", "nature facts",
        "amazing animals", "biodiversity",
    ],
    "RichScience": [
        "science", "space", "physics", "NASA", "biology", "quantum physics",
        "science explained", "universe", "black holes", "science facts",
        "science 2026", "technology",
    ],
    "RichFinance": [
        "personal finance", "investing", "stock market", "passive income",
        "money management", "financial freedom", "wealth building", "budget tips",
        "finance 2026", "save money", "investment strategy",
    ],
    "RichCrypto": [
        "crypto", "cryptocurrency", "Bitcoin", "Ethereum", "blockchain",
        "Web3", "DeFi", "crypto news", "crypto 2026", "altcoins",
        "crypto investing", "digital currency",
    ],
    "RichMovie": [
        "movies", "movie review", "film analysis", "best movies", "movie recap",
        "cinema", "film review", "movie recommendations", "movie 2026",
        "top movies", "movie breakdown",
    ],
    "RichComedy": [
        "comedy", "funny", "humor", "stand up", "funny moments",
        "comedy 2026", "laugh", "jokes", "hilarious",
    ],
    "RichSports": [
        "sports", "sports news", "football", "basketball", "soccer",
        "sports highlights", "sports 2026", "NFL", "NBA", "athlete",
        "sports analysis", "game highlights",
    ],
    "RichMusic": [
        "music playlist", "lo-fi beats", "study music", "chill music",
        "jazz playlist", "blues music", "ambient music", "relaxing music",
        "background music", "focus music", "cafe music", "work music",
    ],
    "RichTravel": [
        "travel", "travel guide", "best destinations", "travel tips",
        "budget travel", "travel vlog", "hidden gems", "world travel",
        "travel 2026", "vacation ideas", "city guide",
    ],
    "RichFood": [
        "food", "food review", "best restaurants", "street food", "food tour",
        "food 2026", "taste test", "cooking", "foodie", "recipe",
        "food challenge",
    ],
    "RichFitness": [
        "fitness", "workout", "gym", "exercise", "weight loss",
        "home workout", "muscle building", "fitness tips", "healthy lifestyle",
        "fitness 2026", "nutrition", "personal training",
    ],
    "RichEducation": [
        "education", "learning", "study tips", "online courses", "knowledge",
        "self education", "study motivation", "educational", "how to learn",
        "education 2026", "skills",
    ],
    "RichLifestyle": [
        "lifestyle", "daily routine", "life hacks", "productivity",
        "minimalism", "self improvement", "lifestyle tips", "morning routine",
        "life advice", "lifestyle 2026",
    ],
    "RichFashion": [
        "fashion", "style tips", "outfit ideas", "fashion trends",
        "mens fashion", "fashion 2026", "streetwear", "wardrobe essentials",
        "fashion advice", "style guide",
    ],
    "RichBeauty": [
        "beauty", "skincare", "makeup", "beauty tips", "skincare routine",
        "beauty 2026", "beauty products", "self care", "dermatologist approved",
        "beauty hacks", "glow up",
    ],
    "RichCooking": [
        "cooking", "recipes", "easy recipes", "kitchen hacks", "meal prep",
        "cooking tips", "chef", "homemade", "cooking 2026", "healthy recipes",
        "quick meals", "dinner ideas",
    ],
    "RichFamily": [
        "family", "parenting", "family tips", "kids activities",
        "family life", "parenting advice", "family fun", "parenthood",
        "family 2026", "mom life", "dad life",
    ],
    "RichCars": [
        "cars", "car review", "best cars", "car comparison", "electric cars",
        "car 2026", "automotive", "sports cars", "car buying guide",
        "new cars", "car news", "EV",
    ],
    "RichDIY": [
        "DIY", "do it yourself", "home improvement", "DIY projects",
        "life hacks", "crafts", "home repair", "DIY 2026", "how to",
        "maker", "woodworking",
    ],
    "RichDesign": [
        "design", "graphic design", "web design", "UI UX", "design tips",
        "creative design", "design 2026", "typography", "branding",
        "design tutorial", "Figma",
    ],
    "RichPhotography": [
        "photography", "photo tips", "camera review", "photography tutorial",
        "portrait photography", "landscape photography", "photography 2026",
        "photo editing", "Lightroom", "best camera",
    ],
    "RichMemes": [
        "memes", "funny memes", "meme compilation", "internet memes",
        "viral memes", "trending memes", "meme review",
    ],
    "RichAnimation": [
        "animation", "animated", "cartoon", "anime", "animation review",
        "animation breakdown", "Studio Ghibli", "Pixar", "animation 2026",
        "animation explained", "best animated",
    ],
    "RichVlogging": [
        "vlog", "vlogging", "daily vlog", "vlog tips", "how to vlog",
        "vlog setup", "vlogging 2026", "content creator", "YouTube tips",
        "vlog camera", "creator lifestyle",
    ],
    "RichKids": [
        "kids", "children", "kids educational", "kids fun", "family friendly",
        "kids 2026", "learn for kids", "kids activities", "cartoon",
        "kids entertainment",
    ],
    "RichDance": [
        "dance", "dance tutorial", "choreography", "dance moves",
        "dance 2026", "hip hop dance", "dance workout", "learn to dance",
    ],
    "EvaReyes": [
        "women empowerment", "self improvement", "confidence", "inspiration",
        "mindset", "self care", "career growth", "motivational", "affirmations",
        "women in business", "self love", "girl boss",
    ],
    "HowToMeditate": [
        "meditation", "how to meditate", "mindfulness", "guided meditation",
        "calm", "stress relief", "relaxation", "meditation for beginners",
        "breathing exercises", "zen", "inner peace",
    ],
    "RichBusiness": [
        "business", "entrepreneurship", "side hustle", "startup",
        "business tips", "make money online", "business 2026", "passive income",
        "business strategy", "small business", "online business",
    ],
    "RichArt": [
        "art for tv", "tv wall art", "4k art", "4k slideshow", "art background",
        "living room tv art", "frame tv art", "ambient video", "relaxing art",
        "art slideshow", "wall art video", "background art", "turn your tv into art",
        "samsung frame tv art", "art screensaver",
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


def _refresh_oauth_token(creds_dict, label="default", max_retries=3):
    """Refresh an OAuth token with retry logic and exponential backoff.

    Args:
        creds_dict: Dict with client_id, client_secret, refresh_token
        label: Label for error messages
        max_retries: Number of retry attempts

    Returns:
        access_token string

    Raises:
        RuntimeError if all retries fail
    """
    data = urllib.parse.urlencode({
        "client_id": creds_dict["client_id"],
        "client_secret": creds_dict["client_secret"],
        "refresh_token": creds_dict["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()

    for attempt in range(max_retries):
        try:
            req = Request("https://oauth2.googleapis.com/token", data=data)
            resp = json.loads(urlopen(req, timeout=30).read())
            token = resp.get("access_token")
            if not token:
                raise KeyError(f"No access_token in response: {list(resp.keys())}")
            return token
        except (HTTPError, OSError, KeyError, json.JSONDecodeError) as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Token refresh failed for {label} (attempt {attempt+1}): {e}")
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Failed to refresh token for {label} after {max_retries} attempts: {e}"
                )


def refresh_default_token():
    """Get fresh access token from the default google_token.json."""
    with open(TOKEN_PATH) as f:
        creds = json.load(f)
    return _refresh_oauth_token(creds, label="default")


def refresh_channel_token(channel_creds):
    """Get fresh access token for a specific channel."""
    return _refresh_oauth_token(channel_creds, label="channel")


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


def read_script_frontmatter(script_path):
    """Extract YAML-like frontmatter from script file.

    Returns dict with keys like 'title', 'channel', 'format'.
    """
    if not script_path or not os.path.exists(script_path):
        return {}
    try:
        with open(script_path, encoding="utf-8", errors="replace") as f:
            content = f.read(2000)  # frontmatter is always at the top
    except Exception:
        return {}
    m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip().lower()] = val.strip()
    return fm


def load_seo_sidecar(video_filename):
    """Load SEO JSON sidecar for a video if it exists.

    Searches for <base>_seo.json in the scripts directory.
    Returns dict with keys: titles, description, tags, category_id.
    """
    base = os.path.splitext(os.path.basename(video_filename))[0]
    # Try exact match first, then prefix match (filenames may be truncated)
    for f in os.listdir(SCRIPTS_DIR):
        if not f.endswith("_seo.json"):
            continue
        seo_base = f[:-len("_seo.json")]
        if seo_base == base or base.startswith(seo_base) or seo_base.startswith(base):
            path = os.path.join(SCRIPTS_DIR, f)
            try:
                with open(path) as fh:
                    data = json.load(fh)
                return data
            except Exception:
                pass
    return {}


def make_title(filename, script_path=None, seo_data=None):
    """Generate a CTR-optimized YouTube title.

    Priority order:
    1. Script frontmatter ---title: field (best quality, has punctuation)
    2. SEO sidecar first title (if available)
    3. Filename-derived title (fallback)

    Title optimization rules:
    - 40-70 chars (full display width in search)
    - Include numbers (+36% CTR boost)
    - Front-load keywords (most important words first)
    - Use power words that drive curiosity
    """
    # Try frontmatter title first (highest quality — has punctuation, hooks)
    if script_path:
        fm = read_script_frontmatter(script_path)
        fm_title = fm.get("title", "").strip()
        if fm_title and len(fm_title) > 10:
            # Truncate at word boundary if over 100 chars (YouTube max)
            if len(fm_title) > 100:
                truncated = fm_title[:97]
                last_space = truncated.rfind(" ")
                if last_space > 40:
                    fm_title = truncated[:last_space] + "..."
            return fm_title

    # Try SEO sidecar title
    if seo_data and seo_data.get("titles"):
        seo_title = seo_data["titles"][0].strip()
        if seo_title and len(seo_title) > 10:
            if len(seo_title) > 100:
                truncated = seo_title[:97]
                last_space = truncated.rfind(" ")
                if last_space > 40:
                    seo_title = truncated[:last_space] + "..."
            return seo_title

    # Fallback: derive from filename
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
    """Generate evenly-spaced timestamp strings for chapter list.

    Chapter names are cleaned to max 40 chars at a word boundary so they
    don't appear as truncated mid-sentence lines in the description.
    """
    if len(chapters) < 2:
        return ""
    interval = total_duration_sec // len(chapters)
    lines = []
    for i, ch in enumerate(chapters):
        mins = (i * interval) // 60
        secs = (i * interval) % 60
        # Clean chapter name — truncate at word boundary, strip trailing punctuation
        clean = ch.strip().rstrip(".,;:*")
        if len(clean) > 40:
            truncated = clean[:38]
            last_space = truncated.rfind(" ")
            clean = truncated[:last_space] if last_space > 15 else truncated
        lines.append(f"{mins}:{secs:02d} {clean}")
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
        "Business inquiries: CEO@cumquat-vibes.com",
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


def _make_music_description(title, script_path):
    """Generate description for RichMusic ambient/background music videos."""
    # Extract genre/mood from title
    genre = title
    for strip in ["1Hr", "1hr", "1 Hour", "2Hr", "2hr", "3Hr", "3hr",
                   "Background Music", "No Copyright", "|", "RichMusic"]:
        genre = genre.replace(strip, "")
    genre = re.sub(r'\s+', ' ', genre).strip(" -–—")
    if not genre:
        genre = "background music"

    # Detect duration
    duration = "1 hour"
    if "2Hr" in title or "2 Hour" in title:
        duration = "2 hours"
    elif "3Hr" in title or "3 Hour" in title:
        duration = "3 hours"

    # Extract visual scene descriptions from script if available
    scenes = []
    if script_path and os.path.exists(script_path):
        with open(script_path) as f:
            content = f.read()
        for match in re.finditer(r'\[VISUAL:\s*(.+?)\]', content):
            scene = match.group(1).strip()
            # Take just the first phrase of each visual description
            short = scene.split(",")[0].strip()
            if short and short not in scenes:
                scenes.append(short)

    parts = [
        f"{duration.title()} of {genre.lower()} for studying, relaxing, sleeping, meditation, or deep focus.",
        f"Let these sounds fill your space and help you unwind.",
        "",
    ]

    # Add timestamps for scenes if we have them
    if scenes and len(scenes) >= 3:
        parts.append("SCENES:")
        segment_mins = 60 // len(scenes) if len(scenes) <= 10 else 6
        for i, scene in enumerate(scenes[:10]):
            ts_min = i * segment_mins
            parts.append(f"{ts_min // 60}:{ts_min % 60:02d}:00 {scene}")
        parts.append("")

    parts.extend([
        "HOW TO USE THIS VIDEO:",
        "- Background music while studying, working, or reading",
        "- Ambient sound for meditation, yoga, or mindfulness",
        "- Relaxation and sleep aid — set a timer and drift off",
        "- Cafe, office, or lobby atmosphere",
        "",
        "---",
        "",
        "Subscribe for new playlists every week!",
        "Like this video if it helped you focus or relax.",
        "",
        "---",
        "",
        "More from RichMusic:",
        "Shop: https://cumquatvibes.com",
        "Portfolio: https://richardabreu.studio",
        "Community: https://vibeconnectionlounge.com",
        "Business inquiries: CEO@cumquat-vibes.com",
        "",
        "\u00a9 2026 Cumquat Vibes Media",
        "AI DISCLOSURE: This video was created with the assistance of AI tools.",
        "",
        f"#{genre.lower().replace(' ', '')} #backgroundmusic #studymusic #relaxingmusic "
        f"#ambientmusic #chillmusic #focusmusic #sleepmusic",
    ])
    return "\n".join(parts)


def _extract_primary_keyword(title):
    """Extract the best primary keyword phrase from a title for triple-keyword SEO.

    Returns a 2-4 word phrase that should appear in title, description, and tags.
    """
    # Remove common filler words to find the core topic
    clean = re.sub(r'\b(the|a|an|and|or|but|in|on|at|to|for|of|is|it|you|your|my|'
                   r'this|that|how|why|what|when|best|top|new|most|really|just|'
                   r'need|will|can|don\'t|do|has|have|are|was|were|'
                   r'\d+)\b', '', title.lower())
    clean = re.sub(r'[^\w\s]', '', clean)
    words = [w for w in clean.split() if len(w) > 2]
    if len(words) >= 2:
        return " ".join(words[:3])
    return title.lower()[:40]


def make_description(channel, title, script_path):
    """Generate SEO-optimized YouTube description for maximum vidIQ score.

    vidIQ Optimize Score checklist targets:
    - Primary keyword in first 200 characters of description
    - Description > 300 characters total
    - Chapters starting at 0:00
    - Relevant hashtags (3-5)

    Structure:
    1. First 2 lines = keyword-rich hook (visible in search results)
    2. Timestamps/chapters (starting at 0:00)
    3. Affiliate links (if product channel)
    4. Niche context paragraph (keyword density boost)
    5. CTA + social links
    6. Hashtags + AI disclosure
    """
    # RichArt uses the "Turn Your TV Into Art" template
    if channel in ART_SLIDESHOW_CHANNELS:
        return _make_art_description(title, script_path)

    # RichMusic uses the ambient/background music template
    if channel in MUSIC_CHANNELS:
        return _make_music_description(title, script_path)

    intro = extract_intro(script_path)
    chapters = extract_chapters_from_script(script_path)
    niche = CHANNEL_NICHE.get(channel, "")
    primary_kw = _extract_primary_keyword(title)

    # CumquatVibes gets a personal brand description (first-person, avatar channel)
    is_avatar = channel in AVATAR_CHANNELS
    is_affiliate = channel in AFFILIATE_CHANNELS

    # First 200 chars are critical for vidIQ — must contain primary keyword.
    # DO NOT repeat the title verbatim (YouTube penalizes duplicate content).
    # Lead with VALUE HOOK from script intro, ensuring keyword appears naturally.
    parts = []
    if intro:
        parts.append(intro)
    elif niche:
        # If no script intro available, generate a keyword-rich opener
        parts.append(f"Everything you need to know about {primary_kw}. "
                     f"In this video, we cover the latest in {niche}.")
    parts.append("")

    # Niche context paragraph — boosts keyword density for SEO Score
    if niche:
        parts.extend([
            f"This video covers {niche}. Whether you're a beginner or an expert, "
            f"you'll find valuable insights on {primary_kw} and related topics.",
            "",
        ])

    # Timestamps / Chapters (boosts watch time + gets "Key Moments" in Google)
    # vidIQ requires first chapter at 0:00 for the Optimize Score checkbox
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
            "Thank you for watching and being part of this journey. Your support means the world to me.",
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
            "Business: CEO@cumquat-vibes.com",
            "",
        ])
    else:
        parts.extend([
            "---",
            "",
            "A huge thank you to everyone who subscribes, likes, and shares. None of this would be possible without your support.",
            "",
            "Subscribe and hit the bell for new videos every week!",
            "Like this video if you found it valuable.",
            "Drop a comment — we read every single one!",
            "",
            "---",
            "",
            "Shop: https://cumquatvibes.com",
            "Portfolio: https://richardabreu.studio",
            "Community: https://vibeconnectionlounge.com",
            "Business inquiries: CEO@cumquat-vibes.com",
            "",
        ])

    # Hashtags: topic-first, not brand-first.
    title_lower = title.lower()
    TOPIC_HASHTAG_MAP = [
        (["apple", "mac", "ipad", "ios", "macos"],          ["#apple", "#mac", "#techreview"]),
        (["adobe", "creative cloud", "photoshop"],           ["#adobe", "#creativecloud", "#design"]),
        (["affinity", "pixelmator"],                         ["#affinity", "#design", "#techreview"]),
        (["ai", "chatgpt", "gemini", "claude", "llm"],       ["#AI", "#artificialintelligence", "#tech"]),
        (["final cut", "premiere", "davinci", "video edit"], ["#videoediting", "#filmmaking", "#tech"]),
        (["python", "code", "programming", "developer"],     ["#coding", "#programming", "#tech"]),
        (["crypto", "bitcoin", "ethereum", "web3"],          ["#crypto", "#bitcoin", "#web3"]),
        (["fitness", "workout", "gym", "exercise"],          ["#fitness", "#workout", "#health"]),
        (["finance", "invest", "stock", "money"],            ["#finance", "#investing", "#money"]),
        (["gaming", "game", "gameplay", "streamer"],         ["#gaming", "#gamer", "#games"]),
        (["art", "painting", "artist", "design"],            ["#art", "#artist", "#creative"]),
        (["music", "beat", "lofi", "jazz", "playlist"],      ["#music", "#lofi", "#chill"]),
        (["travel", "destination", "vacation", "tour"],      ["#travel", "#wanderlust", "#explore"]),
        (["food", "recipe", "cooking", "chef"],              ["#food", "#cooking", "#recipe"]),
        (["motivation", "mindset", "success", "hustle"],     ["#motivation", "#mindset", "#success"]),
        (["horror", "scary", "haunted", "paranormal"],       ["#horror", "#scary", "#truestories"]),
        (["history", "ancient", "medieval", "civilization"], ["#history", "#historyfacts", "#education"]),
        (["psychology", "mind", "behavior", "mental"],       ["#psychology", "#mindset", "#mentalhealth"]),
        (["pet", "dog", "cat", "animal"],                    ["#pets", "#animals", "#petcare"]),
        (["movie", "film", "cinema", "review"],              ["#movies", "#filmreview", "#cinema"]),
        (["car", "auto", "vehicle", "electric"],             ["#cars", "#automotive", "#carreview"]),
        (["meditation", "mindful", "calm", "zen"],           ["#meditation", "#mindfulness", "#calm"]),
        (["business", "entrepreneur", "startup", "hustle"],  ["#business", "#entrepreneur", "#startup"]),
        (["education", "learn", "study", "knowledge"],       ["#education", "#learning", "#knowledge"]),
    ]
    topic_tags = []
    for keywords, tags in TOPIC_HASHTAG_MAP:
        if any(kw in title_lower for kw in keywords):
            topic_tags.extend(tags)
        if len(topic_tags) >= 5:
            break

    if not topic_tags:
        topic_tags = [f"#{channel.lower()}", "#2026"]

    # Cap at 5 hashtags
    hashtags_str = " ".join(dict.fromkeys(topic_tags))

    if is_avatar:
        ai_note = "AI DISCLOSURE: This video features my digital avatar created with AI assistance."
    else:
        ai_note = "AI DISCLOSURE: This video was created with the assistance of AI tools."
    parts.extend([
        "\u00a9 2026 Cumquat Vibes Media",
        ai_note,
        "",
        hashtags_str,
    ])

    return "\n".join(parts)


def make_tags(channel, title, seo_data=None):
    """Generate tags combining channel base tags, SEO sidecar tags, and title keywords.

    Merges from multiple sources for maximum coverage:
    1. Channel base tags (niche-specific, high-volume)
    2. SEO sidecar tags (topic-specific from script generation)
    3. Title keywords (catch-all for remaining relevant terms)

    Targets 15-20 tags with >200 chars total for vidIQ Optimize Score.
    """
    seen_lower = set()
    merged = []

    def _add_tag(tag):
        t = tag.strip()
        if not t or t.lower() in seen_lower:
            return
        seen_lower.add(t.lower())
        merged.append(t)

    # 1. Channel base tags (highest priority — curated high-volume terms)
    for tag in CHANNEL_TAGS.get(channel, []):
        _add_tag(tag)

    # 2. SEO sidecar tags (topic-specific)
    if seo_data and seo_data.get("tags"):
        for tag in seo_data["tags"]:
            # Skip generic filler tags from the sidecar
            if tag.lower() in ("faceless youtube", "ai narration", "top 10", "facts"):
                continue
            _add_tag(tag)

    # 3. Title keywords (fill remaining slots)
    title_words = [w for w in title.lower().split() if len(w) > 3]
    small_words = {"this", "that", "with", "from", "your", "about", "them",
                   "will", "what", "when", "were", "been", "have", "here",
                   "they", "need", "just", "more", "than", "most", "also"}
    for w in title_words:
        if w not in small_words:
            _add_tag(w)

    # 4. Always include "2026" and channel brand
    _add_tag("2026")
    _add_tag("Cumquat Vibes")

    # Cap at 490 chars (YouTube limit is 500)
    result = []
    total_len = 0
    for tag in merged:
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
    Returns True on success, False on failure.
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
        # 403 = channel not verified for custom thumbnails (needs phone verification)
        if e.code == 403:
            print(f"    Thumbnail: Channel needs phone verification for custom thumbnails")
        else:
            print(f"    Thumbnail: Upload error {e.code}: {body[:200]}")
        return False
    except Exception as e:
        print(f"    Thumbnail: Upload error: {str(e)[:150]}")
        return False


def add_to_playlist(video_id, playlist_id, access_token):
    """Add an uploaded video to a YouTube playlist.

    Uses YouTube Data API v3 playlistItems.insert endpoint.
    Returns True on success, False on failure.
    """
    url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
    payload = json.dumps({
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        },
    }).encode()
    req = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        resp = urlopen(req, timeout=30)
        json.loads(resp.read().decode())
        print(f"    Playlist: Added to {playlist_id}")
        return True
    except HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        if "playlistNotFound" in body:
            print(f"    Playlist: {playlist_id} not found (create it first)")
        elif "duplicate" in body.lower():
            print(f"    Playlist: Already in playlist")
            return True
        else:
            print(f"    Playlist: Error {e.code}: {body[:150]}")
        return False
    except Exception as e:
        print(f"    Playlist: Error: {str(e)[:100]}")
        return False


# Per-channel playlist IDs (populate as playlists are created on YouTube)
# Format: channel_prefix -> playlist_id
# These need to be created once per channel via YouTube Studio or API
CHANNEL_PLAYLISTS = {}


def upload_video(filepath, title, description, tags, category_id, access_token,
                  privacy="public", publish_at=None):
    """Upload video using YouTube Data API v3 resumable upload.

    Args:
        publish_at: ISO 8601 datetime string for scheduled publishing.
                    If set, privacy is forced to "private" and the video
                    will auto-publish at the specified time.
                    Example: "2026-03-01T14:00:00Z"

    Returns:
        dict: Upload result on success
        "rate_limited": When channel hit daily upload limit
        None: On other failures
    """
    file_size = os.path.getsize(filepath)

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }

    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status,
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

    upload_url = None
    for init_attempt in range(3):
        try:
            init_resp = urlopen(init_req, timeout=60)
            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                print("    No upload URL returned")
                return None
            break
        except HTTPError as e:
            body = e.read().decode()
            if "uploadLimitExceeded" in body:
                print("    Daily upload limit reached for this channel")
                return "rate_limited"
            if "quota" in body.lower():
                print("    YouTube API daily quota exceeded")
                return "quota_exceeded"
            if e.code in (500, 502, 503) and init_attempt < 2:
                wait = 2 ** init_attempt
                print(f"    Server error {e.code}, retrying in {wait}s (attempt {init_attempt+1}/3)")
                time.sleep(wait)
                continue
            print(f"    Init error {e.code}: {body[:300]}")
            return {"error": f"Init error {e.code}: {body[:300]}"}
        except OSError as e:
            if init_attempt < 2:
                wait = 2 ** init_attempt
                print(f"    Network error, retrying in {wait}s (attempt {init_attempt+1}/3): {e}")
                time.sleep(wait)
                continue
            return {"error": f"Network error after 3 attempts: {e}"}

    if not upload_url:
        return {"error": "Failed to get upload URL after retries"}

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


def run_video_quality_gate(filepath, channel):
    """Check video file quality metrics before uploading.

    Validates bitrate, duration, and file size to prevent uploading
    low-quality or broken videos.

    Returns (passed: bool, issues: list[str])
    """
    import subprocess as _sp

    issues = []

    try:
        probe = _sp.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "format=duration,bit_rate,size:stream=width,height,codec_name,r_frame_rate",
             "-of", "json", filepath],
            capture_output=True, text=True, timeout=15,
        )
        data = __import__("json").loads(probe.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        duration = float(fmt.get("duration", 0))
        bitrate = int(fmt.get("bit_rate", 0))
        size_mb = int(fmt.get("size", 0)) / (1024 * 1024)

        # Find video stream
        video_stream = next((s for s in streams if s.get("codec_name") in ("h264", "hevc", "vp9")), None)

        # Check 1: Duration sanity
        if duration < 30:
            issues.append(f"Video too short ({duration:.0f}s) — likely broken or incomplete")
        elif duration > 7200:
            # Only warn for non-music (music can be 1hr+)
            if "Music" not in channel and "Ambient" not in channel:
                issues.append(f"Video unusually long ({duration/60:.0f}min) for non-music channel")

        # Check 2: Bitrate floor (below 800kbps looks terrible on YouTube)
        bitrate_kbps = bitrate / 1000
        if bitrate_kbps < 800:
            issues.append(f"Bitrate too low ({bitrate_kbps:.0f}kbps) — will look blocky on YouTube")
        elif bitrate_kbps < 1500:
            print(f"  WARNING: Low bitrate ({bitrate_kbps:.0f}kbps) — quality may be marginal")

        # Check 3: Resolution
        if video_stream:
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            if width < 1080 and height < 1080:
                issues.append(f"Resolution too low ({width}x{height}) — minimum 1080p expected")

        # Check 4: File size vs duration ratio (detect empty/corrupt files)
        if duration > 0 and size_mb / (duration / 60) < 5:
            issues.append(f"File suspiciously small ({size_mb:.1f}MB for {duration/60:.1f}min) — may be corrupt")

    except Exception as e:
        print(f"  Quality gate: probe failed ({str(e)[:60]}), proceeding with caution")
        return True, []

    if issues:
        for issue in issues:
            print(f"  QUALITY ISSUE: {issue}")

    return len(issues) == 0, issues


POWER_WORDS = {
    "secret", "truth", "proven", "shocking", "ultimate", "insane", "brutal",
    "hidden", "deadly", "genius", "epic", "unbelievable", "guaranteed",
    "devastating", "legendary", "incredible", "powerful", "essential",
    "critical", "explosive", "terrifying", "mysterious", "stunning",
    "mind-blowing", "game-changing", "life-changing", "unstoppable",
}


def validate_seo(title, description, tags, channel):
    """Validate SEO quality of video metadata before upload.

    Returns list of warning strings. Empty list = all good.
    Does NOT block upload — just logs warnings for monitoring.
    """
    warnings = []

    # 1. Power words in title
    title_lower = title.lower()
    if not any(pw in title_lower for pw in POWER_WORDS):
        warnings.append("SEO: Title missing power words (SECRET, PROVEN, HIDDEN, etc.)")

    # 2. Numbers in title
    if not re.search(r'\d', title):
        warnings.append("SEO: Title has no numbers (numbers boost CTR ~36%)")

    # 3. Title length
    if len(title) < 30:
        warnings.append(f"SEO: Title too short ({len(title)} chars, aim for 40-70)")
    elif len(title) > 80:
        warnings.append(f"SEO: Title too long ({len(title)} chars, aim for 40-70)")

    # 4. Tag count
    if len(tags) < 8:
        warnings.append(f"SEO: Only {len(tags)} tags (minimum 8 recommended)")

    # 5. Description length
    if len(description) < 200:
        warnings.append(f"SEO: Description too short ({len(description)} chars, min 200)")

    # 6. Hashtags in description
    if "#" not in description:
        warnings.append("SEO: No hashtags in description")

    if warnings:
        for w in warnings:
            print(f"  {w}")

    return warnings


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

    # Parse --channel filter and --max-uploads from argv
    channel_filter = None
    max_uploads_this_run = None
    for idx, arg in enumerate(sys.argv[1:], 1):
        if arg == '--channel' and idx < len(sys.argv) - 1:
            channel_filter = sys.argv[idx + 1]
        elif arg.startswith('--channel='):
            channel_filter = arg.split('=', 1)[1]
        elif arg == '--max-uploads' and idx < len(sys.argv) - 1:
            max_uploads_this_run = int(sys.argv[idx + 1])
        elif arg.startswith('--max-uploads='):
            max_uploads_this_run = int(arg.split('=', 1)[1])
    print("YouTube Video Uploader")
    print("=" * 60)
    if channel_filter:
        print(f"  Channel filter: {channel_filter}")
    if max_uploads_this_run:
        print(f"  Max uploads this run: {max_uploads_this_run}")
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
    # Scan top-level and one level of subdirectories for MP4 files
    videos = sorted([f for f in os.listdir(VIDEOS_DIR) if f.endswith(".mp4")])
    for subdir in os.listdir(VIDEOS_DIR):
        subdir_path = os.path.join(VIDEOS_DIR, subdir)
        if os.path.isdir(subdir_path) and not subdir.startswith("temp"):
            for f in sorted(os.listdir(subdir_path)):
                if f.endswith(".mp4"):
                    videos.append(os.path.join(subdir, f))
    pending = [v for v in videos if v not in already_uploaded]
    if channel_filter:
        pending = [v for v in pending if os.path.basename(v).split("_")[0] == channel_filter]
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
    uploads_this_run = 0
    skipped_limit = 0
    failed_count = 0
    preflight_blocked = 0

    # Load today's quota usage from DB (persists across runs)
    quota_already_used, uploads_today = get_daily_quota()
    quota_used_this_run = quota_already_used
    if quota_already_used > 0:
        print(f"  Quota already used today: {quota_already_used}/{DAILY_QUOTA_LIMIT} "
              f"({uploads_today} uploads)\n")

    # Load upload schedule if available
    schedule_by_file = {}
    schedule_path = os.path.join(REPORT_DIR, "upload_schedule.json")
    if os.path.exists(schedule_path):
        try:
            with open(schedule_path) as f:
                sched_data = json.load(f)
            for entry in sched_data.get("schedule", []):
                schedule_by_file[entry["file"]] = entry.get("publish_at")
            if schedule_by_file:
                print(f"  Loaded upload schedule: {len(schedule_by_file)} scheduled videos\n")
        except (json.JSONDecodeError, KeyError):
            pass

    for i, video_file in enumerate(pending, 1):
        # Handle subdirectory paths (e.g., "rich_education/RichEducation_Topic.mp4")
        video_basename = os.path.basename(video_file)
        channel = video_basename.split("_")[0]

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

        script_path = find_script(video_file)
        seo_data = load_seo_sidecar(video_file)
        title = make_title(video_file, script_path=script_path, seo_data=seo_data)
        description = make_description(channel, title, script_path)
        tags = make_tags(channel, title, seo_data=seo_data)

        # Override category based on title keywords (prevents tech reviews
        # landing in "People & Blogs" when the channel default is generic).
        category_id = detect_category_from_title(title, category_id)

        # SEO quality check (logs warnings, does not block)
        seo_warnings = validate_seo(title, description, tags, channel)

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
            })
            continue

        # Video quality gate — check bitrate, resolution, duration
        quality_passed, quality_issues = run_video_quality_gate(filepath, channel)
        if not quality_passed:
            print(f"  BLOCKED by video quality gate — skipping upload")
            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": None,
                "status": "quality_blocked",
                "issues": quality_issues,
            })
            continue

        # Generate thumbnail before upload
        thumb_path = generate_thumbnail(title, channel, video_file)

        # Use scheduled publish time if available, otherwise publish immediately
        video_publish_at = schedule_by_file.get(video_file) or schedule_by_file.get(video_basename)
        if video_publish_at:
            privacy = "private"
            print(f"  Scheduled: {video_publish_at}")
        else:
            privacy = "public"
            video_publish_at = None

        result = upload_video(filepath, title, description, tags, category_id, token,
                              privacy=privacy, publish_at=video_publish_at)

        if result == "quota_exceeded":
            print(f"\n  YouTube API quota exhausted. Remaining {len(pending) - i} videos will retry after quota reset (midnight PT).")
            results.append({
                "file": video_file,
                "channel": channel,
                "target_channel_id": channel_id,
                "video_id": None,
                "status": "quota_exceeded",
            })
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
            })
        elif result:
            vid_id = result.get("id", "?")
            status = result.get("status", {}).get("uploadStatus", "?")
            print(f"  Uploaded: https://youtube.com/watch?v={vid_id} (status: {status})")

            # Upload custom thumbnail if we generated one
            thumb_uploaded = False
            if thumb_path and vid_id != "?":
                thumb_uploaded = upload_thumbnail(vid_id, thumb_path, token)

            # Add to channel playlist if configured
            playlist_added = False
            playlist_id = CHANNEL_PLAYLISTS.get(channel)
            if playlist_id and vid_id != "?":
                playlist_added = add_to_playlist(vid_id, playlist_id, token)

            upload_quota = QUOTA_PER_UPLOAD
            if thumb_uploaded:
                upload_quota += QUOTA_PER_THUMBNAIL
            if playlist_added:
                upload_quota += 50  # playlistItems.insert costs ~50 units
            quota_used_this_run += upload_quota

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
            })
            uploaded_count += 1
            uploads_this_run += 1

            # Log to telemetry DB + persist quota usage
            try:
                video_name = os.path.splitext(video_file)[0]
                log_video_published(video_name, vid_id, quota_used=upload_quota)
                record_quota_usage(upload_quota)
            except Exception as e:
                print(f"  WARNING: Failed to log telemetry: {str(e)[:80]}")

            # Check --max-uploads limit (after telemetry is saved)
            if max_uploads_this_run and uploads_this_run >= max_uploads_this_run:
                print("\n  Reached --max-uploads limit (%d). Stopping." % max_uploads_this_run)
                break
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
    with open(UPLOAD_REPORT_PATH, "w") as f:
        json.dump({
            "uploaded": uploaded_count,
            "total": len(videos),
            "rate_limited": list(rate_limited_channels),
            "results": deduped_results,
        }, f, indent=2)
    print(f"\nReport: {UPLOAD_REPORT_PATH}")


if __name__ == "__main__":
    main()
