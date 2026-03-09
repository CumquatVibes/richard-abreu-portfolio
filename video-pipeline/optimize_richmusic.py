#!/usr/bin/env python3
"""RichMusic channel optimization script.

Fixes identified in the March 2026 channel audit:
  1. Make 3 private "What If" videos public
  2. Update all video metadata (titles, descriptions, tags) for SEO
  3. Update channel branding/description
  4. List stuck/failed videos for triage

Usage:
    python optimize_richmusic.py --publish-whatif    Make "What If" videos public
    python optimize_richmusic.py --fix-metadata      Update titles/descriptions/tags
    python optimize_richmusic.py --fix-branding      Update channel description + keywords
    python optimize_richmusic.py --list-videos       List all videos with status
    python optimize_richmusic.py --all               Run all fixes
    python optimize_richmusic.py --dry-run --all     Preview without writing
"""

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")

RICHMUSIC_CHANNEL_ID = "UCCI_ynXNuutXGrzWDYzUZiA"

# The 3 "What If" videos currently set to private
WHATIF_VIDEO_IDS = {
    # These will be discovered dynamically via --list-videos, but we also
    # keep known IDs for direct targeting
}

# Optimized channel description
NEW_CHANNEL_DESCRIPTION = """What if your favorite pop song was a rap banger? What if today's biggest hit was made in the 80s?

RichMusic creates GENRE-SWAP covers and ERA-SWAP remakes that reimagine famous songs in completely different styles. Plus long-form background music for study, focus, and relaxation.

🎧 Genre Swap — Pop → Rap, Rap → Pop, R&B → Rock
🕰️ Era Swap — Modern hits remade as 80s synth, 90s grunge, 70s disco
📚 Study & Focus Music — 1-hour ambient playlists for work and concentration
🎵 Chill Vibes — Jazz, blues, lo-fi, and acoustic background music

New videos every week. Subscribe for the next "What If?"

#music #genreswap #studymusic #lofi #backgroundmusic"""

NEW_CHANNEL_KEYWORDS = (
    '"genre swap" "era swap" "what if song" "study music" "background music" '
    '"lo-fi beats" "focus music" "chill music" "jazz playlist" "ambient music" '
    '"music reimagined" "song cover" "pop to rap" "80s remix" "relaxing music"'
)

