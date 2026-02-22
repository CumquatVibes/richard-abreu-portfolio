"""YouTube Analytics API integration for the feedback loop.

Queries YouTube Analytics API (reports.query) for per-video KPIs:
- Impressions + CTR (packaging effectiveness)
- Watch time + avg view duration/percentage (content quality)
- Engagement (likes, comments, shares)
- Subscribers gained/lost (growth efficiency)

Stores results in the SQLite telemetry DB for learning loop and drift detection.
"""

import json
import os
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = os.path.join(BASE_DIR, "youtube_token.json")
CLIENT_SECRET_PATH = os.path.join(BASE_DIR, "client_secret.json")

# YouTube Analytics API endpoint
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"

# Core metrics we track per the report's KPI framework
CORE_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
]

# Reach metrics (thumbnail impressions + CTR)
REACH_METRICS = [
    "cardClickRate",  # closest available via API
]


def _get_access_token():
    """Get a fresh YouTube API access token."""
    if not os.path.exists(TOKEN_PATH):
        print("  Analytics: No youtube_token.json found")
        return None

    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expiry = token_data.get("expiry", "")

    # Check if token needs refresh
    if expiry:
        try:
            expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if datetime.now(expiry_dt.tzinfo) > expiry_dt:
                access_token = _refresh_token(refresh_token)
        except (ValueError, TypeError):
            pass

    return access_token


def _refresh_token(refresh_token):
    """Refresh the OAuth2 token."""
    if not os.path.exists(CLIENT_SECRET_PATH):
        return None

    with open(CLIENT_SECRET_PATH) as f:
        client = json.load(f).get("installed", json.load(open(CLIENT_SECRET_PATH)).get("web", {}))

    # Re-read since we consumed the file handle
    with open(CLIENT_SECRET_PATH) as f:
        secrets = json.load(f)
    client = secrets.get("installed", secrets.get("web", {}))

    data = (
        f"client_id={client['client_id']}"
        f"&client_secret={client['client_secret']}"
        f"&refresh_token={refresh_token}"
        f"&grant_type=refresh_token"
    ).encode()

    req = Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        resp = urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        new_token = result.get("access_token")

        # Save updated token
        with open(TOKEN_PATH) as f:
            token_data = json.load(f)
        token_data["access_token"] = new_token
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f, indent=2)

        return new_token
    except Exception as e:
        print(f"  Analytics: Token refresh failed: {str(e)[:100]}")
        return None


def query_video_metrics(video_id, start_date=None, end_date=None, access_token=None):
    """Query YouTube Analytics API for a specific video's KPIs.

    Args:
        video_id: YouTube video ID
        start_date: Start date string (YYYY-MM-DD). Default: 7 days ago
        end_date: End date string (YYYY-MM-DD). Default: today
        access_token: OAuth token override

    Returns:
        dict with metric names as keys and values, or None on failure
    """
    token = access_token or _get_access_token()
    if not token:
        return None

    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    metrics_str = ",".join(CORE_METRICS)

    params = (
        f"ids=channel==MINE"
        f"&startDate={start_date}"
        f"&endDate={end_date}"
        f"&metrics={metrics_str}"
        f"&filters=video=={video_id}"
    )

    url = f"{ANALYTICS_API}?{params}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"})

    try:
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())

        # Parse response: columnHeaders + rows
        headers = [h["name"] for h in data.get("columnHeaders", [])]
        rows = data.get("rows", [])

        if not rows:
            return {"video_id": video_id, "data_available": False}

        # Map header names to values from first row
        result = {"video_id": video_id, "data_available": True}
        for i, header in enumerate(headers):
            if i < len(rows[0]):
                result[header] = rows[0][i]

        return result

    except HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        print(f"  Analytics API error {e.code}: {body[:200]}")
        return None
    except Exception as e:
        print(f"  Analytics query failed: {str(e)[:150]}")
        return None


def query_channel_overview(days=28, access_token=None):
    """Get channel-level performance overview."""
    token = access_token or _get_access_token()
    if not token:
        return None

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    metrics_str = ",".join(CORE_METRICS)

    url = (
        f"{ANALYTICS_API}?ids=channel==MINE"
        f"&startDate={start_date}&endDate={end_date}"
        f"&metrics={metrics_str}"
        f"&dimensions=video"
        f"&sort=-estimatedMinutesWatched"
        f"&maxResults=50"
    )

    req = Request(url, headers={"Authorization": f"Bearer {token}"})

    try:
        resp = urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())

        headers = [h["name"] for h in data.get("columnHeaders", [])]
        rows = data.get("rows", [])

        videos = []
        for row in rows:
            video = {}
            for i, header in enumerate(headers):
                if i < len(row):
                    video[header] = row[i]
            videos.append(video)

        return videos

    except HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        print(f"  Analytics API error {e.code}: {body[:200]}")
        return None
    except Exception as e:
        print(f"  Analytics overview failed: {str(e)[:150]}")
        return None


