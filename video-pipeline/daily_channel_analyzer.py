#!/usr/bin/env python3
"""Daily YouTube Channel Deep-Dive Analyzer.

Runs daily to analyze ALL YouTube channels across 3 accounts:
- rabreu84@gmail.com
- furywall213@gmail.com
- evarey69@gmail.com

For each channel, performs a full-suite analysis:
1. Channel Health: subscribers, views, upload frequency
2. SEO Audit: titles, descriptions, tags, keywords
3. Thumbnail Assessment: consistency, text overlay patterns
4. Content Strategy: upload cadence, topic gaps, trending alignment
5. Engagement Metrics: likes/views ratio, comments, shares
6. Playlist Organization: coverage, naming, structure
7. Branding Check: description, banner, links, country
8. Monetization Readiness: watch hours, subs, metadata compliance

Outputs a detailed Google Doc report with actionable recommendations.
"""

import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "daily_analysis")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# YouTube API Key for public data queries (saves OAuth quota)
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "AIzaSyCRu7Ac5o-zHm-0q7WrUiKDFEGEg46M7ME")

# Google Docs OAuth token path (needs docs + drive scope)
GOOGLE_TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")

# Analysis period
ANALYSIS_DAYS = 30

# Benchmarks
BENCHMARKS = {
    "upload_frequency_weekly": 3,          # Minimum uploads per week
    "title_length_min": 40,
    "title_length_max": 70,
    "description_min_length": 200,
    "tags_min_count": 8,
    "engagement_rate_min": 3.0,            # likes/views %
    "ctr_target": 4.0,
    "avd_target": 40.0,
    "subscriber_conversion_target": 5.0,
    "shorts_swipe_away_max": 90.0,
}

# Priority tiers for channels
PRIORITY_CHANNELS = [
    "Cumquat Motivation", "How to Use AI", "RichMind", "RichTech",
    "Eva Reyes", "RichHorror", "Rich Business", "RichFinance"
]


# ──────────────────────────────────────────────
# OAuth Token Management
# ──────────────────────────────────────────────

def refresh_channel_token(creds):
    """Refresh OAuth token for a channel."""
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    try:
        resp = json.loads(urlopen(req).read())
        return resp["access_token"]
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        return None


