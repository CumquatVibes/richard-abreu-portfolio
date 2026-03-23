#!/usr/bin/env python3
"""Add end-screen CTAs to YouTube video descriptions.

YouTube Data API v3 does NOT expose a public endScreens endpoint, so this
script takes an alternative approach: it appends a "Watch Next" section and
a subscribe link to every video description that doesn't already have one.

For each channel it:
  1. Refreshes the OAuth token
  2. Fetches all published videos
  3. Checks if the description already contains the CTA section
  4. If missing, appends a "Watch Next" block with the channel's latest video
     and a subscribe-confirmation link
  5. Optionally commits the update via videos.update
  6. Saves a JSON report to output/reports/end_screen_report.json

Usage:
    python add_end_screens.py --dry-run                    # Preview changes
    python add_end_screens.py --commit                     # Apply changes
    python add_end_screens.py --commit --channel RichTech  # One channel only
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "end_screen_report.json")
os.makedirs(REPORT_DIR, exist_ok=True)

# ── Channel configuration ─────────────────────────────────────────────────────

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

# YouTube handle for each channel — used in subscribe links
CHANNEL_HANDLES = {
    "RichTech": "@RichTech",
    "RichPets": "@RichPets",
    "RichHorror": "@RichHorror",
    "RichMind": "@RichMind",
    "HowToUseAI": "@HowToUseAI",
    "RichReviews": "@RichReviews",
    "RichGaming": "@RichGaming",
    "RichHistory": "@RichHistory",
    "RichNature": "@RichNature",
    "RichScience": "@RichScience",
    "RichFinance": "@RichFinance",
    "RichCrypto": "@RichCrypto",
    "RichMovie": "@RichMovie",
    "RichComedy": "@RichComedy",
    "RichSports": "@RichSports",
    "RichMusic": "@RichMusic",
    "RichTravel": "@RichTravel",
    "RichFood": "@RichFood",
    "RichFitness": "@RichFitness",
    "RichEducation": "@RichEducation",
    "RichLifestyle": "@RichLifestyle",
    "RichFashion": "@RichFashion",
    "RichBeauty": "@RichBeauty",
    "RichCooking": "@RichCooking",
    "RichFamily": "@RichFamily",
    "RichCars": "@RichCars",
    "RichDIY": "@RichDIY",
    "RichDesign": "@RichDesign",
    "RichPhotography": "@RichPhotography",
    "RichMemes": "@RichMemes",
    "RichAnimation": "@RichAnimation",
    "RichVlogging": "@RichVlogging",
    "RichKids": "@RichKids",
    "RichDance": "@RichDance",
    "EvaReyes": "@EvaReyes",
    "HowToMeditate": "@HowToMeditate",
    "RichBusiness": "@RichBusiness",
    "CumquatMotivation": "@CumquatMotivation",
    "CumquatVibes": "@CumquatVibes67",
    "CumquatGaming": "@CumquatGaming",
    "CumquatShortform": "@CumquatShortform",
    "RichArt": "@RichArt",
    "RichTraining": "@RichTraining",
}

# Marker used to detect whether the CTA block already exists
CTA_MARKER = "── WATCH NEXT ──"


# ── Helpers ────────────────────────────────────────────────────────────────────

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


def refresh_token(channel_name):
    """Refresh OAuth token for a channel."""
    with open(CHANNEL_TOKENS_PATH) as f:
        tokens = json.load(f)

    key = TOKEN_KEY_MAP.get(channel_name, channel_name)
    entry = tokens.get(key)
    if not entry:
        return None

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
        print(f"  Token refresh failed for {channel_name}: {err[:200]}")
        return None


# ── Core functions ─────────────────────────────────────────────────────────────

def fetch_all_videos(channel_id, access_token):
    """Fetch all videos from a channel's uploads playlist.

    Returns a list of video items with snippet data (including description,
    title, categoryId, etc.) needed for videos.update.
    """
    uploads_playlist = channel_id.replace("UC", "UU", 1)

    video_ids = []
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
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
        time.sleep(1)

    if not video_ids:
        return []

    # Fetch full snippet details in batches of 50
    all_videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        ids_str = ",".join(batch)
        url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet&id={ids_str}"
        )
        details = _api_call("GET", url, access_token, label="details")
        if details and "items" in details:
            all_videos.extend(details["items"])
        time.sleep(1)

    return all_videos


def has_cta_section(description):
    """Return True if the description already contains our CTA block."""
    return CTA_MARKER in description


def find_latest_video_url(videos, exclude_video_id=None):
    """Return the YouTube URL of the most-recently-published video.

    Videos are assumed to be sorted newest-first (YouTube default).
    If *exclude_video_id* is given, skip that video (so we don't link a
    video to itself).
    """
    for v in videos:
        vid = v["id"]
        if vid != exclude_video_id:
            return f"https://youtu.be/{vid}"
    return None


def build_cta_block(channel_name, latest_video_url):
    """Build the CTA text block to append to a description."""
    handle = CHANNEL_HANDLES.get(channel_name, f"@{channel_name}")
    subscribe_url = f"https://www.youtube.com/{handle}?sub_confirmation=1"

    lines = [
        "",
        f"─── {CTA_MARKER} ───",
    ]
    if latest_video_url:
        lines.append(f"▶ Watch Next: {latest_video_url}")
    lines.extend([
        f"🔔 Subscribe: {subscribe_url}",
        "",
    ])
    return "\n".join(lines)


def update_video_description(video_item, new_description, access_token):
    """Push an updated description via videos.update (snippet)."""
    snippet = video_item["snippet"]
    url = "https://www.googleapis.com/youtube/v3/videos?part=snippet"
    payload = {
        "id": video_item["id"],
        "snippet": {
            "title": snippet["title"],
            "description": new_description,
            "categoryId": snippet.get("categoryId", "22"),
        },
    }
    return _api_call("PUT", url, access_token, payload=payload, label="update")


# ── Per-channel processing ─────────────────────────────────────────────────────

def process_channel(channel_name, dry_run=True):
    """Process a single channel: fetch videos, append CTAs where missing.

    Returns a dict with stats for the report.
    """
    channel_id, category_id = CHANNEL_MAP[channel_name]
    print(f"\n{'='*60}")
    print(f"Channel: {channel_name}  (dry_run={dry_run})")
    print(f"{'='*60}")

    access_token = refresh_token(channel_name)
    if not access_token:
        print(f"  SKIP — could not refresh token for {channel_name}")
        return {"channel": channel_name, "status": "token_error", "updated": 0, "skipped": 0}

    videos = fetch_all_videos(channel_id, access_token)
    print(f"  Found {len(videos)} videos")

    if not videos:
        return {"channel": channel_name, "status": "no_videos", "updated": 0, "skipped": 0}

    latest_url = find_latest_video_url(videos)
    updated = 0
    skipped = 0
    details = []

    for video in videos:
        vid = video["id"]
        title = video["snippet"]["title"]
        description = video["snippet"].get("description", "")

        if has_cta_section(description):
            skipped += 1
            continue

        # Don't link a video to itself — pick the next best
        watch_next = find_latest_video_url(videos, exclude_video_id=vid)
        cta = build_cta_block(channel_name, watch_next)
        new_description = description + cta

        # YouTube description limit is 5000 characters
        if len(new_description) > 5000:
            print(f"  SKIP (too long): {title[:60]}")
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would update: {title[:60]}")
            details.append({"video_id": vid, "title": title, "action": "would_update"})
        else:
            print(f"  Updating: {title[:60]}")
            result = update_video_description(video, new_description, access_token)
            if result:
                details.append({"video_id": vid, "title": title, "action": "updated"})
            else:
                details.append({"video_id": vid, "title": title, "action": "failed"})
            time.sleep(1)  # rate limit: 1 req/sec

        updated += 1

    status = "dry_run" if dry_run else "committed"
    print(f"  Done — updated: {updated}, skipped (already has CTA): {skipped}")

    return {
        "channel": channel_name,
        "status": status,
        "total_videos": len(videos),
        "updated": updated,
        "skipped": skipped,
        "details": details,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Add end-screen CTAs to YouTube video descriptions."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    mode.add_argument("--commit", action="store_true", help="Apply description updates")
    parser.add_argument("--channel", type=str, default=None, help="Process a single channel")
    args = parser.parse_args()

    dry_run = args.dry_run

    if args.channel:
        if args.channel not in CHANNEL_MAP:
            print(f"Unknown channel: {args.channel}")
            print(f"Available: {', '.join(sorted(CHANNEL_MAP))}")
            sys.exit(1)
        channels = [args.channel]
    else:
        channels = list(CHANNEL_MAP.keys())

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run" if dry_run else "commit",
        "channels": [],
    }

    for ch in channels:
        result = process_channel(ch, dry_run=dry_run)
        report["channels"].append(result)

    # Save report
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {REPORT_PATH}")

    total_updated = sum(c.get("updated", 0) for c in report["channels"])
    total_skipped = sum(c.get("skipped", 0) for c in report["channels"])
    print(f"Total — updated: {total_updated}, skipped: {total_skipped}")


if __name__ == "__main__":
    main()
