#!/usr/bin/env python3
"""Re-produce the 3 "What If" genre-swap videos with matching visuals.

Downloads audio from existing YouTube videos, generates themed B-roll,
assembles new videos, uploads them, and unlists the originals.

Usage:
    python reproduce_whatif.py --dry-run    # Preview the plan
    python reproduce_whatif.py              # Full production + upload
    python reproduce_whatif.py --step extract   # Only download audio
    python reproduce_whatif.py --step broll     # Only generate B-roll
    python reproduce_whatif.py --step assemble  # Only assemble videos
    python reproduce_whatif.py --step upload    # Only upload + unlist
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

from utils.assembly import assemble_video

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
WORK_DIR = os.path.join(BASE_DIR, "output", "whatif_remake")
RICHMUSIC_CHANNEL_ID = "UCCI_ynXNuutXGrzWDYzUZiA"

# The 3 videos to re-produce
WHATIF_VIDEOS = [
    {
        "old_video_id": "I2JLlC9v21w",
        "slug": "blinding_lights_disco",
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
        "broll_prompts": [
            "1970s disco dance floor with mirror ball, colorful lights, dancers in bell-bottoms and platform shoes, Saturday Night Fever aesthetic, cinematic wide shot, warm retro color grading, 4K",
            "close-up of vintage vinyl record spinning on a turntable, disco-era album cover visible, warm amber lighting, shallow depth of field, retro music aesthetic, 4K",
            "neon-lit 1970s nightclub exterior with 'DISCO' sign glowing, classic cars parked outside, purple and gold neon reflections on wet pavement, cinematic night shot, 4K",
            "retro analog synthesizer and drum machine setup from the 1970s, colorful knobs and patch cables, warm studio lighting, vintage music production aesthetic, 4K",
            "abstract disco-themed visualization with mirror ball light reflections, prismatic light rays on dark background, sparkle and shimmer, music video aesthetic, 4K",
            "wide shot of 1970s concert stage with dramatic spotlights, funky band performing, string section visible, warm golden stage lighting, retro concert photography, 4K",
        ],
    },
    {
        "old_video_id": "FIND_VIA_SEARCH",  # Will be resolved dynamically
        "slug": "lose_yourself_ballad",
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
        "broll_prompts": [
            "dramatic grand piano in spotlight on dark empty stage, single pianist performing, emotional atmosphere, concert hall with warm amber lighting, cinematic wide shot, 4K",
            "close-up of piano keys being played with emotional intensity, hands pressing chords, shallow depth of field, warm golden side lighting, intimate music performance, 4K",
            "rainy city street at night with blurred car headlights and street lamps, moody emotional atmosphere, reflections on wet pavement, cinematic urban melancholy, 4K",
            "recording studio with vintage microphone and dim amber lighting, sheet music visible, intimate vocal booth atmosphere, warm analog tones, music production, 4K",
            "abstract sound wave visualization in warm gold and deep purple tones, flowing emotional energy pattern, music-inspired digital art, dark background, 4K",
            "silhouette of person standing alone at window looking at city skyline, dramatic backlight, emotional contemplative mood, cinematic composition, warm tones, 4K",
        ],
    },
    {
        "old_video_id": "FIND_VIA_SEARCH",  # Will be resolved dynamically
        "slug": "shape_of_you_rap",
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
        "broll_prompts": [
            "hip-hop recording studio with neon purple and red lighting, mixing board with glowing faders, microphone with pop filter, urban music production aesthetic, 4K",
            "close-up of DJ turntable with vinyl record and hip-hop graffiti art on the wall behind, moody purple and amber lighting, urban music culture, 4K",
            "wide shot of urban concert stage with rapper silhouette, crowd hands up, dramatic red and purple stage lighting, smoke effects, hip-hop performance, 4K",
            "abstract hip-hop beat visualizer with pulsing bass waves in red and purple, dark background with geometric patterns, trap music aesthetic, 4K",
            "graffiti-covered brick wall in urban alley with dramatic spotlight, boom box and sneakers visible, street culture aesthetic, warm amber and cool purple tones, 4K",
            "close-up of professional studio headphones on mixing console, beat-making software on screen in background, warm studio lighting, rap production vibes, 4K",
        ],
    },
]


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
    req = Request("https://oauth2.googleapis.com/token", data=payload,
                  headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]


def _api_call(method, url, access_token, payload=None, label="api"):
    """YouTube API call helper."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        print(f"  [{label}] HTTP {e.code}: {err[:300]}")
        return None