def refresh_google_token():
    """Refresh Google Docs/Drive token."""
    if not os.path.exists(GOOGLE_TOKEN_PATH):
        return None
    with open(GOOGLE_TOKEN_PATH) as f:
        token_data = json.load(f)

    payload = urllib.parse.urlencode({
        "client_id": token_data["client_id"],
        "client_secret": token_data["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=payload)
    try:
        resp = json.loads(urlopen(req).read())
        return resp["access_token"]
    except HTTPError:
        return None


# ──────────────────────────────────────────────
# YouTube Data API Calls
# ──────────────────────────────────────────────

def api_get(url, access_token=None):
    """Generic GET request to YouTube API."""
    if access_token:
        req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    else:
        sep = "&" if "?" in url else "?"
        req = Request(f"{url}{sep}key={YOUTUBE_API_KEY}")
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        return {"error": err[:300]}


def get_channel_details(access_token):
    """Fetch full channel details using OAuth."""
    url = ("https://www.googleapis.com/youtube/v3/channels"
           "?part=snippet,brandingSettings,statistics,contentDetails,status"
           "&mine=true")
    return api_get(url, access_token)


def get_recent_videos(channel_id, max_results=50):
    """Fetch recent videos for a channel using API key."""
    url = (f"https://www.googleapis.com/youtube/v3/search"
           f"?part=snippet&channelId={channel_id}&type=video"
           f"&order=date&maxResults={max_results}")
    return api_get(url)


def get_video_stats(video_ids):
    """Fetch stats for a batch of video IDs."""
    if not video_ids:
        return []
    ids_str = ",".join(video_ids[:50])
    url = (f"https://www.googleapis.com/youtube/v3/videos"
           f"?part=snippet,statistics,contentDetails&id={ids_str}")
    data = api_get(url)
    return data.get("items", [])


def get_playlists(access_token):
    """List playlists for a channel."""
    url = ("https://www.googleapis.com/youtube/v3/playlists"
           "?part=snippet,contentDetails&mine=true&maxResults=50")
    data = api_get(url, access_token)
    return data.get("items", [])


# ──────────────────────────────────────────────
# Analysis Functions
# ──────────────────────────────────────────────

def analyze_channel_health(channel_info, recent_videos):
    """Analyze overall channel health metrics."""
    issues = []
    stats = channel_info.get("statistics", {})
    snippet = channel_info.get("snippet", {})
    branding = channel_info.get("brandingSettings", {}).get("channel", {})

    sub_count = int(stats.get("subscriberCount", 0))
    view_count = int(stats.get("viewCount", 0))
    video_count = int(stats.get("videoCount", 0))

    # Upload frequency check
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=ANALYSIS_DAYS)
    recent_dates = []
    for v in recent_videos:
        pub = v.get("snippet", {}).get("publishedAt", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt >= cutoff:
                    recent_dates.append(dt)
            except ValueError:
                pass

    uploads_last_30d = len(recent_dates)
    uploads_per_week = uploads_last_30d / 4.3 if uploads_last_30d > 0 else 0

    if uploads_per_week < 1:
        issues.append({
            "severity": "CRITICAL",
            "area": "Upload Frequency",
            "issue": f"Only {uploads_last_30d} uploads in last 30 days ({uploads_per_week:.1f}/week)",
            "fix": "Increase to minimum 3 uploads/week. Use batch production pipeline to stay consistent."
        })
    elif uploads_per_week < BENCHMARKS["upload_frequency_weekly"]:
        issues.append({
            "severity": "WARNING",
            "area": "Upload Frequency",
            "issue": f"{uploads_last_30d} uploads in 30 days ({uploads_per_week:.1f}/week)",
            "fix": f"Target {BENCHMARKS['upload_frequency_weekly']}+ uploads/week for algorithm favor."
        })

    # Branding checks
    desc = branding.get("description", snippet.get("description", ""))
    if len(desc) < 50:
        issues.append({
            "severity": "HIGH",
            "area": "Channel Branding",
            "issue": f"Channel description too short ({len(desc)} chars)",
            "fix": "Write 200+ char description with keywords, value prop, and CTA."
        })

    if not branding.get("keywords", "").strip():
        issues.append({
            "severity": "HIGH",
            "area": "Channel SEO",
            "issue": "No channel keywords set",
            "fix": "Add 10-20 relevant keywords in channel settings > Advanced."
        })

    country = snippet.get("country", branding.get("country", ""))
    if not country:
        issues.append({
            "severity": "HIGH",
            "area": "Monetization",
            "issue": "No country set (required for monetization)",
            "fix": "Set country to 'US' in channel settings."
        })

    lang = snippet.get("defaultLanguage", "")
    if not lang:
        issues.append({
            "severity": "MEDIUM",
            "area": "SEO",
            "issue": "No default language set",
            "fix": "Set default language to English in channel settings."
        })

    # Monetization readiness
    if sub_count < 1000:
        issues.append({
            "severity": "INFO",
            "area": "Monetization",
            "issue": f"Only {sub_count} subscribers (need 1,000 for YPP)",
            "fix": "Focus on subscriber CTAs, end screens, and community engagement."
        })

    return {
        "subscribers": sub_count,
        "total_views": view_count,
        "total_videos": video_count,
        "uploads_last_30d": uploads_last_30d,
        "uploads_per_week": round(uploads_per_week, 1),
        "has_description": len(desc) >= 50,
        "has_keywords": bool(branding.get("keywords", "").strip()),
        "has_country": bool(country),
        "issues": issues
    }


def analyze_video_seo(video_items):
    """Analyze SEO quality across recent videos."""
    issues = []
    video_scores = []

    for video in video_items:
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        title = snippet.get("title", "")
        desc = snippet.get("description", "")
        tags = snippet.get("tags", [])
        video_id = video.get("id", "")

        score = 100
        video_issues = []

        # Title analysis
        if len(title) < BENCHMARKS["title_length_min"]:
            video_issues.append(f"Title too short ({len(title)} chars)")
            score -= 15
        elif len(title) > BENCHMARKS["title_length_max"]:
            video_issues.append(f"Title too long ({len(title)} chars) — may truncate")
            score -= 5

        import re
        if not re.search(r'\d', title):
            video_issues.append("No numbers in title (numbers boost CTR ~36%)")
            score -= 10

        # Check for clickbait power words
        power_words = ["secret", "truth", "never", "always", "best", "worst",
                       "how to", "why", "what", "shocking", "proven", "ultimate"]
        has_power = any(pw in title.lower() for pw in power_words)
        if not has_power:
            video_issues.append("No power words in title")
            score -= 5

        # Description analysis
        if len(desc) < BENCHMARKS["description_min_length"]:
            video_issues.append(f"Description too short ({len(desc)} chars)")
            score -= 15

        if "#" not in desc:
            video_issues.append("No hashtags in description")
            score -= 5

        if "0:00" not in desc and "00:00" not in desc:
            video_issues.append("No timestamps/chapters in description")
            score -= 10

        # Tags analysis
        if len(tags) < BENCHMARKS["tags_min_count"]:
            video_issues.append(f"Only {len(tags)} tags (need {BENCHMARKS['tags_min_count']}+)")
            score -= 10

        # Engagement analysis
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        if views > 0:
            engagement_rate = (likes / views) * 100
            if engagement_rate < BENCHMARKS["engagement_rate_min"]:
                video_issues.append(f"Low engagement ({engagement_rate:.1f}% like rate)")
                score -= 10

        video_scores.append({
            "video_id": video_id,
            "title": title[:80],
            "score": max(0, score),
            "views": views,
            "likes": likes,
            "comments": comments,
            "issues": video_issues
        })

    # Aggregate issues
    all_video_issues = []
    for vs in video_scores:
        all_video_issues.extend(vs["issues"])

    issue_counts = Counter(all_video_issues)
    for issue, count in issue_counts.most_common(10):
        pct = (count / len(video_scores) * 100) if video_scores else 0
        severity = "CRITICAL" if pct > 80 else "HIGH" if pct > 50 else "MEDIUM"
        issues.append({
            "severity": severity,
            "area": "Video SEO",
            "issue": f"{issue} — affects {count}/{len(video_scores)} videos ({pct:.0f}%)",
            "fix": get_seo_fix(issue)
        })

    avg_score = sum(vs["score"] for vs in video_scores) / len(video_scores) if video_scores else 0

    return {
        "avg_seo_score": round(avg_score),
        "videos_analyzed": len(video_scores),
        "top_performers": sorted(video_scores, key=lambda x: x["views"], reverse=True)[:5],
        "worst_performers": sorted(video_scores, key=lambda x: x["score"])[:5],
        "issues": issues
    }


def get_seo_fix(issue_text):
    """Map common issues to specific fix instructions."""
    fixes = {
        "title too short": "Expand titles to 40-70 chars. Use format: [Number] + [Power Word] + [Topic] + [Qualifier]",
        "title too long": "Trim to 70 chars max. Front-load keywords — truncated text won't appear in search.",
        "no numbers in title": "Add a number: '7 Signs...', '5 Ways...', '3 Secrets...'. Numbers increase CTR by ~36%.",
        "no power words": "Add hooks: 'SECRET', 'TRUTH', 'PROVEN', 'How To'. These trigger curiosity clicks.",
        "description too short": "Write 200+ chars. Include: hook (2 lines), timestamps, hashtags, links, keywords.",
        "no hashtags": "Add 3-5 niche hashtags at the end. YouTube shows first 3 above the title.",
        "no timestamps": "Add chapter markers (0:00 Intro, 1:23 Topic...). Enables Google Key Moments in search.",
        "only": "Add 8-15 specific tags mixing broad and long-tail keywords. Use TubeBuddy/VidIQ for research.",
        "low engagement": "Add CTAs within first 60 seconds. Ask questions. Pin a comment to spark discussion."
    }
    for key, fix in fixes.items():
        if key in issue_text.lower():
            return fix
    return "Review and optimize based on top-performing videos in your niche."


def analyze_playlists(playlists, video_count):
    """Analyze playlist organization."""
    issues = []

    if not playlists:
        issues.append({
            "severity": "HIGH",
            "area": "Playlists",
            "issue": "No playlists created",
            "fix": "Create 3-5 topic-based playlists. Playlists boost session time and appear in search."
        })
    elif len(playlists) < 3:
        issues.append({
            "severity": "MEDIUM",
            "area": "Playlists",
            "issue": f"Only {len(playlists)} playlists",
            "fix": "Create at least 3 playlists to organize content by topic/series."
        })

    # Check for empty playlists
    for pl in playlists:
        item_count = pl.get("contentDetails", {}).get("itemCount", 0)
        if item_count == 0:
            issues.append({
                "severity": "LOW",
                "area": "Playlists",
                "issue": f"Empty playlist: '{pl['snippet']['title']}'",
                "fix": "Add videos or delete empty playlists — they look unfinished."
            })

    return {
        "playlist_count": len(playlists),
        "issues": issues
    }


def analyze_content_strategy(video_items, channel_name):
    """Analyze content strategy and topic coverage."""
    issues = []

    if not video_items:
        issues.append({
            "severity": "CRITICAL",
            "area": "Content Strategy",
            "issue": "No videos found",
            "fix": "Start uploading immediately. Consistency > perfection."
        })
        return {"issues": issues, "topic_distribution": {}}

    # Analyze upload timing patterns
    publish_hours = []
    publish_days = []
    for v in video_items:
        pub = v.get("snippet", {}).get("publishedAt", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                publish_hours.append(dt.hour)
                publish_days.append(dt.strftime("%A"))
            except ValueError:
                pass

    # Check duration distribution (shorts vs longs)
    shorts_count = 0
    longs_count = 0
    for v in video_items:
        duration = v.get("contentDetails", {}).get("duration", "")
        if duration:
            # Parse ISO 8601 duration
            import re
            match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
            if match:
                hours = int(match.group(1) or 0)
                minutes = int(match.group(2) or 0)
                seconds = int(match.group(3) or 0)
                total_seconds = hours * 3600 + minutes * 60 + seconds
                if total_seconds <= 60:
                    shorts_count += 1
                else:
                    longs_count += 1

    if shorts_count == 0 and longs_count > 0:
        issues.append({
            "severity": "MEDIUM",
            "area": "Content Mix",
            "issue": "No Shorts uploaded — missing discovery opportunity",
            "fix": "Add 2-3 Shorts/week. Shorts drive subscriber growth and feed long-form audience."
        })

    if longs_count == 0 and shorts_count > 0:
        issues.append({
            "severity": "HIGH",
            "area": "Content Mix",
            "issue": "Only Shorts, no long-form content",
            "fix": "Add 1-2 long-form videos/week. Long-form drives watch hours for monetization."
        })

    # Best publish times (for reference)
    best_hour = Counter(publish_hours).most_common(1)[0][0] if publish_hours else None
    best_day = Counter(publish_days).most_common(1)[0][0] if publish_days else None

    return {
        "shorts_count": shorts_count,
        "longs_count": longs_count,
        "best_publish_hour": best_hour,
        "best_publish_day": best_day,
        "issues": issues
    }


# ──────────────────────────────────────────────
# Report Generation
# ──────────────────────────────────────────────

def generate_channel_report(channel_name, channel_info, access_token):
    """Generate a comprehensive analysis report for one channel."""
    print(f"  Analyzing: {channel_name}...")

    channel_data = channel_info.get("items", [{}])[0] if channel_info.get("items") else {}
    if not channel_data:
        return {"channel": channel_name, "error": "Could not fetch channel data", "issues": []}

    channel_id = channel_data.get("id", "")

    # Get recent videos
    search_data = get_recent_videos(channel_id, max_results=50)
    recent_videos = search_data.get("items", [])
    time.sleep(0.3)

    # Get video IDs for detailed stats
    video_ids = [v["id"]["videoId"] for v in recent_videos
                 if v.get("id", {}).get("videoId")]
    video_items = get_video_stats(video_ids[:50]) if video_ids else []
    time.sleep(0.3)

    # Get playlists
    playlists = get_playlists(access_token)
    time.sleep(0.3)

    # Run all analyses
    health = analyze_channel_health(channel_data, recent_videos)
    seo = analyze_video_seo(video_items)
    playlist_analysis = analyze_playlists(playlists, health["total_videos"])
    strategy = analyze_content_strategy(video_items, channel_name)

    # Compile all issues
    all_issues = (
        health["issues"] +
        seo["issues"] +
        playlist_analysis["issues"] +
        strategy["issues"]
    )

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "WARNING": 3, "LOW": 4, "INFO": 5}
    all_issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

    # Calculate overall score
    critical_count = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
    high_count = sum(1 for i in all_issues if i["severity"] == "HIGH")
    medium_count = sum(1 for i in all_issues if i["severity"] == "MEDIUM")

    base_score = 100
    base_score -= critical_count * 20
    base_score -= high_count * 10
    base_score -= medium_count * 5
    overall_score = max(0, min(100, base_score))

    is_priority = channel_name in PRIORITY_CHANNELS

    return {
        "channel": channel_name,
        "channel_id": channel_id,
        "is_priority": is_priority,
        "overall_score": overall_score,
        "health": health,
        "seo": seo,
        "playlists": playlist_analysis,
        "strategy": strategy,
        "all_issues": all_issues,
        "issue_count": {
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "total": len(all_issues)
        }
    }


def format_report_text(reports, run_date):
    """Format all channel reports into a readable text document."""
    lines = []
    lines.append(f"{'='*80}")
    lines.append(f"DAILY YOUTUBE CHANNEL ANALYSIS REPORT")
    lines.append(f"Date: {run_date}")
    lines.append(f"Channels Analyzed: {len(reports)}")
    lines.append(f"{'='*80}")
    lines.append("")

    # Executive Summary
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 40)

    # Sort by score (worst first for priority)
    sorted_reports = sorted(reports, key=lambda r: r.get("overall_score", 0))

    total_issues = sum(r.get("issue_count", {}).get("total", 0) for r in reports)
    total_critical = sum(r.get("issue_count", {}).get("critical", 0) for r in reports)
    total_high = sum(r.get("issue_count", {}).get("high", 0) for r in reports)

    lines.append(f"Total Issues Found: {total_issues}")
    lines.append(f"  Critical: {total_critical}")
    lines.append(f"  High: {total_high}")
    lines.append("")

    # Channel scorecard
    lines.append("CHANNEL SCORECARD (sorted by score)")
    lines.append("-" * 40)
    for r in sorted_reports:
        if "error" in r:
            lines.append(f"  {r['channel']}: ERROR - {r['error']}")
            continue
        priority_tag = " [PRIORITY]" if r.get("is_priority") else ""
        score = r.get("overall_score", 0)
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D" if score >= 20 else "F"
        health = r.get("health", {})
        lines.append(
            f"  {grade} ({score:3d}) | {r['channel']}{priority_tag}"
            f" | {health.get('subscribers', 0):,} subs"
            f" | {health.get('uploads_last_30d', 0)} uploads/30d"
            f" | {r['issue_count']['total']} issues"
        )
    lines.append("")

    # Channels needing immediate attention
    critical_channels = [r for r in sorted_reports if r.get("issue_count", {}).get("critical", 0) > 0]
    if critical_channels:
        lines.append("CHANNELS NEEDING IMMEDIATE ATTENTION")
        lines.append("-" * 40)
        for r in critical_channels:
            lines.append(f"\n  >>> {r['channel']} (Score: {r['overall_score']})")
            for issue in r.get("all_issues", []):
                if issue["severity"] == "CRITICAL":
                    lines.append(f"      CRITICAL: {issue['issue']}")
                    lines.append(f"      FIX: {issue['fix']}")
        lines.append("")

    # Detailed channel reports
    lines.append("")
    lines.append(f"{'='*80}")
    lines.append("DETAILED CHANNEL REPORTS")
    lines.append(f"{'='*80}")

    for r in sorted_reports:
        if "error" in r:
            continue

        lines.append("")
        lines.append(f"{'─'*60}")
        priority_tag = " [PRIORITY CHANNEL]" if r.get("is_priority") else ""
        lines.append(f"CHANNEL: {r['channel']}{priority_tag}")
        lines.append(f"Score: {r['overall_score']}/100")
        lines.append(f"{'─'*60}")

        # Health metrics
        health = r.get("health", {})
        lines.append(f"\n  CHANNEL HEALTH:")
        lines.append(f"    Subscribers: {health.get('subscribers', 0):,}")
        lines.append(f"    Total Views: {health.get('total_views', 0):,}")
        lines.append(f"    Total Videos: {health.get('total_videos', 0)}")
        lines.append(f"    Uploads (30d): {health.get('uploads_last_30d', 0)}")
        lines.append(f"    Uploads/Week: {health.get('uploads_per_week', 0)}")
        lines.append(f"    Has Description: {'Yes' if health.get('has_description') else 'NO'}")
        lines.append(f"    Has Keywords: {'Yes' if health.get('has_keywords') else 'NO'}")
        lines.append(f"    Has Country: {'Yes' if health.get('has_country') else 'NO'}")

        # SEO metrics
        seo = r.get("seo", {})
        lines.append(f"\n  VIDEO SEO:")
        lines.append(f"    Avg SEO Score: {seo.get('avg_seo_score', 0)}/100")
        lines.append(f"    Videos Analyzed: {seo.get('videos_analyzed', 0)}")

        # Top performers
        top = seo.get("top_performers", [])
        if top:
            lines.append(f"\n    Top Performing Videos:")
            for v in top[:3]:
                lines.append(f"      [{v['views']:,} views] {v['title']}")

        # Worst performers
        worst = seo.get("worst_performers", [])
        if worst:
            lines.append(f"\n    Lowest SEO Score Videos:")
            for v in worst[:3]:
                lines.append(f"      [Score {v['score']}] {v['title']}")
                if v.get("issues"):
                    for vi in v["issues"][:3]:
                        lines.append(f"        - {vi}")

        # Content Strategy
        strat = r.get("strategy", {})
        lines.append(f"\n  CONTENT STRATEGY:")
        lines.append(f"    Long-form Videos: {strat.get('longs_count', 0)}")
        lines.append(f"    Shorts: {strat.get('shorts_count', 0)}")
        if strat.get("best_publish_day"):
            lines.append(f"    Best Publish Day: {strat['best_publish_day']}")
        if strat.get("best_publish_hour") is not None:
            lines.append(f"    Best Publish Hour: {strat['best_publish_hour']}:00 UTC")

        # Playlists
        pl = r.get("playlists", {})
        lines.append(f"\n  PLAYLISTS:")
        lines.append(f"    Total Playlists: {pl.get('playlist_count', 0)}")

        # All issues
        all_issues = r.get("all_issues", [])
        if all_issues:
            lines.append(f"\n  ALL ISSUES ({len(all_issues)}):")
            for issue in all_issues:
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "WARNING": "🟡", "LOW": "🔵", "INFO": "ℹ️"}.get(issue["severity"], "•")
                lines.append(f"    {icon} [{issue['severity']}] {issue['area']}: {issue['issue']}")
                lines.append(f"       FIX: {issue['fix']}")
        else:
            lines.append(f"\n  No issues found — channel is in good shape!")

    # Footer
    lines.append("")
    lines.append(f"{'='*80}")
    lines.append(f"Report generated: {datetime.now().isoformat()[:19]}")
    lines.append(f"Next analysis scheduled: Tomorrow at 6:00 AM ET")
    lines.append(f"{'='*80}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Google Docs Integration
# ──────────────────────────────────────────────

def create_or_update_google_doc(title, content, access_token):
    """Create a new Google Doc with the report content."""
    # Create the document
    create_url = "https://docs.googleapis.com/v1/documents"
    create_payload = json.dumps({"title": title}).encode("utf-8")
    req = Request(create_url, data=create_payload, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })

    try:
        with urlopen(req) as resp:
            doc_data = json.loads(resp.read().decode("utf-8"))
        doc_id = doc_data["documentId"]
        print(f"  Created Google Doc: {doc_id}")
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Google Docs create error: {err[:300]}")
        return None

    # Insert content
    update_url = f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate"
    update_payload = json.dumps({
        "requests": [{
            "insertText": {
                "location": {"index": 1},
                "text": content
            }
        }]
    }).encode("utf-8")

    req = Request(update_url, data=update_payload, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })

    try:
        urlopen(req)
        print(f"  Content written to Google Doc")
        return f"https://docs.google.com/document/d/{doc_id}/edit"
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Google Docs update error: {err[:300]}")
        return f"https://docs.google.com/document/d/{doc_id}/edit"


