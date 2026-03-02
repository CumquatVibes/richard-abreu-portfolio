"""Competitive benchmarking for YouTube channels.

For each channel's niche, finds a top-performing competitor video, extracts
the transcript, analyzes what makes it successful, and returns a structured
brief that can be injected into script generation prompts.

Results are cached in SQLite for 7 days to minimize API usage.
"""

import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "output", "pipeline.db")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "AIzaSyCRu7Ac5o-zHm-0q7WrUiKDFEGEg46M7ME")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

CACHE_TTL_DAYS = 7


# ── YouTube Data API ──

def _api_get(url):
    """YouTube Data API GET with API key."""
    sep = "&" if "?" in url else "?"
    req = Request(f"{url}{sep}key={YOUTUBE_API_KEY}")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  [competitive] YouTube API error {e.code}: {err[:200]}")
        return None
    except Exception as e:
        print(f"  [competitive] YouTube API error: {str(e)[:200]}")
        return None


# ── Gemini API ──

def _gemini_call(prompt, retries=2):
    """Gemini Flash call for analysis (temperature 0.7)."""
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}
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
                print(f"  [competitive] Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                err = e.read().decode() if hasattr(e, 'read') else str(e)
                print(f"  [competitive] Gemini error {e.code}: {err[:200]}")
                if attempt == retries - 1:
                    return None
                time.sleep(5)
        except Exception as e:
            print(f"  [competitive] Gemini error: {str(e)[:200]}")
            if attempt == retries - 1:
                return None
            time.sleep(5)
    return None


# ── Search & Transcript ──

def _build_search_query(channel_config):
    """Build a YouTube search query from channel niche + first sub_topic + year."""
    niche = channel_config.get("niche", "general")
    sub_topics = channel_config.get("sub_topics", [])
    first_topic = sub_topics[0] if sub_topics else ""
    year = datetime.now().year
    parts = [niche]
    if first_topic:
        parts.append(first_topic)
    parts.append(str(year))
    return " ".join(parts)


def fetch_top_video(niche_query):
    """Search YouTube for a top-performing video in the niche (last 90 days).

    Returns dict with video_id, title, channel_title, view_count, like_count,
    description — or None on failure.
    """
    published_after = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = urllib.parse.quote(niche_query)
    search_url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&q={query}&type=video&order=viewCount"
        f"&videoDuration=medium&publishedAfter={published_after}&maxResults=5"
    )
    data = _api_get(search_url)
    if not data or "items" not in data or not data["items"]:
        return None

    # Pick the first result
    item = data["items"][0]
    video_id = item["id"]["videoId"]
    snippet = item["snippet"]

    # Fetch stats
    stats_url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=statistics,snippet&id={video_id}"
    )
    stats_data = _api_get(stats_url)
    stats = {}
    description = snippet.get("description", "")
    if stats_data and stats_data.get("items"):
        stats = stats_data["items"][0].get("statistics", {})
        description = stats_data["items"][0].get("snippet", {}).get("description", description)

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "description": description[:500],
    }


def get_video_transcript(video_id, max_seconds=180):
    """Extract first N seconds of auto-captions via yt-dlp.

    Returns transcript text or empty string on failure.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_path = os.path.join(tmpdir, "subs")
        try:
            subprocess.run(
                [
                    "yt-dlp", "--skip-download",
                    "--write-auto-sub", "--sub-lang", "en",
                    "--sub-format", "vtt",
                    "--output", sub_path,
                    f"https://www.youtube.com/watch?v={video_id}",
                ],
                capture_output=True, timeout=30, check=False,
            )
        except FileNotFoundError:
            print("  [competitive] yt-dlp not found, skipping transcript")
            return ""
        except subprocess.TimeoutExpired:
            print("  [competitive] yt-dlp timed out")
            return ""

        # Find the VTT file (yt-dlp may add language suffix)
        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
        if not vtt_files:
            return ""

        vtt_path = os.path.join(tmpdir, vtt_files[0])
        return _parse_vtt_transcript(vtt_path, max_seconds)


def _parse_vtt_transcript(vtt_path, max_seconds):
    """Parse VTT file, dedup overlapping lines, stop at timestamp limit."""
    try:
        with open(vtt_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""

    lines = []
    seen = set()
    ts_pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.\d{3}")

    for line in content.split("\n"):
        line = line.strip()

        # Check timestamp lines
        match = ts_pattern.search(line)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            total_seconds = h * 3600 + m * 60 + s
            if total_seconds > max_seconds:
                break
            continue

        # Skip VTT headers and empty lines
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        # Skip numeric cue identifiers
        if line.isdigit():
            continue

        # Strip VTT tags like <c> </c> <00:00:01.234>
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)

    return " ".join(lines)


# ── Analysis ──

def analyze_competitor(video_data, transcript, niche):
    """Analyze a competitor video and produce a structured brief."""
    title = video_data.get("title", "Unknown")
    channel = video_data.get("channel_title", "Unknown")
    views = video_data.get("view_count", 0)
    likes = video_data.get("like_count", 0)
    description = video_data.get("description", "")

    transcript_section = ""
    if transcript:
        transcript_section = f"\nTRANSCRIPT (first 3 minutes):\n{transcript[:2000]}\n"

    prompt = f"""Analyze this top-performing YouTube video in the {niche} niche.