# ── Step 1: Resolve video IDs + extract audio ──────────────────────────────

def resolve_video_ids(access_token):
    """Find the actual video IDs for videos with FIND_VIA_SEARCH placeholder."""
    uploads_playlist = RICHMUSIC_CHANNEL_ID.replace("UC", "UU", 1)
    all_videos = []
    page_token = ""
    while True:
        url = (f"https://www.googleapis.com/youtube/v3/playlistItems"
               f"?part=contentDetails,snippet&playlistId={uploads_playlist}&maxResults=50")
        if page_token:
            url += f"&pageToken={page_token}"
        data = _api_call("GET", url, access_token, label="resolve")
        if not data:
            break
        for item in data.get("items", []):
            all_videos.append({
                "video_id": item["contentDetails"]["videoId"],
                "title": item["snippet"]["title"],
            })
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    for video in WHATIF_VIDEOS:
        if video["old_video_id"] == "FIND_VIA_SEARCH":
            slug_keywords = video["slug"].replace("_", " ").split()
            for v in all_videos:
                lower = v["title"].lower()
                if all(kw in lower for kw in slug_keywords[:2]):
                    video["old_video_id"] = v["video_id"]
                    print(f"  Resolved {video['slug']} → {v['video_id']} ({v['title'][:50]})")
                    break
            if video["old_video_id"] == "FIND_VIA_SEARCH":
                print(f"  WARNING: Could not find video for {video['slug']}")


def step_extract(dry_run=False):
    """Download audio from each original video using yt-dlp."""
    print("\n=== Step 1: Extract Audio ===")
    os.makedirs(WORK_DIR, exist_ok=True)

    for video in WHATIF_VIDEOS:
        vid = video["old_video_id"]
        slug = video["slug"]
        audio_path = os.path.join(WORK_DIR, f"{slug}.m4a")
        video["audio_path"] = audio_path

        if vid == "FIND_VIA_SEARCH":
            print(f"  SKIP {slug}: video ID not resolved")
            continue

        if os.path.exists(audio_path):
            print(f"  SKIP {slug}: audio already extracted ({audio_path})")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would extract audio from {vid} → {slug}.m4a")
            continue

        yt_url = f"https://www.youtube.com/watch?v={vid}"
        print(f"  Extracting audio from {vid} ({slug})...")

        result = subprocess.run([
            sys.executable, "-m", "yt_dlp",
            "-x", "--audio-format", "m4a",
            "--audio-quality", "0",
            "-o", audio_path,
            yt_url,
        ], capture_output=True, text=True, timeout=120)

        if result.returncode == 0 and os.path.exists(audio_path):
            size_kb = os.path.getsize(audio_path) / 1024
            print(f"    Saved: {audio_path} ({size_kb:.0f} KB)")
        else:
            # yt-dlp may add extension — check for variants
            for ext in [".m4a", ".m4a.m4a", ".webm", ".opus"]:
                alt = audio_path.replace(".m4a", ext)
                if os.path.exists(alt) and alt != audio_path:
                    os.rename(alt, audio_path)
                    print(f"    Saved (renamed): {audio_path}")
                    break
            else:
                print(f"    FAILED: {result.stderr[:200] if result.stderr else 'unknown error'}")


