#!/usr/bin/env python3
"""List and unlist off-brand videos from the main Cumquat Vibes channel.

The main channel should only have:
- Product Shorts (Cumquat Vibes merch)
- Adobe Fresco tutorials
- Brand-relevant content (POD, design, coastal aesthetic)

Off-brand content (tech reviews, horror, psychology, pet tips, AI tutorials)
should be unlisted to maintain channel identity.
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")

MAIN_CHANNEL_ID = "UCThXDUhXqcui2HqBv4MUBBA"

# Off-brand keywords — videos containing these should be unlisted
OFF_BRAND_KEYWORDS = [
    "iphone", "tech gadget", "budget tech", "ai tool", "ai automation",
    "cat breed", "dog breed", "pet health", "dog is unhappy", "dog is secretly",
    "haunted place", "horror stor", "unsolved myster",
    "dark psychology", "manipulator", "overthinking", "body language",
    "lying to your face", "chatgpt", "prompt engineering",
    "pet health mistake", "cat breeds that act",
    "ai tools that will", "everyone is wrong about",
]

# Videos to KEEP (on-brand for Cumquat Vibes)
KEEP_KEYWORDS = [
    "fresco", "adobe", "cumquat", "tote bag", "design", "print on demand",
    "pod", "shopify", "etsy", "illustration", "drawing",
]


def refresh_token():
    """Refresh the OAuth access token."""
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    payload = json.dumps({
        "client_id": token_data["client_id"],
        "client_secret": token_data["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = Request(
        token_data["token_uri"],
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    token_data["token"] = data["access_token"]
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    return data["access_token"]


def list_channel_videos(access_token):
    """List all videos on the main channel."""
    videos = []
    page_token = ""

    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&channelId={MAIN_CHANNEL_ID}"
            f"&type=video&maxResults=50&order=date"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

        try:
            with urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
            print(f"API Error {e.code}: {err[:300]}")
            break

        for item in data.get("items", []):
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            published = item["snippet"]["publishedAt"]
            videos.append({
                "video_id": video_id,
                "title": title,
                "published": published,
            })

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    return videos


def is_off_brand(title):
    """Check if a video title is off-brand for Cumquat Vibes."""
    lower = title.lower()

    # Always keep on-brand content
    for kw in KEEP_KEYWORDS:
        if kw in lower:
            return False

    # Flag off-brand content
    for kw in OFF_BRAND_KEYWORDS:
        if kw in lower:
            return True

    return False


def unlist_video(video_id, access_token):
    """Set a video's privacy to unlisted."""
    # First get current video details
    url = f"https://www.googleapis.com/youtube/v3/videos?part=status&id={video_id}"
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Error getting video: {err[:200]}")
        return False

    if not data.get("items"):
        print(f"  Video {video_id} not found")
        return False

    # Update privacy to unlisted
    update_url = "https://www.googleapis.com/youtube/v3/videos?part=status"
    update_payload = json.dumps({
        "id": video_id,
        "status": {
            "privacyStatus": "unlisted",
        }
    }).encode("utf-8")

    req = Request(
        update_url,
        data=update_payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )

    try:
        with urlopen(req) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Error unlisting: {err[:200]}")
        return False


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"

    print("Cumquat Vibes (@CumquatVibes) — Channel Cleanup")
    print("=" * 60)

    access_token = refresh_token()
    print("Token refreshed.\n")

    print("Fetching all videos on main channel...")
    videos = list_channel_videos(access_token)
    print(f"Found {len(videos)} videos.\n")

    on_brand = []
    off_brand = []

    for v in videos:
        if is_off_brand(v["title"]):
            off_brand.append(v)
        else:
            on_brand.append(v)

    print(f"ON-BRAND ({len(on_brand)} videos — keeping):")
    for v in on_brand:
        print(f"  [KEEP] {v['title']}")

    print(f"\nOFF-BRAND ({len(off_brand)} videos — should unlist):")
    for v in off_brand:
        print(f"  [UNLIST] {v['title']} ({v['video_id']})")

    if mode == "unlist" and off_brand:
        print(f"\nUnlisting {len(off_brand)} off-brand videos...")
        unlisted = 0
        for v in off_brand:
            print(f"  Unlisting: {v['title']}...")
            if unlist_video(v["video_id"], access_token):
                print(f"    -> Unlisted!")
                unlisted += 1
            else:
                print(f"    -> FAILED")
        print(f"\nDone! Unlisted {unlisted}/{len(off_brand)} videos.")
    elif mode == "list":
        print(f"\nDry run — use 'python3 manage_main_channel.py unlist' to actually unlist.")
    else:
        print("\nNo off-brand videos found!")


if __name__ == "__main__":
    main()
