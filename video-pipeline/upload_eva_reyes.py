#!/usr/bin/env python3
"""Upload Eva Reyes videos to the Eva Reyes YouTube channel."""

import json
import os
import re
import time
import urllib.parse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "output", "videos")
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")

AMAZON_AFFILIATE_TAG = "richstudio0f-20"
AMAZON_STORE_ID = "7193294712"
EVA_CATEGORY = "22"


def refresh_channel_token(creds):
    """Refresh OAuth token for Eva Reyes channel."""
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urlopen(req).read())
    return resp["access_token"]


def make_title(filename):
    name = os.path.splitext(filename)[0]
    parts = name.split("_", 1)
    title_raw = parts[1] if len(parts) > 1 else name
    title = title_raw.replace("_", " ")
    words = title.split()
    result = []
    small_words = {"a", "an", "the", "and", "but", "or", "for", "in", "on", "at", "to", "of", "is", "it"}
    for i, word in enumerate(words):
        if word.isupper() and len(word) > 1:
            result.append(word)
        elif i == 0 or word.lower() not in small_words:
            result.append(word.capitalize())
        else:
            result.append(word.lower())
    return " ".join(result)


def extract_chapters(script_path):
    if not script_path or not os.path.exists(script_path):
        return []
    with open(script_path) as f:
        content = f.read()
    return re.findall(r'\[CHAPTER:\s*(.+?)\]', content)


def generate_timestamps(chapters, dur_min=10):
    if not chapters:
        return ""
    interval = (dur_min * 60) / max(len(chapters), 1)
    lines = []
    for i, ch in enumerate(chapters):
        total = int(i * interval)
        lines.append(f"{total // 60}:{total % 60:02d} {ch}")
    return "\n".join(lines)


def find_script(video_file):
    """Find matching script file for a video."""
    video_slug = os.path.splitext(video_file)[0]
    for sf in sorted(os.listdir(SCRIPTS_DIR)):
        if sf.startswith("EvaReyes") and sf.endswith(".txt"):
            script_slug = re.sub(r'_\d{8}_\d{6}\.txt$', '', sf)
            if video_slug == script_slug:
                return os.path.join(SCRIPTS_DIR, sf)
    return None


def make_description(script_path):
    chapters = extract_chapters(script_path)
    timestamps = generate_timestamps(chapters, 10)

    intro = ""
    if script_path and os.path.exists(script_path):
        with open(script_path) as f:
            content = f.read()
        for line in content.split("\n"):
            clean = re.sub(r'\[.*?\]', '', line).strip()
            clean = re.sub(r'\*\*.*?\*\*', '', clean).strip()
            clean = re.sub(r'^```.*$', '', clean).strip()
            if len(clean) > 50:
                intro = clean[:200]
                break

    parts = []
    if intro:
        parts.append(intro)
    parts.append("Discover tips on women's empowerment, confidence building, and self-improvement.")
    parts.append("")

    if timestamps:
        parts.extend([timestamps, ""])

    parts.extend([
        "---",
        "",
        "RECOMMENDED RESOURCES (affiliate links):",
        f"Shop our picks: https://www.amazon.com/shop/{AMAZON_STORE_ID}?tag={AMAZON_AFFILIATE_TAG}",
        "",
        "DISCLOSURE: Some links are affiliate links. As an Amazon Associate,",
        "I earn from qualifying purchases at no extra cost to you.",
        "",
        "---",
        "",
        "Like this? Subscribe and hit the bell for more empowering content!",
        "",
        "#WomensEmpowerment #Confidence #SelfImprovement #Motivation #EvaReyes #Inspiration",
    ])
    return "\n".join(parts)


def upload_video(video_path, title, description, tags, cat_id, token):
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": cat_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    meta_json = json.dumps(metadata).encode("utf-8")
    file_size = os.path.getsize(video_path)

    # Initiate resumable upload
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    init_req = Request(init_url, data=meta_json, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(file_size),
        "X-Upload-Content-Type": "video/mp4",
    }, method="POST")

    try:
        with urlopen(init_req) as resp:
            upload_url = resp.headers["Location"]
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Init Error {e.code}: {err[:300]}")
        if "uploadLimitExceeded" in err:
            return "rate_limited"
        return None

    # Upload video data
    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_req = Request(upload_url, data=video_data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "video/mp4",
        "Content-Length": str(file_size),
    }, method="PUT")

    try:
        with urlopen(upload_req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Upload Error {e.code}: {err[:300]}")
        if "uploadLimitExceeded" in err:
            return "rate_limited"
        return None


def main():
    print("Eva Reyes — YouTube Upload")
    print("=" * 50)

    # Find Eva Reyes videos
    eva_videos = sorted([
        f for f in os.listdir(VIDEOS_DIR)
        if f.startswith("EvaReyes") and f.endswith(".mp4")
    ])
    print(f"Found {len(eva_videos)} videos\n")

    # Refresh token
    with open(CHANNEL_TOKENS_PATH) as f:
        tokens = json.load(f)
    eva_creds = tokens["Eva Reyes"]
    access_token = refresh_channel_token(eva_creds)
    print("Token refreshed.")

    # Verify channel
    verify_url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
    vreq = Request(verify_url, headers={"Authorization": f"Bearer {access_token}"})
    vdata = json.loads(urlopen(vreq).read())
    if vdata.get("items"):
        ch = vdata["items"][0]
        print(f"Channel: {ch['snippet']['title']} ({ch['id']})\n")
    else:
        print("WARNING: Could not verify channel\n")

    eva_tags = [
        "womens empowerment", "confidence", "self improvement", "motivation",
        "strong women", "personal growth", "self care", "mindset", "inspiration",
        "empowerment", "women motivation 2026", "self worth", "confidence tips",
    ]

    results = []
    for i, vf in enumerate(eva_videos, 1):
        vpath = os.path.join(VIDEOS_DIR, vf)
        title = make_title(vf)
        script_path = find_script(vf)
        desc = make_description(script_path)
        size_mb = os.path.getsize(vpath) / (1024 * 1024)

        print(f"[{i}/{len(eva_videos)}] {title}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"  Script: {os.path.basename(script_path) if script_path else 'none'}")

        result = upload_video(vpath, title, desc, eva_tags, EVA_CATEGORY, access_token)

        if result == "rate_limited":
            print("  -> RATE LIMITED — YouTube daily upload limit reached")
            results.append({"file": vf, "status": "rate_limited"})
            print("  Stopping uploads (remaining videos will hit same limit)")
            break
        elif result and isinstance(result, dict):
            vid = result["id"]
            url = f"https://youtube.com/watch?v={vid}"
            print(f"  -> SUCCESS: {url}")
            results.append({"file": vf, "status": "success", "video_id": vid, "url": url})
        else:
            print("  -> FAILED")
            results.append({"file": vf, "status": "failed"})

        if i < len(eva_videos):
            time.sleep(5)

    print(f"\n{'=' * 50}")
    ok = sum(1 for r in results if r["status"] == "success")
    print(f"Upload Results: {ok}/{len(results)}")
    for r in results:
        print(f"  [{r['status']}] {r['file']}")
        if r.get("url"):
            print(f"    {r['url']}")


if __name__ == "__main__":
    main()