VIDEO: "{title}" by {channel}
VIEWS: {views:,} | LIKES: {likes:,}
DESCRIPTION: {description[:300]}
{transcript_section}
Produce a competitive brief in EXACTLY these 5 sections (total max 400 words):

HOOK TECHNIQUE:
What hook strategy does the video use in the first 10-30 seconds? (question, stat, bold claim, story, etc.)

TITLE FORMULA:
Break down the title structure. What makes it clickable? (numbers, curiosity gap, power words, specificity)

CONTENT STRUCTURE:
How is the video organized? (listicle, narrative arc, problem-solution, comparison, etc.)

COMPETITIVE EDGE:
What specific angle or unique value does this video offer that others in the niche don't?

ACTIONABLE TAKEAWAYS:
3-5 bullet points our channel can immediately apply to outperform this video.

Be specific and actionable. Reference exact phrases from the title/transcript when relevant."""

    return _gemini_call(prompt)


# ── SQLite Caching ──

def _ensure_table(conn):
    """Create competitor_briefs table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS competitor_briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_key TEXT NOT NULL,
            video_id TEXT,
            video_title TEXT,
            channel_title TEXT,
            view_count INTEGER,
            like_count INTEGER,
            brief_text TEXT,
            search_query TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            UNIQUE(channel_key)
        )
    """)
    conn.commit()


def _get_cached_brief(channel_key):
    """Return cached brief if it exists and is within TTL, else None."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    try:
        row = conn.execute(
            "SELECT brief_text, fetched_at FROM competitor_briefs WHERE channel_key = ?",
            (channel_key,)
        ).fetchone()
        if not row:
            return None
        fetched = datetime.fromisoformat(row["fetched_at"])
        if datetime.utcnow() - fetched > timedelta(days=CACHE_TTL_DAYS):
            return None
        return row["brief_text"]
    finally:
        conn.close()


def _cache_brief(channel_key, video_data, brief_text, search_query=""):
    """Store or update a competitor brief in the cache."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _ensure_table(conn)
    try:
        conn.execute("""
            INSERT INTO competitor_briefs
                (channel_key, video_id, video_title, channel_title, view_count, like_count,
                 brief_text, search_query, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(channel_key) DO UPDATE SET
                video_id = excluded.video_id,
                video_title = excluded.video_title,
                channel_title = excluded.channel_title,
                view_count = excluded.view_count,
                like_count = excluded.like_count,
                brief_text = excluded.brief_text,
                search_query = excluded.search_query,
                fetched_at = excluded.fetched_at
        """, (
            channel_key,
            video_data.get("video_id", ""),
            video_data.get("title", ""),
            video_data.get("channel_title", ""),
            video_data.get("view_count", 0),
            video_data.get("like_count", 0),
            brief_text,
            search_query,
        ))
        conn.commit()
    finally:
        conn.close()


# ── Main Entry Point ──

def get_competitive_brief(channel_key):
    """Get a competitive analysis brief for a channel.

    Checks cache first (7-day TTL), then fetches fresh data.
    Returns brief string, or "" on any failure.
    """
    # Load channel config
    try:
        config_path = os.path.join(BASE_DIR, "channels_config.json")
        with open(config_path) as f:
            config = json.load(f)
        channel_config = config.get("channels", {}).get(channel_key)
        if not channel_config:
            print(f"  [competitive] Channel '{channel_key}' not found in config")
            return ""
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  [competitive] Config error: {e}")
        return ""

    # Check cache
    cached = _get_cached_brief(channel_key)
    if cached:
        print(f"  [competitive] Using cached brief for {channel_key}")
        return cached

    niche = channel_config.get("niche", "general")
    search_query = _build_search_query(channel_config)
    print(f"  [competitive] Searching: {search_query}")

    # Fetch top video
    video_data = fetch_top_video(search_query)
    if not video_data:
        print(f"  [competitive] No videos found for '{search_query}'")
        return ""

    print(f"  [competitive] Found: \"{video_data['title']}\" ({video_data['view_count']:,} views)")

    # Extract transcript
    transcript = get_video_transcript(video_data["video_id"])
    if transcript:
        print(f"  [competitive] Transcript: {len(transcript)} chars")
    else:
        print(f"  [competitive] No transcript available, analyzing without it")

    # Analyze
    brief = analyze_competitor(video_data, transcript, niche)
    if not brief:
        print(f"  [competitive] Analysis failed")
        return ""

    # Cache
    _cache_brief(channel_key, video_data, brief, search_query)
    print(f"  [competitive] Brief cached for {channel_key}")

    return brief
