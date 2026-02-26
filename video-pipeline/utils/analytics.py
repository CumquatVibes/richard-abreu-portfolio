"""YouTube Analytics API integration for the feedback loop.

Queries YouTube Analytics API (reports.query) for per-video KPIs:
- Impressions + CTR (packaging effectiveness)
- Watch time + avg view duration/percentage (content quality)
- Engagement (likes, comments, shares)
- Subscribers gained/lost (growth efficiency)

Stores results in the SQLite telemetry DB for learning loop and drift detection.

Uses per-channel OAuth tokens from channel_tokens.json so that each video's
metrics are queried via the token that owns that channel.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
CLIENT_SECRET_PATH = os.path.join(BASE_DIR, "client_secret.json")

# YouTube Analytics API endpoint
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"

# Mapping from filename channel prefix to channel_tokens.json key
# (same as upload_to_youtube.TOKEN_KEY_MAP)
_TOKEN_KEY_MAP = {
    "HowToUseAI": "How to Use AI",
    "HowToMeditate": "How to Meditate",
    "EvaReyes": "Eva Reyes",
    "RichBusiness": "Rich Business",
    "CumquatMotivation": "Cumquat Motivation",
    "CumquatVibes": "Cumquat Vibes",
}

# Core metrics we track per the report's KPI framework
CORE_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "engagedViews",
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


# ---------------------------------------------------------------------------
# Token management — per-channel tokens
# ---------------------------------------------------------------------------

def _load_client_secret():
    """Load OAuth client secret (installed or web type)."""
    if not os.path.exists(CLIENT_SECRET_PATH):
        return None
    with open(CLIENT_SECRET_PATH) as f:
        secrets = json.load(f)
    return secrets.get("installed", secrets.get("web", {}))


def _refresh_channel_token(creds):
    """Refresh a per-channel OAuth2 token. Returns access_token string."""
    client = _load_client_secret()
    if not client:
        return None

    data = urlencode({
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()

    req = Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        resp = urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        return result.get("access_token")
    except Exception as e:
        print(f"  Analytics: Token refresh failed for {creds.get('channel_title', '?')}: {str(e)[:80]}")
        return None


def _load_channel_tokens():
    """Load all per-channel tokens from channel_tokens.json.

    Returns dict mapping token key (channel name) to its credentials dict.
    """
    if not os.path.exists(CHANNEL_TOKENS_PATH):
        return {}
    with open(CHANNEL_TOKENS_PATH) as f:
        return json.load(f)


def _get_token_for_channel(channel_prefix, channel_tokens_cache):
    """Get a fresh access token for a channel by its filename prefix.

    Args:
        channel_prefix: e.g. "RichMind", "HowToUseAI"
        channel_tokens_cache: dict of token_key -> {access_token, creds}

    Returns:
        (access_token, channel_id) tuple, or (None, None) if unavailable
    """
    token_key = _TOKEN_KEY_MAP.get(channel_prefix, channel_prefix)
    cached = channel_tokens_cache.get(token_key)
    if cached:
        return cached["access_token"], cached["channel_id"]
    return None, None


def _refresh_all_channel_tokens():
    """Refresh tokens for all channels. Returns cache dict.

    Cache format: {token_key: {"access_token": str, "channel_id": str, "creds": dict}}
    """
    all_creds = _load_channel_tokens()
    cache = {}
    refreshed = 0
    failed = 0

    for token_key, creds in all_creds.items():
        access_token = _refresh_channel_token(creds)
        if access_token:
            cache[token_key] = {
                "access_token": access_token,
                "channel_id": creds.get("channel_id"),
                "creds": creds,
            }
            refreshed += 1
        else:
            failed += 1

    print(f"  Analytics: Refreshed {refreshed} channel tokens ({failed} failed)")
    return cache


# ---------------------------------------------------------------------------
# YouTube Analytics API queries
# ---------------------------------------------------------------------------

def query_video_metrics(video_id, start_date=None, end_date=None, access_token=None):
    """Query YouTube Analytics API for a specific video's KPIs.

    Args:
        video_id: YouTube video ID
        start_date: Start date string (YYYY-MM-DD). Default: 7 days ago
        end_date: End date string (YYYY-MM-DD). Default: today
        access_token: OAuth token for the channel that owns this video

    Returns:
        dict with metric names as keys and values, or None on failure
    """
    if not access_token:
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
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

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
        # Don't spam logs for 403 (quota) — just note it
        if e.code == 403:
            print(f"  Analytics: API quota/permission error for {video_id}")
        else:
            print(f"  Analytics API error {e.code} for {video_id}: {body[:200]}")
        return None
    except Exception as e:
        print(f"  Analytics query failed for {video_id}: {str(e)[:150]}")
        return None


def query_traffic_sources(video_id, start_date=None, end_date=None, access_token=None):
    """Query traffic source breakdown for a video.

    Returns dict with views by source type (e.g., SHORTS, SEARCH, SUGGESTED).
    """
    if not access_token:
        return None

    if not start_date:
        start_date = "2020-01-01"
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    url = (f"{ANALYTICS_API}?ids=channel==MINE"
           f"&startDate={start_date}&endDate={end_date}"
           f"&metrics=views"
           f"&dimensions=insightTrafficSourceType"
           f"&filters=video=={video_id}")

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            rows = data.get("rows", [])
            sources = {}
            total_views = 0
            for row in rows:
                source_type = row[0]
                views = row[1]
                sources[source_type] = views
                total_views += views

            shorts_views = sources.get("SHORTS", 0)
            shorts_share = shorts_views / total_views if total_views > 0 else 0

            return {
                "sources": sources,
                "total_views": total_views,
                "shorts_feed_views": shorts_views,
                "shorts_feed_share": shorts_share,
            }
    except Exception as e:
        print(f"  Analytics: Traffic source query failed for {video_id}: {e}")
        return None


def query_audience_retention(video_id, access_token=None):
    """Query per-video audience retention curve.

    Returns list of {elapsed_pct, watch_ratio, relative_perf} dicts.
    Segments where watch_ratio > 1 indicate rewatching.
    """
    if not access_token:
        return None

    url = (f"{ANALYTICS_API}?ids=channel==MINE"
           f"&startDate=2020-01-01"
           f"&endDate={datetime.now().strftime('%Y-%m-%d')}"
           f"&metrics=audienceWatchRatio,relativeRetentionPerformance"
           f"&dimensions=elapsedVideoTimeRatio"
           f"&filters=video=={video_id}")

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            rows = data.get("rows", [])
            return [
                {
                    "elapsed_pct": row[0],
                    "watch_ratio": row[1],
                    "relative_perf": row[2] if len(row) > 2 else 0,
                }
                for row in rows
            ]
    except Exception as e:
        print(f"  Analytics: Retention query failed for {video_id}: {e}")
        return None


def query_channel_overview(channel_id=None, days=28, access_token=None):
    """Get channel-level performance overview."""
    if not access_token:
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

    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

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


# ---------------------------------------------------------------------------
# Reward computation
# ---------------------------------------------------------------------------

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

    # CTR value (0-10 points) — packaging effectiveness
    ctr = metrics.get("ctr", 0)
    if ctr > 0:
        ctr_score = min(ctr / 10.0, 1.0) * 10
    else:
        ctr_score = 0
    components["ctr"] = ctr_score

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


def compute_shorts_reward(metrics, costs=None, risk_scores=None):
    """Shorts-specific reward function with different weights.

    Shorts prioritize retention and engagement rate over raw watch time.
    Range: [-25, 75], normalized separately from long-form.
    """
    if not metrics or not metrics.get("data_available"):
        return {"total_reward": 0, "components": {}, "confidence": "no_data"}

    components = {}
    views = max(metrics.get("views", 1), 1)

    # Retention (0-30 points) — most important for shorts
    avg_pct = metrics.get("averageViewPercentage", 0)
    retention_score = min(avg_pct / 70, 1.0) * 30  # 70%+ = max
    components["retention"] = retention_score

    # Engaged view rate (0-20 points)
    engaged = metrics.get("engagedViews", 0)
    if engaged > 0:
        engaged_rate = engaged / views
        engaged_score = min(engaged_rate / 0.5, 1.0) * 20  # 50%+ engaged = max
    else:
        engaged_score = 0
    components["engaged_view_rate"] = engaged_score

    # Shares (0-15 points) — virality signal
    shares = metrics.get("shares", 0)
    share_rate = shares / views
    share_score = min(share_rate / 0.02, 1.0) * 15  # 2%+ share rate = max
    components["shares"] = share_score

    # Subscriber conversion (0-10 points)
    subs_gained = metrics.get("subscribersGained", 0)
    subs_lost = metrics.get("subscribersLost", 0)
    net_subs = subs_gained - subs_lost
    sub_score = min(max(net_subs, 0) / 5, 1.0) * 10  # 5+ net subs = max
    components["subscriber_growth"] = sub_score

    # Cost penalty (0 to -5) — shorts are cheaper
    if costs:
        total_cost = costs.get("total_cost_usd", 0)
        cost_penalty = -min(total_cost / 2, 5)
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

    if views < 10:     confidence = "very_low"
    elif views < 100:  confidence = "low"
    elif views < 1000: confidence = "medium"
    else:              confidence = "high"

    return {
        "total_reward": round(total, 2),
        "components": {k: round(v, 2) for k, v in components.items()},
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Metrics pull + storage
# ---------------------------------------------------------------------------

def pull_metrics_and_store(video_name, youtube_video_id, window="7d",
                           access_token=None):
    """Pull metrics from YouTube Analytics and store in telemetry DB.

    Args:
        video_name: Pipeline video name (for DB lookup)
        youtube_video_id: YouTube video ID
        window: "6h", "24h", "48h", "7d", "28d" — determines date range
        access_token: OAuth token for the channel that owns this video
    """
    from utils.telemetry import log_metrics

    window_days = {
        "6h": 1, "24h": 1, "48h": 2, "7d": 7, "14d": 14, "28d": 28
    }
    days = window_days.get(window, 7)

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    metrics = query_video_metrics(youtube_video_id, start_date, end_date,
                                  access_token=access_token)

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

    # Look up video row for is_short and cost/risk context
    from utils.telemetry import _get_db
    video_row = None
    costs = None
    risk_scores = None
    try:
        conn = _get_db()
        video_row = conn.execute(
            "SELECT * FROM videos WHERE video_name = ?", (video_name,)
        ).fetchone()
        conn.close()
    except Exception:
        pass

    # Use shorts-specific reward for shorts
    metrics_data = metrics
    is_short = video_row["is_short"] if video_row and "is_short" in video_row.keys() else 0
    if is_short:
        reward_result = compute_shorts_reward(metrics_data, costs, risk_scores)
    else:
        reward_result = compute_reward(metrics_data, costs, risk_scores)

    reward = reward_result
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

    # Store traffic source data
    try:
        traffic = query_traffic_sources(youtube_video_id,
                                        access_token=access_token)
        if traffic:
            conn = _get_db()
            conn.execute("""
                UPDATE metrics SET shorts_feed_share = ?
                WHERE video_name = ? AND window = ?
            """, (traffic.get("shorts_feed_share", 0), video_name, window))
            conn.commit()
            conn.close()
    except Exception:
        pass

    # Update bandit arm if this video has one assigned
    try:
        from utils.bandits import update_arm
        conn = _get_db()
        row = conn.execute(
            "SELECT template_arm FROM videos WHERE video_name = ?", (video_name,)
        ).fetchone()
        conn.close()
        if row and row["template_arm"]:
            update_arm(row["template_arm"], reward["total_reward"], video_name)
            print(f"  Bandit: Updated arm {row['template_arm']} with reward {reward['total_reward']:.1f}")
    except Exception:
        pass  # Bandits not critical path

    # Update shorts-specific arm if applicable
    if is_short and video_row:
        shorts_arm = video_row.get("shorts_arm")
        if shorts_arm:
            try:
                from utils.bandits import update_arm
                normalized = (reward_result["total_reward"] - (-25)) / (75 - (-25))
                normalized = max(0, min(1, normalized))
                update_arm(shorts_arm, normalized, video_name)
            except Exception:
                pass

    return metrics


def pull_all_published_metrics(window="7d"):
    """Pull metrics for all published videos and store in telemetry DB.

    Groups videos by channel and uses the correct per-channel OAuth token
    for each YouTube Analytics API call.
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

    if not published:
        print("  Analytics: No published videos to pull metrics for")
        return

    print(f"  Analytics: Pulling {window} metrics for {len(published)} published videos")

    # Refresh all channel tokens once
    token_cache = _refresh_all_channel_tokens()

    # Group videos by channel for efficient token lookup
    by_channel = defaultdict(list)
    for entry in published:
        by_channel[entry["channel"]].append(entry)

    fetched = 0
    no_data = 0
    no_token = 0

    for channel_prefix, entries in sorted(by_channel.items()):
        access_token, channel_id = _get_token_for_channel(
            channel_prefix, token_cache
        )

        if not access_token:
            # Try to see if the channel was uploaded via the default token
            # (e.g. RichArt). Skip these — we can't query analytics without
            # a channel-specific token.
            no_token += len(entries)
            if len(entries) > 0:
                print(f"  Analytics: No token for {channel_prefix} "
                      f"({len(entries)} videos) — skipping")
            continue

        for entry in entries:
            video_name = os.path.splitext(entry["file"])[0]
            video_id = entry["video_id"]
            result = pull_metrics_and_store(
                video_name, video_id, window, access_token=access_token
            )
            if result and result.get("data_available"):
                fetched += 1
            else:
                no_data += 1

    print(f"  Analytics: Done — {fetched} with data, {no_data} no data yet, "
          f"{no_token} skipped (no token)")