# SEO-optimized descriptions for existing videos
VIDEO_METADATA_FIXES = {
    # Long-form background music — fix generic descriptions
    "chill acoustic study": {
        "title": "Chill Acoustic Study Vibes — 1 Hour Background Music for Focus & Relaxation",
        "description": (
            "1 hour of chill acoustic guitar music for studying, working, or relaxing. "
            "Soft, warm tones to help you focus without distraction.\n\n"
            "🎧 Use this for: studying, homework, reading, coding, creative work\n"
            "⏱️ 1 full hour — no interruptions\n\n"
            "If this helped you focus, hit 👍 and subscribe for more study playlists!\n\n"
            "#studymusic #acousticmusic #backgroundmusic #focusmusic #chillvibes #relaxing"
        ),
        "tags": [
            "study music", "acoustic study music", "chill acoustic", "background music",
            "focus music", "relaxing guitar", "1 hour study music", "concentration music",
            "homework music", "calm acoustic", "study playlist 2026",
        ],
    },
    "ambient meditation": {
        "title": "Ambient Meditation & Deep Relaxation — 1 Hour Calming Background Music",
        "description": (
            "1 hour of ambient meditation music for deep relaxation, yoga, sleep, or mindfulness practice. "
            "Gentle soundscapes to calm your mind.\n\n"
            "🧘 Use this for: meditation, yoga, sleep, stress relief, deep breathing\n"
            "⏱️ 1 full hour — uninterrupted calm\n\n"
            "Subscribe for more meditation and relaxation playlists!\n\n"
            "#meditationmusic #ambientmusic #relaxation #sleepmusic #calmingmusic #mindfulness"
        ),
        "tags": [
            "meditation music", "ambient music", "relaxation music", "deep relaxation",
            "calming music", "sleep music", "yoga music", "mindfulness", "1 hour meditation",
            "stress relief music", "ambient meditation 2026",
        ],
    },
    "cinematic epic": {
        "title": "Cinematic Epic Instrumental — 1 Hour Dramatic Orchestral Background Music",
        "description": (
            "1 hour of cinematic orchestral music — epic, dramatic, and inspiring. "
            "Perfect for creative projects, gaming, writing, or just feeling like a movie protagonist.\n\n"
            "🎬 Use this for: creative work, writing, gaming, video editing, motivation\n"
            "⏱️ 1 full hour — nonstop epic energy\n\n"
            "Subscribe for more cinematic and orchestral playlists!\n\n"
            "#cinematicmusic #epicmusic #orchestral #backgroundmusic #dramaticmusic #inspiringmusic"
        ),
        "tags": [
            "cinematic music", "epic music", "orchestral music", "dramatic music",
            "background music", "inspiring music", "movie soundtrack", "1 hour epic",
            "gaming music", "writing music", "cinematic instrumental 2026",
        ],
    },
    "blues soul": {
        "title": "Blues & Soul Timeless Classics — 1 Hour Smooth Background Music",
        "description": (
            "1 hour of smooth blues and soul music — timeless grooves for relaxing, cooking, "
            "evening vibes, or just unwinding after a long day.\n\n"
            "🎷 Use this for: evening relaxation, dinner music, cooking, driving, chilling\n"
            "⏱️ 1 full hour — pure soul\n\n"
            "Subscribe for more blues, jazz, and soul playlists!\n\n"
            "#bluesmusic #soulmusic #smoothjazz #backgroundmusic #relaxingmusic #eveningvibes"
        ),
        "tags": [
            "blues music", "soul music", "blues playlist", "smooth blues", "timeless classics",
            "relaxing blues", "dinner music", "evening music", "1 hour blues",
            "soul classics", "blues soul 2026",
        ],
    },
    "study focus classical": {
        "title": "Study Focus — 1 Hour Classical Music for Deep Concentration",
        "description": (
            "1 hour of classical music curated for deep focus and concentration. "
            "Piano, strings, and orchestral pieces to power through study sessions.\n\n"
            "📚 Use this for: studying, exams, deep work, reading, problem-solving\n"
            "⏱️ 1 full hour — scientifically backed focus music\n\n"
            "Subscribe for more classical study playlists!\n\n"
            "#classicalmusic #studymusic #focusmusic #concentrationmusic #pianomusic #deepwork"
        ),
        "tags": [
            "classical music", "study music", "focus music", "concentration music",
            "classical piano", "deep work music", "exam study music", "1 hour classical",
            "piano study", "classical focus 2026",
        ],
    },
    "happy upbeat": {
        "title": "Happy Upbeat Feel Good — 1 Hour Positive Background Music for Energy & Motivation",
        "description": (
            "1 hour of happy, upbeat background music to boost your mood and energy. "
            "Bright melodies and positive vibes for your morning routine, workouts, or creative projects.\n\n"
            "☀️ Use this for: morning routine, working out, cleaning, cooking, good vibes\n"
            "⏱️ 1 full hour — nonstop positivity\n\n"
            "Subscribe for more feel-good playlists!\n\n"
            "#happymusic #upbeatmusic #feelgood #positivevibes #backgroundmusic #motivationmusic"
        ),
        "tags": [
            "happy music", "upbeat music", "feel good music", "positive music",
            "motivation music", "morning music", "cheerful music", "1 hour happy",
            "background music", "good vibes 2026",
        ],
    },
    # "What If" genre-swap videos — keep titles, fix descriptions
    "blinding lights": {
        "title": "What If Blinding Lights by The Weeknd Was Made in the 1970s Disco Era? 🕺",
        "description": (
            "What would The Weeknd's 'Blinding Lights' sound like if it was a 1970s disco track? "
            "We reimagined this modern synth-pop hit as a full disco-era production — funky basslines, "
            "string orchestration, and Saturday Night Fever energy.\n\n"
            "🎧 Genre: Era Swap — 2020s Synth-Pop → 1970s Disco\n"
            "🎵 Original: The Weeknd — Blinding Lights (2020)\n\n"
            "What song should we era-swap next? Drop it in the comments!\n\n"
            "Subscribe for more Genre Swap and Era Swap music reimaginings every week.\n\n"
            "#blindinglights #theweeknd #disco #genreswap #eraswap #whatif #musicremake #70smusic"
        ),
        "tags": [
            "blinding lights", "the weeknd", "disco", "genre swap", "era swap",
            "what if", "70s disco", "music reimagined", "blinding lights disco",
            "song remake", "music cover 2026", "what if song",
        ],
    },
    "lose yourself": {
        "title": "What If Lose Yourself by Eminem Was a Pop Ballad? 🎹",
        "description": (
            "What would Eminem's 'Lose Yourself' sound like as an emotional pop ballad? "
            "We took the iconic rap anthem and reimagined it with piano, soft vocals, "
            "and a completely different emotional tone.\n\n"
            "🎧 Genre: Genre Swap — Rap → Pop Ballad\n"
            "🎵 Original: Eminem — Lose Yourself (2002)\n\n"
            "What song should we genre-swap next? Tell us in the comments!\n\n"
            "Subscribe for more Genre Swap music every week.\n\n"
            "#eminem #loseyourself #popballad #genreswap #whatif #musicremake #raptoballad"
        ),
        "tags": [
            "eminem", "lose yourself", "pop ballad", "genre swap", "what if",
            "music reimagined", "rap to pop", "song remake", "eminem pop version",
            "music cover 2026", "what if song",
        ],
    },
    "shape of you": {
        "title": "What If Shape of You by Ed Sheeran Was a Rap Song? 🎤",
        "description": (
            "What would Ed Sheeran's 'Shape of You' sound like as a full rap track? "
            "We took the pop mega-hit and reimagined it with hard-hitting beats, rap verses, "
            "and a completely different energy.\n\n"
            "🎧 Genre: Genre Swap — Pop → Rap\n"
            "🎵 Original: Ed Sheeran — Shape of You (2017)\n\n"
            "What song should we genre-swap next? Drop your pick in the comments!\n\n"
            "Subscribe for more Genre Swap music every week.\n\n"
            "#edsheeran #shapeofyou #rap #genreswap #whatif #musicremake #poptrap"
        ),
        "tags": [
            "ed sheeran", "shape of you", "rap", "genre swap", "what if",
            "music reimagined", "pop to rap", "song remake", "shape of you rap",
            "music cover 2026", "what if song",
        ],
    },
}