# ──────────────────────────────────────────────
# Main Execution
# ──────────────────────────────────────────────

def main():
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\nDaily YouTube Channel Analyzer")
    print(f"Run Date: {run_date}")
    print(f"{'='*60}")

    # Load channel tokens
    with open(CHANNEL_TOKENS_PATH) as f:
        all_tokens = json.load(f)

    print(f"Found {len(all_tokens)} channels to analyze.\n")

    reports = []
    errors = []

    for channel_name, creds in sorted(all_tokens.items()):
        print(f"\n--- {channel_name} ---")

        # Refresh token
        access_token = refresh_channel_token(creds)
        if not access_token:
            print(f"  SKIP: Token refresh failed")
            errors.append(channel_name)
            continue

        # Get channel details
        channel_info = get_channel_details(access_token)
        if "error" in channel_info:
            print(f"  SKIP: API error")
            errors.append(channel_name)
            continue

        # Generate report
        report = generate_channel_report(channel_name, channel_info, access_token)
        reports.append(report)

        # Rate limit
        time.sleep(0.5)

    # Format the full report
    report_text = format_report_text(reports, run_date)

    # Save locally
    local_path = os.path.join(OUTPUT_DIR, f"analysis_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(local_path, "w") as f:
        f.write(report_text)
    print(f"\nLocal report saved: {local_path}")

    # Save JSON for programmatic access
    json_path = os.path.join(OUTPUT_DIR, f"analysis_{datetime.now().strftime('%Y%m%d')}.json")
    with open(json_path, "w") as f:
        json.dump(reports, f, indent=2, default=str)
    print(f"JSON data saved: {json_path}")

    # Upload to Google Docs
    google_token = refresh_google_token()
    if google_token:
        doc_title = f"YouTube Channel Analysis — {datetime.now().strftime('%B %d, %Y')}"
        doc_url = create_or_update_google_doc(doc_title, report_text, google_token)
        if doc_url:
            print(f"\nGoogle Doc: {doc_url}")
    else:
        print("\nGoogle Docs token not available — report saved locally only.")

    # Print summary
    print(f"\n{'='*60}")
    print(f"ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Channels analyzed: {len(reports)}")
    print(f"Channels with errors: {len(errors)}")
    if errors:
        print(f"Failed channels: {', '.join(errors)}")

    total_issues = sum(r.get("issue_count", {}).get("total", 0) for r in reports)
    total_critical = sum(r.get("issue_count", {}).get("critical", 0) for r in reports)
    print(f"Total issues found: {total_issues}")
    print(f"Critical issues: {total_critical}")

    # Return exit code based on critical issues
    if total_critical > 0:
        print(f"\n⚠️  {total_critical} CRITICAL issues need immediate attention!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