def compute_reward(metrics, costs=None, risk_scores=None):
    """Compute multi-objective reward from video metrics.

    Reward function (from the research report):
    - Packaging: CTR (when available)
    - Watch-time value: estimatedMinutesWatched, averageViewDuration, averageViewPercentage
    - Engagement: likes, comments, shares, subscribers gained/lost
    - Hard penalties: policy/copyright risk
    - Cost efficiency: penalize high per-video costs

    Returns:
        dict with total_reward and component breakdown
    """
    if not metrics or not metrics.get("data_available"):
        return {"total_reward": 0, "components": {}, "confidence": "no_data"}

    components = {}

    # Watch time value (0-40 points)
    watch_min = metrics.get("estimatedMinutesWatched", 0)
    avg_pct = metrics.get("averageViewPercentage", 0)

    # Normalize: 100+ watch minutes = max score, 50%+ avg view = max score
    watch_score = min(watch_min / 100, 1.0) * 20
    retention_score = min(avg_pct / 50, 1.0) * 20
    components["watch_time"] = watch_score
    components["retention"] = retention_score

    # Engagement (0-30 points)
    views = max(metrics.get("views", 1), 1)
    likes = metrics.get("likes", 0)
    comments = metrics.get("comments", 0)
    shares = metrics.get("shares", 0)
    subs_gained = metrics.get("subscribersGained", 0)
    subs_lost = metrics.get("subscribersLost", 0)

    # Engagement rate (likes+comments+shares per view)
    engagement_rate = (likes + comments * 2 + shares * 3) / views
    engagement_score = min(engagement_rate / 0.1, 1.0) * 15  # 10% engagement = max
    components["engagement"] = engagement_score

    # Subscriber efficiency
    net_subs = subs_gained - subs_lost
    sub_score = min(max(net_subs, 0) / 10, 1.0) * 15  # 10+ net subs = max
    components["subscriber_growth"] = sub_score

    # Cost penalty (0 to -10)
    if costs:
        total_cost = costs.get("total_cost_usd", 0)
        cost_penalty = -min(total_cost / 5, 10)  # $5+ per video = -10 penalty
        components["cost_penalty"] = cost_penalty
    else:
        components["cost_penalty"] = 0

    # Risk penalty (0 to -20)
    if risk_scores:
        max_risk = max(risk_scores.values()) if risk_scores else 0
        risk_penalty = -max_risk * 20
        components["risk_penalty"] = risk_penalty
    else:
        components["risk_penalty"] = 0

    total = sum(components.values())

    # Confidence based on view count
    if views < 10:
        confidence = "very_low"
    elif views < 100:
        confidence = "low"
    elif views < 1000:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "total_reward": round(total, 2),
        "components": {k: round(v, 2) for k, v in components.items()},
        "confidence": confidence,
    }


def pull_metrics_and_store(video_name, youtube_video_id, window="7d"):
    """Pull metrics from YouTube Analytics and store in telemetry DB.

    Args:
        video_name: Pipeline video name (for DB lookup)
        youtube_video_id: YouTube video ID
        window: "6h", "24h", "48h", "7d", "28d" — determines date range
    """
    from utils.telemetry import log_metrics

    window_days = {
        "6h": 1, "24h": 1, "48h": 2, "7d": 7, "14d": 14, "28d": 28
    }
    days = window_days.get(window, 7)

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    metrics = query_video_metrics(youtube_video_id, start_date, end_date)

    if not metrics or not metrics.get("data_available"):
        print(f"  Analytics: No data for {youtube_video_id} ({window} window)")
        return None

    # Store in telemetry DB
    log_metrics(
        video_name=video_name,
        youtube_video_id=youtube_video_id,
        window=window,
        views=metrics.get("views"),
        estimated_minutes_watched=metrics.get("estimatedMinutesWatched"),
        avg_view_duration_sec=metrics.get("averageViewDuration"),
        avg_view_percentage=metrics.get("averageViewPercentage"),
        likes=metrics.get("likes"),
        comments=metrics.get("comments"),
        shares=metrics.get("shares"),
        subscribers_gained=metrics.get("subscribersGained"),
        subscribers_lost=metrics.get("subscribersLost"),
    )

    # Compute and store reward
    reward = compute_reward(metrics)
    log_metrics(
        video_name=video_name,
        youtube_video_id=youtube_video_id,
        window=f"{window}_reward",
        reward=reward["total_reward"],
        reward_components=json.dumps(reward["components"]),
        confidence=reward["confidence"],
    )

    print(f"  Analytics: {video_name} ({window}): {metrics.get('views', 0)} views, "
          f"{metrics.get('estimatedMinutesWatched', 0):.0f} min watched, "
          f"reward={reward['total_reward']:.1f} ({reward['confidence']})")

    return metrics


def pull_all_published_metrics(window="7d"):
    """Pull metrics for all published videos and store in telemetry DB.

    Reads the upload report to find published video IDs.
    """
    report_path = os.path.join(BASE_DIR, "output", "reports", "youtube_upload_report.json")
    if not os.path.exists(report_path):
        print("  Analytics: No upload report found")
        return

    with open(report_path) as f:
        report = json.load(f)

    published = [
        r for r in report.get("results", [])
        if r.get("status") == "success" and r.get("video_id")
    ]

    print(f"  Analytics: Pulling {window} metrics for {len(published)} published videos")

    for entry in published:
        video_name = os.path.splitext(entry["file"])[0]
        video_id = entry["video_id"]
        pull_metrics_and_store(video_name, video_id, window)
