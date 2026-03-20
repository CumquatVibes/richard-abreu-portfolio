#!/usr/bin/env python3
"""Bulk SEO metadata fixer for all YouTube channels.

Fetches all published videos, analyzes titles/tags/descriptions against SEO
benchmarks, and optionally updates them via YouTube API.

Uses Gemini to generate optimized titles and descriptions when needed.

Usage:
    python bulk_fix_seo_metadata.py --dry-run                    # Audit only
    python bulk_fix_seo_metadata.py --dry-run --channel RichTech  # Audit one channel
    python bulk_fix_seo_metadata.py --commit                      # Apply fixes
    python bulk_fix_seo_metadata.py --commit --channel EvaReyes   # Fix one channel
    python bulk_fix_seo_metadata.py --report                      # Generate JSON report
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# Load Gemini key
from dotenv import load_dotenv
ENV_PATH = os.path.join(os.path.dirname(BASE_DIR), "shopify-theme", ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Channel map from upload_to_youtube.py
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

POWER_WORDS = {
    "secret", "truth", "proven", "shocking", "ultimate", "insane", "brutal",
    "hidden", "deadly", "genius", "epic", "unbelievable", "guaranteed",
    "devastating", "legendary", "incredible", "powerful", "essential",
    "critical", "explosive", "terrifying", "mysterious", "stunning",
    "mind-blowing", "game-changing", "life-changing", "unstoppable",
}

# Channels where we should NOT rewrite titles (music/art have special formats)
SKIP_TITLE_REWRITE = {"RichMusic", "RichArt"}


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


def fetch_all_videos(channel_id, access_token):
    """Fetch all videos from a channel's uploads playlist."""
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

    if not video_ids:
        return []

    # Fetch full details in batches of 50
    all_videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        ids_str = ",".join(batch)
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id={ids_str}"
        details = _api_call("GET", url, access_token, label="details")
        if details and "items" in details:
            all_videos.extend(details["items"])
        time.sleep(0.5)

    return all_videos


def analyze_seo(video_item):
    """Analyze a video's SEO and return list of issues."""
    snippet = video_item["snippet"]
    title = snippet.get("title", "")
    description = snippet.get("description", "")
    tags = snippet.get("tags", [])

    issues = []

    # Power words
    title_lower = title.lower()
    if not any(pw in title_lower for pw in POWER_WORDS):
        issues.append("no_power_words")

    # Numbers in title
    if not re.search(r'\d', title):
        issues.append("no_numbers")

    # Title length
    if len(title) < 30:
        issues.append("title_too_short")
    elif len(title) > 80:
        issues.append("title_too_long")

    # Tags
    if len(tags) < 8:
        issues.append(f"low_tags_{len(tags)}")

    # Description length
    if len(description) < 200:
        issues.append("short_description")

    # Hashtags
    if "#" not in description:
        issues.append("no_hashtags")

    return issues


def gemini_optimize_title(current_title, channel_niche):
    """Use Gemini to generate an SEO-optimized title."""
    if not GEMINI_API_KEY:
        return None

    prompt = f"""Rewrite this YouTube video title for maximum CTR and SEO:

Current title: "{current_title}"
Channel niche: {channel_niche}

Rules:
- Include at least ONE number (Top 5, 7 Signs, 3 Secrets, etc.)
- Include at least ONE power word: SECRET, TRUTH, PROVEN, SHOCKING, ULTIMATE, HIDDEN, GENIUS, EPIC, INCREDIBLE, ESSENTIAL
- Keep it 40-70 characters
- Front-load the primary keyword
- Don't change the topic/meaning
- Don't use all caps except for the power word
- Return ONLY the new title, nothing else."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 100}
    }).encode()

    try:
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"')
        if 30 <= len(text) <= 100:
            return text
    except Exception as e:
        print(f"    Gemini error: {str(e)[:80]}")
    return None


def gemini_generate_tags(title, current_tags, channel_niche):
    """Use Gemini to generate SEO-optimized tags."""
    if not GEMINI_API_KEY:
        return None

    prompt = f"""Generate 15 YouTube SEO tags for this video:

Title: "{title}"
Channel niche: {channel_niche}
Current tags: {', '.join(current_tags[:5])}

Rules:
- Mix short-tail (1-2 words) and long-tail (3-5 words) keywords
- Include the year "2026" in at least one tag
- Include variations of the main topic
- No generic filler tags like "faceless youtube" or "ai narration"
- Return ONLY comma-separated tags, nothing else."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 200}
    }).encode()

    try:
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        tags = [t.strip().strip('"') for t in text.split(",") if t.strip()]
        if len(tags) >= 8:
            return tags[:20]
    except Exception as e:
        print(f"    Gemini error: {str(e)[:80]}")
    return None


