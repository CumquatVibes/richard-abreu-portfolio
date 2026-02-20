#!/usr/bin/env python3
"""Post-upload self-assessment system.

Runs after each video upload to:
1. Verify upload metadata is correct (title, description, tags, category, language)
2. Check video against quality benchmarks
3. Generate improvement recommendations
4. Log assessment for trend tracking

Based on Richard's analytics feedback:
- CTR benchmark: 4-8% (was 1.4-1.6%)
- AVD benchmark: 40%+ (was 25%)
- Swipe-away benchmark: <90% for Shorts (was 95.2%)
- Subscriber conversion benchmark: >5% (was 1.7%)
"""

import json
import os
import re
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
ASSESSMENTS_DIR = os.path.join(BASE_DIR, "output", "assessments")
os.makedirs(ASSESSMENTS_DIR, exist_ok=True)

# Benchmarks based on analytics feedback
BENCHMARKS = {
    "title_length": {"min": 40, "max": 70, "note": "40-70 chars for full display"},
    "title_has_number": True,  # Titles with numbers get higher CTR
    "title_has_caps": True,  # Strategic caps for emphasis
    "description_min_length": 200,
    "description_has_timestamps": True,
    "description_has_hashtags": True,
    "description_has_keywords_first_2_lines": True,
    "tags_min_count": 8,
    "tags_max_count": 15,
    "category_not_default": True,  # Not "People & Blogs" (22)
    "language_set": True,  # defaultAudioLanguage should be "en"
    "script_min_words": 1500,
    "script_has_chapters": True,
    "script_hook_in_first_15s": True,
    "ctr_target": 4.0,  # percent
    "avd_target": 40.0,  # percent
    "subscriber_conversion_target": 5.0,  # percent
}

# Niche-appropriate categories (not "People & Blogs")
CORRECT_CATEGORIES = {
    "RichTech": "28",      # Science & Technology
    "RichHorror": "24",    # Entertainment
    "RichMind": "27",      # Education
    "HowToUseAI": "28",   # Science & Technology
    "RichPets": "15",      # Pets & Animals
    "EvaReyes": "22",      # People & Blogs (ok for empowerment)
    "RichBeauty": "26",    # Howto & Style
    "RichCooking": "26",   # Howto & Style
    "RichFitness": "17",   # Sports
    "RichFinance": "27",   # Education
}


def refresh_token(token_path=None):
    """Refresh OAuth token."""
    path = token_path or TOKEN_PATH
    with open(path) as f:
        token_data = json.load(f)

    if "refresh_token" not in token_data:
        return token_data.get("token", "")

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

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token_data["token"] = data["access_token"]
        with open(path, "w") as f:
            json.dump(token_data, f, indent=2)
        return data["access_token"]
    except HTTPError:
        return token_data.get("token", "")


def get_video_details(video_id, access_token):
    """Fetch video metadata from YouTube API."""
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,status,contentDetails,statistics"
        f"&id={video_id}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("items"):
            return data["items"][0]
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  API Error: {err[:200]}")
    return None


def assess_metadata(video_data, channel):
    """Assess video metadata against benchmarks."""
    issues = []
    good = []
    snippet = video_data.get("snippet", {})
    status = video_data.get("status", {})

    title = snippet.get("title", "")
    description = snippet.get("description", "")
    tags = snippet.get("tags", [])
    category_id = snippet.get("categoryId", "")
    language = snippet.get("defaultAudioLanguage", "")

    # Title checks
    title_len = len(title)
    if title_len < BENCHMARKS["title_length"]["min"]:
        issues.append(f"Title too short ({title_len} chars) — aim for 40-70 for full display")
    elif title_len > BENCHMARKS["title_length"]["max"]:
        issues.append(f"Title too long ({title_len} chars) — may get truncated in search")
    else:
        good.append(f"Title length OK ({title_len} chars)")

    if not re.search(r'\d', title):
        issues.append("Title has no numbers — titles with numbers get 36% higher CTR")
    else:
        good.append("Title contains numbers (CTR boost)")

    if not any(c.isupper() for c in title[1:]):
        issues.append("Title has no caps emphasis — use 1-2 CAPS words for impact")
    else:
        good.append("Title has caps emphasis")

    # Description checks
    if len(description) < BENCHMARKS["description_min_length"]:
        issues.append(f"Description too short ({len(description)} chars) — add timestamps, keywords, links")
    else:
        good.append(f"Description length OK ({len(description)} chars)")

    if "0:00" not in description and "00:00" not in description:
        issues.append("No timestamps in description — add chapter markers for Google Key Moments")
    else:
        good.append("Has timestamps/chapters")

    if "#" not in description:
        issues.append("No hashtags in description — add 3-5 niche hashtags")
    else:
        good.append("Has hashtags")

    # Tags checks
    if len(tags) < BENCHMARKS["tags_min_count"]:
        issues.append(f"Only {len(tags)} tags — add more (8-15 recommended)")
    else:
        good.append(f"Tags count OK ({len(tags)})")

    # Category check
    expected_cat = CORRECT_CATEGORIES.get(channel, "")
    if category_id == "22" and expected_cat and expected_cat != "22":
        issues.append(f"Category is 'People & Blogs' (22) — should be {expected_cat} for {channel}")
    else:
        good.append(f"Category ID: {category_id}")

    # Language check
    if not language:
        issues.append("No defaultAudioLanguage set — set to 'en' for search indexing")
    else:
        good.append(f"Language set: {language}")

    # Privacy check
    privacy = status.get("privacyStatus", "")
    if privacy != "public":
        issues.append(f"Video is {privacy} — make public for discovery")
    else:
        good.append("Video is public")

    return issues, good


