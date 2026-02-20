#!/usr/bin/env python3
"""List all long-form videos (not Shorts) on the main channel to find off-brand content."""

import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")

# Uploads playlist = channel ID with UC -> UU
UPLOADS_PLAYLIST = "UUThXDUhXqcui2HqBv4MUBBA"


def get_token():
    with open(TOKEN_PATH) as f:
        return json.load(f)["token"]


def list_uploads(access_token):
    """List ALL videos using playlistItems (more reliable than search)."""
    videos = []
    page_token = ""

    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/playlistItems"
            f"?part=snippet,contentDetails,status"
            f"&playlistId={UPLOADS_PLAYLIST}"
            f"&maxResults=50"
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
            video_id = item["contentDetails"]["videoId"]
            title = item["snippet"]["title"]
            published = item["snippet"]["publishedAt"]
            privacy = item.get("status", {}).get("privacyStatus", "unknown")
            videos.append({
                "video_id": video_id,
                "title": title,
                "published": published,
                "privacy": privacy,
            })

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    return videos


def main():
    access_token = get_token()
    print("Fetching ALL uploads on main channel...\n")

    videos = list_uploads(access_token)
    print(f"Total uploads: {len(videos)}\n")

    # Separate long-form from Shorts (Shorts titles are usually product names)
    # Look for off-brand content specifically
    off_brand_terms = [
        "iphone", "tech gadget", "budget tech", "ai tool", "ai automation",
        "cat breed", "dog breed", "pet health", "dog is unhappy", "dog is secretly",
        "haunted place", "horror stor", "unsolved myster", "dark psychology",
        "manipulator", "overthinking", "body language", "lying to your face",
        "chatgpt", "prompt engineering", "pet health mistake",
        "cat breeds that act", "ai tools that will", "everyone is wrong",
        "maybe she's born", "empowerment", "toxic habit", "confidence as a woman",
    ]

    print("=== POTENTIAL OFF-BRAND VIDEOS ===")
    found = 0
    for v in videos:
        lower = v["title"].lower()
        for term in off_brand_terms:
            if term in lower:
                found += 1
                print(f"  [{v['privacy']}] {v['title']}")
                print(f"    ID: {v['video_id']} | Published: {v['published'][:10]}")
                break

    if not found:
        print("  None found with keyword matching.\n")

    # Also print the most recent 20 videos to manually inspect
    print(f"\n=== 20 MOST RECENT UPLOADS ===")
    for v in videos[:20]:
        print(f"  [{v['privacy']}] {v['title']}")
        print(f"    ID: {v['video_id']} | {v['published'][:10]}")


if __name__ == "__main__":
    main()