# Channel niche descriptions for Gemini prompts
CHANNEL_NICHE = {
    "RichTech": "tech gadgets and AI tools",
    "RichPets": "pet care and animal facts",
    "RichHorror": "horror stories and creepy facts",
    "RichMind": "psychology and self-improvement",
    "HowToUseAI": "AI tutorials and tools",
    "RichReviews": "product reviews",
    "RichGaming": "gaming news and reviews",
    "RichHistory": "history documentaries",
    "RichNature": "nature and wildlife",
    "RichScience": "science explainers",
    "RichFinance": "personal finance and investing",
    "RichCrypto": "cryptocurrency and blockchain",
    "RichMovie": "movie reviews and analysis",
    "RichComedy": "comedy and humor",
    "RichSports": "sports news and highlights",
    "RichMusic": "ambient/study music playlists",
    "RichTravel": "travel destinations and guides",
    "RichFood": "food and restaurants",
    "RichFitness": "fitness and workouts",
    "RichEducation": "education and learning",
    "RichLifestyle": "lifestyle tips",
    "RichFashion": "fashion trends",
    "RichBeauty": "beauty and skincare",
    "RichCooking": "cooking recipes and tutorials",
    "RichFamily": "family and parenting",
    "RichCars": "cars and automotive",
    "RichDIY": "DIY projects and crafts",
    "RichDesign": "graphic design and creativity",
    "RichPhotography": "photography tips and techniques",
    "RichMemes": "memes and internet culture",
    "RichAnimation": "animation and cartoons",
    "RichVlogging": "daily vlogs and lifestyle",
    "RichKids": "kids entertainment and education",
    "RichDance": "dance and music",
    "EvaReyes": "women's empowerment and lifestyle",
    "HowToMeditate": "meditation and mindfulness",
    "RichBusiness": "business and entrepreneurship",
    "CumquatMotivation": "motivation and stoic philosophy",
    "CumquatVibes": "creator tools and digital art",
    "CumquatGaming": "gaming indie reviews",
    "CumquatShortform": "viral facts and quick content",
    "RichArt": "4K art slideshows",
    "RichTraining": "military training and discipline",
}