def assess_script(script_path):
    """Assess the source script quality."""
    issues = []
    good = []

    if not script_path or not os.path.exists(script_path):
        issues.append("Source script not found — can't assess content quality")
        return issues, good

    with open(script_path) as f:
        content = f.read()

    word_count = len(content.split())
    if word_count < BENCHMARKS["script_min_words"]:
        issues.append(f"Script only {word_count} words — aim for 1500+ for 8-12 min videos")
    else:
        good.append(f"Script word count OK ({word_count})")

    if "[CHAPTER:" not in content:
        issues.append("No [CHAPTER:] markers in script — add for YouTube timestamps")
    else:
        chapters = re.findall(r'\[CHAPTER:', content)
        good.append(f"Has {len(chapters)} chapter markers")

    # Check hook quality (first 200 chars should have pattern interrupt)
    first_lines = content[:500].lower()
    hook_signals = ["?", "you", "imagine", "what if", "have you ever", "think about",
                    "right now", "every day", "destroying", "wrong", "mistake"]
    hook_count = sum(1 for s in hook_signals if s in first_lines)
    if hook_count < 2:
        issues.append("Weak hook — first 15 seconds need bold statement, question, or pattern interrupt")
    else:
        good.append(f"Strong hook detected ({hook_count} hook signals)")

    # Check visual directions
    visuals = re.findall(r'\[VISUAL:', content)
    if len(visuals) < 5:
        issues.append(f"Only {len(visuals)} [VISUAL:] cues — add more for B-roll variety")
    else:
        good.append(f"Good visual variety ({len(visuals)} cues)")

    return issues, good


def generate_report(video_id, channel, script_path=None, access_token=None):
    """Generate a full assessment report for an uploaded video."""
    report = {
        "video_id": video_id,
        "channel": channel,
        "assessed_at": datetime.now().isoformat(),
        "metadata_issues": [],
        "metadata_good": [],
        "script_issues": [],
        "script_good": [],
        "recommendations": [],
        "score": 0,
    }

    # Assess metadata
    if access_token and video_id:
        video_data = get_video_details(video_id, access_token)
        if video_data:
            meta_issues, meta_good = assess_metadata(video_data, channel)
            report["metadata_issues"] = meta_issues
            report["metadata_good"] = meta_good
            report["title"] = video_data["snippet"]["title"]
        else:
            report["metadata_issues"].append("Could not fetch video data from API")
    else:
        report["metadata_issues"].append("No video ID or access token — skipping API checks")

    # Assess script
    script_issues, script_good = assess_script(script_path)
    report["script_issues"] = script_issues
    report["script_good"] = script_good

    # Generate recommendations
    all_issues = report["metadata_issues"] + report["script_issues"]
    all_good = report["metadata_good"] + report["script_good"]

    total_checks = len(all_issues) + len(all_good)
    report["score"] = round((len(all_good) / total_checks * 100) if total_checks else 0)

    if any("hook" in i.lower() for i in all_issues):
        report["recommendations"].append(
            "HOOK FIX: Rewrite first 15 seconds — lead with the most shocking/relatable statement. "
            "Reference: Your 3-Second Rule from UgenticIQ ('communicate value in 3 seconds')."
        )

    if any("timestamp" in i.lower() or "chapter" in i.lower() for i in all_issues):
        report["recommendations"].append(
            "CHAPTERS: Add [CHAPTER:] markers to script and timestamps to description. "
            "YouTube rewards Key Moments with higher search placement."
        )

    if any("category" in i.lower() for i in all_issues):
        report["recommendations"].append(
            "CATEGORY: Update video category in YouTube Studio. "
            "Wrong category limits recommended video suggestions."
        )

    if any("tag" in i.lower() for i in all_issues):
        report["recommendations"].append(
            "TAGS: Add 8-15 specific, long-tail tags. Mix broad (psychology) and specific "
            "(dark psychology tricks manipulation). Use VidIQ for keyword research."
        )

    if report["score"] >= 80:
        report["verdict"] = "STRONG — Ready for audience"
    elif report["score"] >= 60:
        report["verdict"] = "GOOD — Minor improvements recommended"
    elif report["score"] >= 40:
        report["verdict"] = "NEEDS WORK — Fix issues before promoting"
    else:
        report["verdict"] = "WEAK — Major improvements needed"

    return report