# ── Step 2: Generate B-roll images ─────────────────────────────────────────

def _generate_image(prompt, output_path, retries=3):
    """Generate an image via Gemini and save to output_path."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.0-flash-exp-image-generation:generateContent?key={GEMINI_API_KEY}")
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.9},
    }).encode()

    for attempt in range(retries):
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        img_data = base64.b64decode(part["inlineData"]["data"])
                        with open(output_path, "wb") as f:
                            f.write(img_data)
                        return True
            print(f"    No image in response")
            return False
        except HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                body = e.read().decode() if hasattr(e, "read") else str(e)
                print(f"    Gemini error {e.code}: {body[:150]}")
                if attempt == retries - 1:
                    return False
                time.sleep(5)
        except Exception as e:
            print(f"    Error: {str(e)[:150]}")
            if attempt == retries - 1:
                return False
            time.sleep(5)
    return False


def step_broll(dry_run=False):
    """Generate themed B-roll images for each video."""
    print("\n=== Step 2: Generate B-Roll Images ===")

    if not GEMINI_API_KEY:
        print("  ERROR: GEMINI_API_KEY not set")
        return

    for video in WHATIF_VIDEOS:
        slug = video["slug"]
        broll_dir = os.path.join(WORK_DIR, f"{slug}_broll")
        video["broll_dir"] = broll_dir
        os.makedirs(broll_dir, exist_ok=True)

        print(f"\n  {slug} ({len(video['broll_prompts'])} images):")

        for i, prompt in enumerate(video["broll_prompts"]):
            img_path = os.path.join(broll_dir, f"broll_{i+1:02d}.png")

            if os.path.exists(img_path):
                print(f"    [{i+1}/{len(video['broll_prompts'])}] SKIP (exists)")
                continue

            if dry_run:
                print(f"    [{i+1}/{len(video['broll_prompts'])}] [DRY-RUN] {prompt[:60]}...")
                continue

            print(f"    [{i+1}/{len(video['broll_prompts'])}] Generating...")
            if _generate_image(prompt, img_path):
                size_kb = os.path.getsize(img_path) / 1024
                print(f"      Saved ({size_kb:.0f} KB)")
            else:
                print(f"      FAILED")
            time.sleep(3)  # Rate limit buffer


# ── Step 3: Assemble videos ────────────────────────────────────────────────

def step_assemble(dry_run=False):
    """Assemble new videos from audio + B-roll."""
    print("\n=== Step 3: Assemble Videos ===")

    for video in WHATIF_VIDEOS:
        slug = video["slug"]
        audio_path = os.path.join(WORK_DIR, f"{slug}.m4a")
        broll_dir = os.path.join(WORK_DIR, f"{slug}_broll")
        output_path = os.path.join(WORK_DIR, f"{slug}.mp4")
        video["output_path"] = output_path

        if not os.path.exists(audio_path):
            print(f"  SKIP {slug}: no audio file")
            continue

        broll_images = [f for f in os.listdir(broll_dir) if f.endswith(".png")] if os.path.isdir(broll_dir) else []
        if not broll_images:
            print(f"  SKIP {slug}: no B-roll images")
            continue

        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  SKIP {slug}: video already assembled ({size_mb:.1f} MB)")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would assemble: {slug} ({len(broll_images)} images + audio)")
            continue

        print(f"\n  Assembling {slug}...")
        # Use 30s segments for music videos (longer hold per image for visual comfort)
        ok, size_mb, duration = assemble_video(
            audio_path, broll_dir, output_path,
            segment_duration=30, crossfade=1.0, verbose=True,
        )
        if ok:
            print(f"  Done: {slug}.mp4 ({size_mb:.1f} MB, {duration/60:.1f} min)")
        else:
            print(f"  FAILED to assemble {slug}")


# ── Step 4: Upload new videos + unlist originals ───────────────────────────

def step_upload(access_token, dry_run=False):
    """Upload re-produced videos and unlist the originals."""
    print("\n=== Step 4: Upload New Videos + Unlist Originals ===")

    for video in WHATIF_VIDEOS:
        slug = video["slug"]
        output_path = os.path.join(WORK_DIR, f"{slug}.mp4")
        old_vid = video["old_video_id"]

        if not os.path.exists(output_path):
            print(f"  SKIP {slug}: no video file to upload")
            continue

        if dry_run:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  [DRY-RUN] Would upload: {slug}.mp4 ({size_mb:.1f} MB)")
            print(f"  [DRY-RUN] Would unlist original: {old_vid}")
            continue

        # Upload via resumable upload
        print(f"\n  Uploading {slug}...")
        new_vid = _upload_video(output_path, video, access_token)

        if new_vid:
            print(f"  Uploaded: https://youtube.com/watch?v={new_vid}")

            # Unlist the original
            if old_vid and old_vid != "FIND_VIA_SEARCH":
                print(f"  Unlisting original: {old_vid}")
                url = "https://www.googleapis.com/youtube/v3/videos?part=status"
                _api_call("PUT", url, access_token, payload={
                    "id": old_vid,
                    "status": {"privacyStatus": "unlisted"},
                }, label="unlist_old")
        else:
            print(f"  FAILED to upload {slug}")


def _upload_video(filepath, video_meta, access_token):
    """Upload a video via YouTube resumable upload. Returns video_id or None."""
    file_size = os.path.getsize(filepath)
    print(f"    File: {file_size / (1024*1024):.1f} MB")

    # Step 1: Initiate resumable upload
    init_url = (
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status"
    )
    body = {
        "snippet": {
            "title": video_meta["title"],
            "description": video_meta["description"],
            "tags": video_meta["tags"],
            "categoryId": "10",  # Music
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    import http.client
    import urllib.parse

    parsed = urllib.parse.urlparse(init_url)
    conn = http.client.HTTPSConnection(parsed.hostname)
    conn.request("POST", f"{parsed.path}?{parsed.query}",
                 body=json.dumps(body),
                 headers={
                     "Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Length": str(file_size),
                     "X-Upload-Content-Type": "video/mp4",
                 })
    resp = conn.getresponse()
    resp.read()

    if resp.status not in (200, 308):
        print(f"    Init failed: HTTP {resp.status}")
        return None

    upload_url = resp.getheader("Location")
    if not upload_url:
        print(f"    Init failed: no upload URL in response")
        return None

    # Step 2: Upload the file in one chunk (< 256MB typical)
    print(f"    Uploading...")
    with open(filepath, "rb") as f:
        file_data = f.read()

    parsed2 = urllib.parse.urlparse(upload_url)
    conn2 = http.client.HTTPSConnection(parsed2.hostname)
    path_query = f"{parsed2.path}?{parsed2.query}" if parsed2.query else parsed2.path
    conn2.request("PUT", path_query, body=file_data, headers={
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    })
    resp2 = conn2.getresponse()
    body2 = resp2.read().decode()

    if resp2.status == 200:
        data = json.loads(body2)
        return data.get("id")
    else:
        print(f"    Upload failed: HTTP {resp2.status}: {body2[:200]}")
        return None


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Re-produce What If videos with themed visuals")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--step", choices=["extract", "broll", "assemble", "upload"],
                        help="Run only a specific step")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN MODE]")

    print("Authenticating...")
    token = get_access_token()
    print("  OK\n")

    # Resolve video IDs
    print("Resolving video IDs...")
    resolve_video_ids(token)

    steps = [args.step] if args.step else ["extract", "broll", "assemble", "upload"]

    if "extract" in steps:
        step_extract(args.dry_run)

    if "broll" in steps:
        step_broll(args.dry_run)

    if "assemble" in steps:
        step_assemble(args.dry_run)

    if "upload" in steps:
        step_upload(token, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