def process_channel(channel_name, channel_id, category_id, dry_run=True, report_only=False):
    """Process all videos for a single channel."""
    print(f"\n{'='*60}")
    print(f"  {channel_name} ({channel_id})")
    print(f"{'='*60}")

    access_token = refresh_token(channel_name)
    if not access_token:
        print(f"  SKIP: Could not get token for {channel_name}")
        return {"channel": channel_name, "status": "token_failed", "videos": []}

    videos = fetch_all_videos(channel_id, access_token)
    if not videos:
        print(f"  No videos found.")
        return {"channel": channel_name, "status": "no_videos", "videos": []}

    print(f"  Found {len(videos)} videos")

    results = []
    updated = 0
    gemini_calls = 0

    for video in videos:
        vid = video["id"]
        snippet = video["snippet"]
        title = snippet.get("title", "")
        tags = snippet.get("tags", [])
        description = snippet.get("description", "")
        cat_id = snippet.get("categoryId", category_id)

        issues = analyze_seo(video)
        if not issues:
            results.append({"video_id": vid, "title": title, "issues": [], "action": "ok"})
            continue

        result_entry = {
            "video_id": vid,
            "title": title,
            "issues": issues,
            "action": "needs_fix",
        }

        if report_only:
            results.append(result_entry)
            continue

        niche = CHANNEL_NICHE.get(channel_name, "general content")
        new_title = title
        new_tags = tags
        needs_update = False

        # Fix title (power words + numbers)
        if channel_name not in SKIP_TITLE_REWRITE and (
            "no_power_words" in issues or "no_numbers" in issues
        ):
            optimized = gemini_optimize_title(title, niche)
            gemini_calls += 1
            time.sleep(1)  # Rate limit Gemini
            if optimized and optimized != title:
                new_title = optimized
                needs_update = True
                result_entry["new_title"] = new_title
                print(f"  Title: {title[:50]}")
                print(f"      -> {new_title[:50]}")

        # Fix tags
        if any("low_tags" in i for i in issues):
            gen_tags = gemini_generate_tags(new_title, tags, niche)
            gemini_calls += 1
            time.sleep(1)
            if gen_tags:
                # Merge: keep existing + add new ones
                seen = {t.lower() for t in tags}
                merged = list(tags)
                for t in gen_tags:
                    if t.lower() not in seen:
                        merged.append(t)
                        seen.add(t.lower())
                # Cap at 490 chars
                capped = []
                total = 0
                for t in merged:
                    if total + len(t) + 1 > 490:
                        break
                    capped.append(t)
                    total += len(t) + 1
                if len(capped) > len(tags):
                    new_tags = capped
                    needs_update = True
                    result_entry["new_tag_count"] = len(new_tags)
                    print(f"  Tags: {len(tags)} -> {len(new_tags)}")

        if not needs_update:
            result_entry["action"] = "no_improvement_found"
            results.append(result_entry)
            continue

        if dry_run:
            result_entry["action"] = "would_update"
            results.append(result_entry)
            updated += 1
            continue

        # Apply update
        update_url = "https://www.googleapis.com/youtube/v3/videos?part=snippet"
        update_result = _api_call("PUT", update_url, access_token, payload={
            "id": vid,
            "snippet": {
                "title": new_title,
                "description": description,
                "tags": new_tags,
                "categoryId": cat_id,
            },
        }, label="update")

        if update_result:
            result_entry["action"] = "updated"
            updated += 1
            print(f"  UPDATED: {new_title[:60]}")
        else:
            result_entry["action"] = "update_failed"
            print(f"  FAILED: {title[:60]}")

        time.sleep(1)  # Rate limit YouTube API
        results.append(result_entry)

    total_issues = sum(1 for r in results if r["issues"])
    print(f"\n  Summary: {len(videos)} videos, {total_issues} with SEO issues, {updated} {'would update' if dry_run else 'updated'}")
    if gemini_calls:
        print(f"  Gemini API calls: {gemini_calls}")

    return {
        "channel": channel_name,
        "status": "processed",
        "total_videos": len(videos),
        "issues_found": total_issues,
        "updated": updated,
        "videos": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Bulk fix SEO metadata across all channels")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    group.add_argument("--commit", action="store_true", help="Apply SEO fixes")
    group.add_argument("--report", action="store_true", help="Generate audit report only (no Gemini)")
    parser.add_argument("--channel", type=str, help="Process only this channel")
    args = parser.parse_args()

    print("=" * 60)
    print("  BULK SEO METADATA FIXER")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'REPORT ONLY' if args.report else 'COMMIT (LIVE)'}")
    if args.channel:
        print(f"  Channel: {args.channel}")
    print("=" * 60)

    all_results = []

    if args.channel:
        channels_to_process = {args.channel: CHANNEL_MAP.get(args.channel)}
        if not channels_to_process[args.channel]:
            print(f"ERROR: Unknown channel '{args.channel}'")
            print(f"Available: {', '.join(sorted(CHANNEL_MAP.keys()))}")
            sys.exit(1)
    else:
        channels_to_process = CHANNEL_MAP

    for channel_name, (channel_id, category_id) in sorted(channels_to_process.items()):
        try:
            result = process_channel(
                channel_name, channel_id, category_id,
                dry_run=args.dry_run or args.report,
                report_only=args.report,
            )
            all_results.append(result)
        except Exception as e:
            print(f"  ERROR processing {channel_name}: {str(e)[:200]}")
            all_results.append({
                "channel": channel_name,
                "status": "error",
                "error": str(e)[:200],
            })

    # Summary
    print(f"\n{'='*60}")
    print("  FINAL SUMMARY")
    print(f"{'='*60}")
    total_videos = sum(r.get("total_videos", 0) for r in all_results)
    total_issues = sum(r.get("issues_found", 0) for r in all_results)
    total_updated = sum(r.get("updated", 0) for r in all_results)
    failed = sum(1 for r in all_results if r["status"] in ("token_failed", "error"))

    print(f"  Channels processed: {len(all_results) - failed}")
    print(f"  Channels failed:    {failed}")
    print(f"  Total videos:       {total_videos}")
    print(f"  SEO issues found:   {total_issues}")
    print(f"  Videos {'to update' if args.dry_run else 'updated'}: {total_updated}")

    # Save report
    report_path = os.path.join(REPORT_DIR, "seo_audit_report.json")
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "dry_run" if args.dry_run else "report" if args.report else "commit",
            "summary": {
                "channels": len(all_results),
                "total_videos": total_videos,
                "issues_found": total_issues,
                "updated": total_updated,
            },
            "channels": all_results,
        }, f, indent=2)
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()
