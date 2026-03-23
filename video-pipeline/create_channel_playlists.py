#!/usr/bin/env python3
"""Create YouTube playlists for all channels and add existing videos.

Iterates over CHANNEL_MAP, refreshes OAuth tokens, checks for existing playlists,
creates missing ones, adds published videos, and updates CHANNEL_PLAYLISTS in
upload_to_youtube.py.

Usage:
    python create_channel_playlists.py                    # Run all channels
    python create_channel_playlists.py --channel RichTech # Single channel
    python create_channel_playlists.py --dry-run          # Preview only
    python create_channel_playlists.py --commit           # Also update upload_to_youtube.py
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
UPLOAD_SCRIPT_PATH = os.path.join(BASE_DIR, "upload_to_youtube.py")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "playlist_creation_report.json")

os.makedirs(REPORT_DIR, exist_ok=True)

# ── Channel configuration ──────────────────────────────────────────────────

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

# Where the token key in channel_tokens.json differs from the channel prefix
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

# Niche descriptions for each channel — used in playlist titles/descriptions
CHANNEL_NICHE = {
    "RichTech": "Tech & AI Tools",
    "RichPets": "Pet Care & Animal Facts",
    "RichHorror": "Horror Stories & Creepy Tales",
    "RichMind": "Psychology & Self-Improvement",
    "HowToUseAI": "AI Tutorials & Prompting",
    "RichReviews": "Honest Product Reviews",
    "RichGaming": "Gaming Tips & Gameplay",
    "RichHistory": "History Deep Dives",
    "RichNature": "Nature & Wildlife",
    "RichScience": "Science Explained",
    "RichFinance": "Personal Finance & Investing",
    "RichCrypto": "Crypto & Web3",
    "RichMovie": "Movie Reviews & Analysis",
    "RichComedy": "Comedy & Funny Takes",
    "RichSports": "Sports Highlights & Analysis",
    "RichMusic": "Music Reimagined & Study Beats",
    "RichTravel": "Travel Guides & Adventures",
    "RichFood": "Food Reviews & Recipes",
    "RichFitness": "Fitness & Workout Tips",
    "RichEducation": "Education & Learning",
    "RichLifestyle": "Lifestyle & Daily Vlogs",
    "RichFashion": "Fashion & Style Tips",
    "RichBeauty": "Beauty & Skincare",
    "RichCooking": "Cooking Tutorials & Recipes",
    "RichFamily": "Family & Parenting",
    "RichCars": "Cars & Automotive",
    "RichDIY": "DIY Projects & Crafts",
    "RichDesign": "Design & Creative Tools",
    "RichPhotography": "Photography Tips & Edits",
    "RichMemes": "Memes & Internet Culture",
    "RichAnimation": "Animation & Motion Graphics",
    "RichVlogging": "Vlogs & Behind the Scenes",
    "RichKids": "Kids Entertainment & Learning",
    "RichDance": "Dance & Choreography",
    "EvaReyes": "Lifestyle & Motivation",
    "HowToMeditate": "Meditation & Mindfulness",
    "RichBusiness": "Business & Entrepreneurship",
    "CumquatMotivation": "Motivation & Mindset",
    "CumquatVibes": "Vibes & Chill Content",
    "CumquatGaming": "Gaming & Let's Plays",
    "CumquatShortform": "Shorts & Quick Takes",
    "RichArt": "Art Showcases & Tutorials",
    "RichTraining": "Training & Skill Building",
}

# Channels that should get a second niche-specific playlist (those with enough content variety)
CHANNELS_WITH_NICHE_PLAYLIST = {
    "RichTech", "RichPets", "RichHorror", "RichMind", "HowToUseAI",
    "RichReviews", "RichGaming", "RichHistory", "RichScience",
    "RichFinance", "RichCrypto", "RichMovie", "RichMusic",
    "RichFood", "RichFitness", "RichCooking", "RichBusiness",
    "RichDesign", "RichPhotography", "RichArt", "RichTraining",
    "CumquatMotivation", "CumquatGaming",
}


# ── Auth ────────────────────────────────────────────────────────────────────

def get_access_token(channel_name):
    """Refresh OAuth token for a given channel."""
    with open(CHANNEL_TOKENS_PATH) as f:
        tokens = json.load(f)

    token_key = TOKEN_KEY_MAP.get(channel_name, channel_name)
    entry = tokens.get(token_key)
    if not entry:
        return None, f"No token entry for '{token_key}' in channel_tokens.json"

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
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data["access_token"], None
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        return None, f"Token refresh failed: {err[:300]}"
    except Exception as e:
        return None, f"Token refresh error: {str(e)[:300]}"


# ── YouTube API helpers ─────────────────────────────────────────────────────

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
            return json.loads(resp.read().decode()), None
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, "read") else str(e)
        return None, f"[{label}] HTTP {e.code}: {err[:300]}"
    except Exception as e:
        return None, f"[{label}] Error: {str(e)[:300]}"


def list_existing_playlists(access_token, channel_id):
    """Fetch all playlists owned by the authenticated channel."""
    playlists = []
    page_token = ""

    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/playlists"
            f"?part=snippet,status&mine=true&maxResults=50"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        data, err = _api_call("GET", url, access_token, label="playlists.list")
        if err:
            return None, err
        if not data:
            return [], None

        for item in data.get("items", []):
            playlists.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
                "privacy": item["status"].get("privacyStatus", "public"),
                "item_count": item.get("contentDetails", {}).get("itemCount", 0),
            })

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
        time.sleep(1)

    return playlists, None


def create_playlist(access_token, title, description, privacy="public"):
    """Create a new playlist via playlists.insert."""
    url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"
    payload = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {
            "privacyStatus": privacy,
        },
    }

    data, err = _api_call("POST", url, access_token, payload=payload, label="playlists.insert")
    if err:
        return None, err
    if data and "id" in data:
        return data["id"], None
    return None, "No playlist ID returned"


def get_channel_videos(access_token, channel_id):
    """Get all public videos for a channel via uploads playlist."""
    uploads_playlist = channel_id.replace("UC", "UU", 1)
    videos = []
    page_token = ""

    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/playlistItems"
            f"?part=contentDetails,snippet&playlistId={uploads_playlist}"
            f"&maxResults=50"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        data, err = _api_call("GET", url, access_token, label="uploads.list")
        if err:
            # Might be empty channel
            if "404" in str(err):
                break
            return None, err
        if not data:
            break

        for item in data.get("items", []):
            videos.append({
                "video_id": item["contentDetails"]["videoId"],
                "title": item["snippet"].get("title", ""),
                "published_at": item["snippet"].get("publishedAt", ""),
            })

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
        time.sleep(1)

    return videos, None


def add_video_to_playlist(access_token, playlist_id, video_id):
    """Add a video to a playlist via playlistItems.insert."""
    url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
    payload = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        },
    }

    data, err = _api_call("POST", url, access_token, payload=payload, label="playlistItems.insert")
    if err:
        # Duplicate or already in playlist — not fatal
        if "409" in str(err) or "duplicate" in str(err).lower():
            return True, "already in playlist"
        return False, err
    return True, None


# ── Playlist naming ─────────────────────────────────────────────────────────

def get_display_name(channel_name):
    """Get a human-readable display name for the channel."""
    # Use TOKEN_KEY_MAP if it has a nicer name, otherwise split CamelCase
    if channel_name in TOKEN_KEY_MAP:
        return TOKEN_KEY_MAP[channel_name]
    # Insert spaces before capitals: "RichTech" -> "Rich Tech"
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", channel_name)


def get_playlist_configs(channel_name):
    """Return list of (title, description) tuples for playlists to create."""
    display = get_display_name(channel_name)
    niche = CHANNEL_NICHE.get(channel_name, "Best Content")

    playlists = []

    # Main "Best of 2026" playlist for every channel
    main_title = f"{display} \u2014 Best of 2026"
    main_desc = (
        f"The best videos from {display} in 2026. "
        f"Curated highlights covering {niche.lower()}. "
        f"Subscribe for more!"
    )
    playlists.append((main_title, main_desc))

    # Second niche-specific playlist for qualifying channels
    if channel_name in CHANNELS_WITH_NICHE_PLAYLIST:
        niche_title = f"{niche} | {display}"
        niche_desc = (
            f"All {niche.lower()} videos from {display}. "
            f"Deep dives, tutorials, and more."
        )
        playlists.append((niche_title, niche_desc))

    return playlists


def playlist_matches_convention(existing_title, channel_name):
    """Check if an existing playlist title matches our naming convention."""
    display = get_display_name(channel_name)
    niche = CHANNEL_NICHE.get(channel_name, "")

    checks = [
        f"{display} \u2014 Best of 2026",
        f"{niche} | {display}" if niche else None,
    ]
    for check in checks:
        if check and existing_title.strip() == check.strip():
            return True
    return False


# ── Core logic ──────────────────────────────────────────────────────────────

def process_channel(channel_name, channel_id, dry_run=False):
    """Process a single channel: check playlists, create missing ones, add videos.

    Returns a dict with results for the report.
    """
    result = {
        "channel": channel_name,
        "channel_id": channel_id,
        "status": "ok",
        "existing_playlists": [],
        "created_playlists": [],
        "videos_added": 0,
        "errors": [],
        "primary_playlist_id": None,
    }

    print(f"\n{'='*60}")
    print(f"  {channel_name} ({channel_id})")
    print(f"{'='*60}")

    # 1. Authenticate
    print(f"  Authenticating...")
    access_token, err = get_access_token(channel_name)
    if err:
        print(f"  ERROR: {err}")
        result["status"] = "auth_failed"
        result["errors"].append(err)
        return result
    print(f"  Authenticated.")
    time.sleep(1)

    # 2. List existing playlists
    print(f"  Checking existing playlists...")
    existing, err = list_existing_playlists(access_token, channel_id)
    if err:
        print(f"  WARNING: Could not list playlists: {err}")
        result["errors"].append(f"list_playlists: {err}")
        existing = []
    else:
        for pl in existing:
            print(f"    Found: \"{pl['title']}\" ({pl['id']})")
            result["existing_playlists"].append({"id": pl["id"], "title": pl["title"]})
    time.sleep(1)

    existing_titles = {pl["title"] for pl in (existing or [])}
    existing_id_map = {pl["title"]: pl["id"] for pl in (existing or [])}

    # 3. Determine which playlists to create
    desired = get_playlist_configs(channel_name)
    primary_playlist_id = None

    for i, (title, description) in enumerate(desired):
        if title in existing_titles:
            print(f"  Playlist already exists: \"{title}\"")
            pid = existing_id_map[title]
            if i == 0:
                primary_playlist_id = pid
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create: \"{title}\"")
            result["created_playlists"].append({"id": "DRY_RUN", "title": title})
            continue

        print(f"  Creating playlist: \"{title}\"...")
        pid, err = create_playlist(access_token, title, description, privacy="public")
        if err:
            print(f"    ERROR: {err}")
            result["errors"].append(f"create '{title}': {err}")
            # Check for quota exhaustion
            if "quota" in str(err).lower() or "429" in str(err):
                result["status"] = "quota"
                return result
        else:
            print(f"    Created: {pid}")
            result["created_playlists"].append({"id": pid, "title": title})
            if i == 0:
                primary_playlist_id = pid
        time.sleep(1)

    # If we found the primary playlist from existing but didn't create one
    if not primary_playlist_id:
        # Try to find it from existing
        main_title = desired[0][0] if desired else None
        if main_title and main_title in existing_id_map:
            primary_playlist_id = existing_id_map[main_title]
        elif existing:
            # Fall back to first existing playlist
            primary_playlist_id = existing[0]["id"]

    result["primary_playlist_id"] = primary_playlist_id

    # 4. Get channel videos and add them to the primary playlist
    if primary_playlist_id and not dry_run:
        print(f"  Fetching channel videos...")
        videos, err = get_channel_videos(access_token, channel_id)
        if err:
            print(f"    WARNING: Could not list videos: {err}")
            result["errors"].append(f"list_videos: {err}")
        elif videos:
            print(f"    Found {len(videos)} videos. Adding to playlist {primary_playlist_id}...")
            added = 0
            for v in videos:
                ok, add_err = add_video_to_playlist(access_token, primary_playlist_id, v["video_id"])
                if ok:
                    if add_err == "already in playlist":
                        pass  # Silent skip
                    else:
                        added += 1
                        print(f"      Added: {v['title'][:50]}")
                else:
                    # Quota or other fatal error
                    if "quota" in str(add_err).lower() or "429" in str(add_err):
                        print(f"    QUOTA HIT — stopping video additions.")
                        result["errors"].append("quota hit during video additions")
                        result["status"] = "quota"
                        break
                    print(f"      Failed: {v['title'][:50]} — {add_err}")
                time.sleep(1)
            result["videos_added"] = added
            print(f"    Added {added} videos to playlist.")
        else:
            print(f"    No videos found on channel.")
    elif dry_run and primary_playlist_id != "DRY_RUN":
        print(f"  [DRY-RUN] Would add existing videos to playlist {primary_playlist_id or '(new)'}")

    return result


# ── Update upload_to_youtube.py ─────────────────────────────────────────────

def update_channel_playlists_in_script(playlist_map):
    """Rewrite the CHANNEL_PLAYLISTS = {} line in upload_to_youtube.py with real IDs.

    playlist_map: dict of channel_name -> playlist_id
    """
    if not playlist_map:
        print("\nNo playlist IDs to write.")
        return False

    if not os.path.exists(UPLOAD_SCRIPT_PATH):
        print(f"\nWARNING: {UPLOAD_SCRIPT_PATH} not found — skipping update.")
        return False

    with open(UPLOAD_SCRIPT_PATH, "r") as f:
        content = f.read()

    # Build the replacement dict string
    lines = ["CHANNEL_PLAYLISTS = {"]
    for ch, pid in sorted(playlist_map.items()):
        lines.append(f'    "{ch}": "{pid}",')
    lines.append("}")
    new_block = "\n".join(lines)

    # Match the existing CHANNEL_PLAYLISTS = { ... } block
    # It could be a single-line `CHANNEL_PLAYLISTS = {}` or a multi-line dict
    pattern = r"CHANNEL_PLAYLISTS\s*=\s*\{[^}]*\}"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print(f"\nWARNING: Could not find CHANNEL_PLAYLISTS in {UPLOAD_SCRIPT_PATH}")
        return False

    new_content = content[:match.start()] + new_block + content[match.end():]

    with open(UPLOAD_SCRIPT_PATH, "w") as f:
        f.write(new_content)

    print(f"\nUpdated CHANNEL_PLAYLISTS in {UPLOAD_SCRIPT_PATH} with {len(playlist_map)} entries.")
    return True


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create YouTube playlists for all channels and add existing videos."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview actions without making API calls")
    parser.add_argument("--channel", type=str, default=None,
                        help="Process only this channel (e.g. RichTech)")
    parser.add_argument("--commit", action="store_true",
                        help="Update CHANNEL_PLAYLISTS in upload_to_youtube.py")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN MODE — no API writes]\n")

    # Validate channel filter
    if args.channel and args.channel not in CHANNEL_MAP:
        print(f"ERROR: Unknown channel '{args.channel}'")
        print(f"Available: {', '.join(sorted(CHANNEL_MAP.keys()))}")
        sys.exit(1)

    channels_to_process = (
        {args.channel: CHANNEL_MAP[args.channel]}
        if args.channel
        else CHANNEL_MAP
    )

    print(f"Processing {len(channels_to_process)} channel(s)...\n")

    results = []
    all_playlist_ids = {}  # channel_name -> primary_playlist_id
    quota_hit = False

    for channel_name, (channel_id, _cat_id) in channels_to_process.items():
        if quota_hit:
            print(f"\n  SKIPPING {channel_name} — quota exhausted.")
            results.append({
                "channel": channel_name,
                "status": "skipped_quota",
            })
            continue

        result = process_channel(channel_name, channel_id, dry_run=args.dry_run)
        results.append(result)

        if result.get("primary_playlist_id") and result["primary_playlist_id"] != "DRY_RUN":
            all_playlist_ids[channel_name] = result["primary_playlist_id"]

        if result.get("status") == "quota":
            quota_hit = True
            print("\n*** QUOTA EXHAUSTED — stopping further channels ***")

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    auth_fail = sum(1 for r in results if r.get("status") == "auth_failed")
    quota_count = sum(1 for r in results if r.get("status") in ("quota", "skipped_quota"))
    created_total = sum(len(r.get("created_playlists", [])) for r in results)
    videos_total = sum(r.get("videos_added", 0) for r in results)

    print(f"  Channels processed:  {ok_count}")
    print(f"  Auth failures:       {auth_fail}")
    print(f"  Quota issues:        {quota_count}")
    print(f"  Playlists created:   {created_total}")
    print(f"  Videos added:        {videos_total}")
    print(f"  Playlist IDs found:  {len(all_playlist_ids)}")

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "channels_processed": len(results),
        "playlists_created": created_total,
        "videos_added": videos_total,
        "playlist_ids": all_playlist_ids,
        "details": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to: {REPORT_PATH}")

    # Update upload_to_youtube.py if --commit
    if args.commit and all_playlist_ids:
        if args.dry_run:
            print("\n  [DRY-RUN] Would update CHANNEL_PLAYLISTS in upload_to_youtube.py")
        else:
            update_channel_playlists_in_script(all_playlist_ids)
    elif args.commit and not all_playlist_ids:
        print("\n  No playlist IDs collected — nothing to commit.")
    elif all_playlist_ids and not args.commit:
        print(f"\n  Tip: Run with --commit to update upload_to_youtube.py automatically.")

    print("\nDone.")


if __name__ == "__main__":
    main()