def print_report(report):
    """Pretty-print an assessment report."""
    print(f"\n{'=' * 60}")
    print(f"POST-UPLOAD ASSESSMENT: {report.get('title', report['video_id'])}")
    print(f"{'=' * 60}")
    print(f"Channel: {report['channel']}")
    print(f"Score: {report['score']}% — {report['verdict']}")
    print(f"Assessed: {report['assessed_at'][:19]}")

    if report["metadata_good"]:
        print(f"\n  PASSING ({len(report['metadata_good'])}):")
        for g in report["metadata_good"]:
            print(f"    + {g}")

    if report["script_good"]:
        for g in report["script_good"]:
            print(f"    + {g}")

    if report["metadata_issues"]:
        print(f"\n  ISSUES ({len(report['metadata_issues'])}):")
        for i in report["metadata_issues"]:
            print(f"    ! {i}")

    if report["script_issues"]:
        for i in report["script_issues"]:
            print(f"    ! {i}")

    if report["recommendations"]:
        print(f"\n  RECOMMENDATIONS:")
        for r in report["recommendations"]:
            print(f"    -> {r}")

    print(f"\n{'=' * 60}\n")


def main():
    """Assess all recently uploaded videos or a specific video."""
    # Load upload report to find recently uploaded videos
    report_path = os.path.join(BASE_DIR, "output", "reports", "youtube_upload_report.json")

    if len(sys.argv) > 1:
        # Assess specific video ID
        video_id = sys.argv[1]
        channel = sys.argv[2] if len(sys.argv) > 2 else "Unknown"
        access_token = refresh_token()
        report = generate_report(video_id, channel, access_token=access_token)
        print_report(report)
        return

    if not os.path.exists(report_path):
        print("No upload report found. Run upload_to_youtube.py first.")
        return

    with open(report_path) as f:
        upload_data = json.load(f)

    access_token = refresh_token()
    print(f"Post-Upload Self-Assessment System")
    print(f"Assessing {upload_data['uploaded']} uploaded videos...\n")

    assessments = []
    for result in upload_data.get("results", []):
        if result.get("status") != "success" or not result.get("video_id"):
            continue

        video_id = result["video_id"]
        channel = result["channel"]
        filename = result.get("file", "")

        # Find matching script
        script_base = os.path.splitext(filename)[0] if filename else ""
        script_path = None
        if script_base:
            for sf in os.listdir(SCRIPTS_DIR):
                if sf.startswith(script_base.rsplit("_", 2)[0]) and sf.endswith(".txt"):
                    script_path = os.path.join(SCRIPTS_DIR, sf)
                    break

        report = generate_report(video_id, channel, script_path, access_token)
        print_report(report)
        assessments.append(report)

    # Save assessments
    if assessments:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        assessment_path = os.path.join(ASSESSMENTS_DIR, f"assessment_{timestamp}.json")
        with open(assessment_path, "w") as f:
            json.dump(assessments, f, indent=2)
        print(f"Assessments saved to: {assessment_path}")

        # Summary
        avg_score = sum(a["score"] for a in assessments) / len(assessments)
        print(f"\nOverall average score: {avg_score:.0f}%")
        print(f"Videos assessed: {len(assessments)}")

        # Most common issues
        all_issues = []
        for a in assessments:
            all_issues.extend(a["metadata_issues"] + a["script_issues"])

        if all_issues:
            print(f"\nMost common issues across all videos:")
            from collections import Counter
            for issue, count in Counter(all_issues).most_common(5):
                print(f"  [{count}x] {issue}")


if __name__ == "__main__":
    main()
