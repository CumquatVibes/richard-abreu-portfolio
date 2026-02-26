"""ViewStats API integration for channel analytics and competitive intelligence.

Uses the ViewStats HTTP API (Bearer token auth) to pull:
- Channel stats (views, subs, revenue over time)
- Channel projections (growth forecasts)
- Similar channels (competitive landscape)

Token: Grab from browser DevTools → Network tab → any ViewStats request → Authorization header.
Store in .env as VIEWSTATS_TOKEN.
"""

import json
import os
import sqlite3
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "output", "pipeline.db")
VIEWSTATS_API = "https://api.viewstats.com"


def _get_token():
    """Get ViewStats Bearer token from env."""
    token = os.environ.get("VIEWSTATS_TOKEN")
    if not token:
        # Try loading from .env
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("VIEWSTATS_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        break
    return token


def _api_request(endpoint, params=None):
    """Make authenticated GET request to ViewStats API."""
    token = _get_token()
    if not token:
        print("  ViewStats: No VIEWSTATS_TOKEN found in env or .env")
        return None

    url = f"{VIEWSTATS_API}{endpoint}"
    if params:
        url += "?" + urlencode(params)

    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        print(f"  ViewStats API error {e.code}: {body[:200]}")
        return None
    except Exception as e:
        print(f"  ViewStats request failed: {str(e)[:150]}")
        return None


def get_channel_stats(handle, range_days=28, group_by="daily"):
    """Get channel performance stats over a time range.

    Args:
        handle: YouTube handle (e.g. "facelessprof" or "@facelessprof")
        range_days: Number of days (7, 28, 90, 365)
        group_by: "daily" or "monthly"

    Returns:
        dict with stats data or None
    """
    handle = handle.lstrip("@")
    return _api_request(f"/channels/@{handle}/stats", {
        "range": str(range_days),
        "groupBy": group_by,
        "sortOrder": "ASC",
        "withRevenue": "true",
        "withEvents": "true",
        "withBreakdown": "false",
        "withToday": "false",
    })


def get_channel_projections(handle):
    """Get growth projections for a channel.

    Args:
        handle: YouTube handle

    Returns:
        dict with projection data or None
    """
    handle = handle.lstrip("@")
    return _api_request(f"/channels/@{handle}/projections")


def get_similar_channels(handle):
    """Get channels similar to the given one (competitive landscape).

    Args:
        handle: YouTube handle

    Returns:
        dict with similar channels or None
    """
    handle = handle.lstrip("@")
    return _api_request(f"/channels/@{handle}/similar")


def get_channel_overview(handle):
    """Get basic channel overview info.

    Args:
        handle: YouTube handle

    Returns:
        dict with channel metadata or None
    """
    handle = handle.lstrip("@")
    return _api_request(f"/channels/@{handle}")


def _ensure_viewstats_table():
    """Create viewstats_snapshots table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS viewstats_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_handle TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            range_days INTEGER DEFAULT 28,
            subscribers INTEGER,
            total_views INTEGER,
            avg_daily_views INTEGER,
            avg_daily_subs INTEGER,
            estimated_revenue_low REAL,
            estimated_revenue_high REAL,
            raw_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS viewstats_similar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_handle TEXT NOT NULL,
            similar_handle TEXT,
            similar_name TEXT,
            subscribers INTEGER,
            avg_daily_views INTEGER,
            similarity_score REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def pull_and_store_stats(handle, range_days=28):
    """Pull channel stats from ViewStats and store in pipeline DB.

    Args:
        handle: YouTube handle
        range_days: Time range

    Returns:
        dict with parsed stats or None
    """
    _ensure_viewstats_table()

    data = get_channel_stats(handle, range_days)
    if not data:
        return None

    # Extract summary metrics from response
    # ViewStats response structure varies; store raw + extract what we can
    parsed = {
        "handle": handle,
        "range_days": range_days,
        "raw": data,
    }

    # Try to extract common fields
    if isinstance(data, dict):
        parsed["subscribers"] = data.get("subscribers") or data.get("subscriberCount")
        parsed["total_views"] = data.get("totalViews") or data.get("viewCount")

        # Look for daily averages in stats arrays
        stats = data.get("stats") or data.get("data") or []
        if stats and isinstance(stats, list):
            views_list = [s.get("views", 0) for s in stats if isinstance(s, dict)]
            subs_list = [s.get("subscribers", 0) or s.get("subscribersGained", 0) for s in stats if isinstance(s, dict)]
            if views_list:
                parsed["avg_daily_views"] = sum(views_list) // len(views_list)
            if subs_list:
                parsed["avg_daily_subs"] = sum(subs_list) // len(subs_list)

        # Revenue estimates
        parsed["revenue_low"] = data.get("estimatedRevenueLow") or data.get("revenueLow")
        parsed["revenue_high"] = data.get("estimatedRevenueHigh") or data.get("revenueHigh")

    # Store in DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO viewstats_snapshots
        (channel_handle, snapshot_date, range_days, subscribers, total_views,
         avg_daily_views, avg_daily_subs, estimated_revenue_low, estimated_revenue_high, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        handle,
        datetime.now().strftime("%Y-%m-%d"),
        range_days,
        parsed.get("subscribers"),
        parsed.get("total_views"),
        parsed.get("avg_daily_views"),
        parsed.get("avg_daily_subs"),
        parsed.get("revenue_low"),
        parsed.get("revenue_high"),
        json.dumps(data),
    ))
    conn.commit()
    conn.close()

    print(f"  ViewStats: {handle} ({range_days}d) — "
          f"subs: {parsed.get('subscribers', '?')}, "
          f"avg daily views: {parsed.get('avg_daily_views', '?')}")

    return parsed


def pull_similar_channels(handle):
    """Pull and store similar channels for competitive analysis.

    Returns:
        list of similar channel dicts or None
    """
    _ensure_viewstats_table()

    data = get_similar_channels(handle)
    if not data:
        return None

    channels = data if isinstance(data, list) else data.get("channels") or data.get("data") or []

    conn = sqlite3.connect(DB_PATH)
    stored = 0
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        conn.execute("""
            INSERT INTO viewstats_similar
            (source_handle, similar_handle, similar_name, subscribers, avg_daily_views, similarity_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            handle,
            ch.get("handle") or ch.get("channelHandle"),
            ch.get("name") or ch.get("channelName"),
            ch.get("subscribers") or ch.get("subscriberCount"),
            ch.get("avgDailyViews") or ch.get("averageDailyViews"),
            ch.get("similarityScore") or ch.get("score"),
        ))
        stored += 1
    conn.commit()
    conn.close()

    print(f"  ViewStats: Found {stored} similar channels to @{handle}")
    return channels


def pull_all_channel_stats(handles, range_days=28):
    """Pull stats for multiple channel handles.

    Args:
        handles: List of YouTube handles
        range_days: Time range

    Returns:
        dict mapping handle -> stats
    """
    results = {}
    for handle in handles:
        stats = pull_and_store_stats(handle, range_days)
        if stats:
            results[handle] = stats
    return results