# ── Auth ────────────────────────────────────────────────────────────────────

def get_access_token():
    """Refresh OAuth token for RichMusic channel."""
    with open(CHANNEL_TOKENS_PATH) as f:
        tokens = json.load(f)

    entry = tokens.get("RichMusic")
    if not entry:
        print("ERROR: No RichMusic entry in channel_tokens.json")
        sys.exit(1)

    payload = json.dumps({
        "client_id": entry["client_id"],
        "client_secret": entry["client_secret"],
        "refresh_token": entry["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()

    req = Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode())
        return data["access_token"]
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        print(f"ERROR: Token refresh failed: {err[:300]}")
        sys.exit(1)


def _api_call(method, url, access_token, payload=None, label="api"):
    """Generic YouTube API call with error handling."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = json.dumps(payload).encode() if payload else None
    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        print(f"  [{label}] HTTP {e.code}: {err[:300]}")
        return None


# ── List videos ─────────────────────────────────────────────────────────────

def cmd_list_videos(access_token):
    """List all videos on the RichMusic channel with their status."""
    print("\n=== RichMusic Video Library ===")

    # Use search to find all videos
    videos = []
    page_token = ""
    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&channelId={RICHMUSIC_CHANNEL_ID}"
            f"&type=video&maxResults=50&order=date"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        data = _api_call("GET", url, access_token, label="search")
        if not data:
            break

        for item in data.get("items", []):
            videos.append({
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "published": item["snippet"]["publishedAt"][:10],
            })

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    if not videos:
        print("  No videos found via search. Trying content details...")
        return []

    # Get detailed status for each video
    video_ids = ",".join(v["video_id"] for v in videos)
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,status,statistics&id={video_ids}"
    )
    details = _api_call("GET", url, access_token, label="video_details")

    if details and "items" in details:
        detail_map = {item["id"]: item for item in details["items"]}
        for v in videos:
            d = detail_map.get(v["video_id"], {})
            status = d.get("status", {})
            stats = d.get("statistics", {})
            v["privacy"] = status.get("privacyStatus", "?")
            v["views"] = stats.get("viewCount", "0")
            v["likes"] = stats.get("likeCount", "0")

    print(f"\n  {'Title':<65} {'Privacy':<10} {'Views':>6} {'Likes':>6} {'ID'}")
    print(f"  {'-'*65} {'-'*10} {'-'*6} {'-'*6} {'-'*11}")
    for v in videos:
        title = v["title"][:64]
        print(f"  {title:<65} {v.get('privacy','?'):<10} {v.get('views','?'):>6} "
              f"{v.get('likes','?'):>6} {v['video_id']}")

    return videos


# ── Make "What If" videos public ────────────────────────────────────────────

def cmd_publish_whatif(access_token, dry_run=False):
    """Find private 'What If' videos and make them public."""
    print("\n=== Publish 'What If' Videos ===")

    # Search won't find private videos — we need to list via uploads playlist
    # The uploads playlist ID is the channel ID with "UU" prefix instead of "UC"
    uploads_playlist = RICHMUSIC_CHANNEL_ID.replace("UC", "UU", 1)

    all_video_ids = []
    page_token = ""
    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/playlistItems"
            f"?part=contentDetails,snippet&playlistId={uploads_playlist}"
            f"&maxResults=50"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        data = _api_call("GET", url, access_token, label="uploads_list")
        if not data:
            break

        for item in data.get("items", []):
            vid = item["contentDetails"]["videoId"]
            title = item["snippet"]["title"]
            all_video_ids.append((vid, title))

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    if not all_video_ids:
        print("  No videos found in uploads playlist.")
        return

    # Get status of all videos
    ids_str = ",".join(vid for vid, _ in all_video_ids)
    url = f"https://www.googleapis.com/youtube/v3/videos?part=status,snippet&id={ids_str}"
    details = _api_call("GET", url, access_token, label="video_status")

    if not details or "items" not in details:
        print("  Could not fetch video details.")
        return

    published = 0
    for item in details["items"]:
        vid = item["id"]
        title = item["snippet"]["title"]
        privacy = item["status"]["privacyStatus"]

        # Find "What If" videos that are private
        if "what if" not in title.lower():
            continue

        if privacy == "public":
            print(f"  Already public: {title[:60]}")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would publish: {title[:60]} ({privacy} → public)")
            published += 1
            continue

        # Update to public
        update_url = "https://www.googleapis.com/youtube/v3/videos?part=status"
        result = _api_call("PUT", update_url, access_token, payload={
            "id": vid,
            "status": {"privacyStatus": "public"},
        }, label="publish")

        if result:
            print(f"  Published: {title[:60]} ({privacy} → public)")
            published += 1
        else:
            print(f"  FAILED to publish: {title[:60]}")
        time.sleep(1)

    print(f"\n  Total published: {published}")


# ── Fix video metadata ──────────────────────────────────────────────────────

def cmd_fix_metadata(access_token, dry_run=False):
    """Update titles, descriptions, and tags on all videos for SEO."""
    print("\n=== Fix Video Metadata (SEO) ===")

    # Get all videos via uploads playlist
    uploads_playlist = RICHMUSIC_CHANNEL_ID.replace("UC", "UU", 1)

    all_video_ids = []
    page_token = ""
    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/playlistItems"
            f"?part=contentDetails&playlistId={uploads_playlist}&maxResults=50"
        )
        if page_token:
            url += f"&pageToken={page_token}"
        data = _api_call("GET", url, access_token, label="uploads")
        if not data:
            break
        for item in data.get("items", []):
            all_video_ids.append(item["contentDetails"]["videoId"])
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    if not all_video_ids:
        print("  No videos found.")
        return

    # Get full details
    ids_str = ",".join(all_video_ids)
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id={ids_str}"
    details = _api_call("GET", url, access_token, label="video_details")
    if not details or "items" not in details:
        print("  Could not fetch video details.")
        return

    updated = 0
    for item in details["items"]:
        vid = item["id"]
        snippet = item["snippet"]
        current_title = snippet["title"]
        lower_title = current_title.lower()

        # Match against our fix map
        matched_key = None
        for key in VIDEO_METADATA_FIXES:
            if key in lower_title:
                matched_key = key
                break

        if not matched_key:
            print(f"  SKIP (no fix mapped): {current_title[:60]}")
            continue

        fix = VIDEO_METADATA_FIXES[matched_key]
        new_title = fix["title"]
        new_desc = fix["description"]
        new_tags = fix["tags"]

        # Check if already optimized
        if current_title == new_title:
            print(f"  Already optimized: {current_title[:60]}")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would update: {current_title[:50]}")
            print(f"         →  {new_title[:50]}")
            updated += 1
            continue

        # Update snippet via videos.update
        update_url = "https://www.googleapis.com/youtube/v3/videos?part=snippet"
        result = _api_call("PUT", update_url, access_token, payload={
            "id": vid,
            "snippet": {
                "title": new_title,
                "description": new_desc,
                "tags": new_tags,
                "categoryId": snippet.get("categoryId", "10"),
                "defaultLanguage": "en",
            },
        }, label="update_metadata")

        if result:
            print(f"  Updated: {new_title[:60]}")
            updated += 1
        else:
            print(f"  FAILED: {current_title[:60]}")
        time.sleep(1)

    print(f"\n  Total updated: {updated}")


# ── Fix channel branding ────────────────────────────────────────────────────

def cmd_fix_branding(access_token, dry_run=False):
    """Update channel description and keywords."""
    print("\n=== Fix Channel Branding ===")

    if dry_run:
        print(f"  [DRY-RUN] Would update channel description to:")
        print(f"  {NEW_CHANNEL_DESCRIPTION[:100]}...")
        print(f"  [DRY-RUN] Would update keywords to:")
        print(f"  {NEW_CHANNEL_KEYWORDS[:100]}...")
        return

    # Update branding settings
    url = "https://www.googleapis.com/youtube/v3/channels?part=brandingSettings"
    result = _api_call("PUT", url, access_token, payload={
        "id": RICHMUSIC_CHANNEL_ID,
        "brandingSettings": {
            "channel": {
                "description": NEW_CHANNEL_DESCRIPTION,
                "keywords": NEW_CHANNEL_KEYWORDS,
                "defaultLanguage": "en",
                "country": "US",
            }
        }
    }, label="branding")

    if result:
        print("  Channel branding updated successfully.")
    else:
        print("  FAILED to update branding.")

    # Also update snippet for country
    url2 = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={RICHMUSIC_CHANNEL_ID}"
    current = _api_call("GET", url2, access_token, label="get_snippet")
    if current and current.get("items"):
        snippet = current["items"][0].get("snippet", {})
        url3 = "https://www.googleapis.com/youtube/v3/channels?part=snippet"
        _api_call("PUT", url3, access_token, payload={
            "id": RICHMUSIC_CHANNEL_ID,
            "snippet": {
                "title": snippet.get("title", "RichMusic"),
                "description": NEW_CHANNEL_DESCRIPTION,
                "defaultLanguage": "en",
                "country": "US",
            }
        }, label="snippet_country")
        print("  Channel snippet/country updated.")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RichMusic channel optimization")
    parser.add_argument("--publish-whatif", action="store_true",
                        help="Make private 'What If' videos public")
    parser.add_argument("--fix-metadata", action="store_true",
                        help="Update all video titles/descriptions/tags for SEO")
    parser.add_argument("--fix-branding", action="store_true",
                        help="Update channel description and keywords")
    parser.add_argument("--list-videos", action="store_true",
                        help="List all videos with status")
    parser.add_argument("--all", action="store_true",
                        help="Run all optimization fixes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    args = parser.parse_args()

    if not any([args.publish_whatif, args.fix_metadata, args.fix_branding,
                args.list_videos, args.all]):
        parser.print_help()
        sys.exit(1)

    if args.dry_run:
        print("[DRY-RUN MODE]")

    print("Authenticating with RichMusic channel...")
    token = get_access_token()
    print("  Authenticated.\n")

    if args.all or args.list_videos:
        cmd_list_videos(token)

    if args.all or args.publish_whatif:
        cmd_publish_whatif(token, args.dry_run)

    if args.all or args.fix_metadata:
        cmd_fix_metadata(token, args.dry_run)

    if args.all or args.fix_branding:
        cmd_fix_branding(token, args.dry_run)

    print("\n" + "=" * 50)
    print("MANUAL STEPS REQUIRED:")
    print("  1. Change handle: Go to YouTube Studio → Settings → Channel → Basic Info")
    print("     → Change '@RichMusic99-q1d' to '@RichMusicVibes' or '@WhatIfMusic'")
    print("  2. Upload banner: YouTube Studio → Customization → Branding → Banner image")
    print("     → Upload 2048x1152px image with 'What If Music' / genre-swap concept")
    print("  3. Verify phone: YouTube Studio → Settings → Channel → Feature eligibility")
    print("     → Verify with phone to unlock >15min uploads (fixes 15 stuck videos)")
    print("=" * 50)
    print("\nDone.")


if __name__ == "__main__":
    main()
