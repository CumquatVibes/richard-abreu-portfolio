"""SQLite-backed telemetry for the video production pipeline.

Tracks the full artifact lineage (topic → script → audio → video → upload)
plus per-video costs, risk scores, quality signals, and YouTube performance metrics.

This replaces scattered JSON report files with a queryable database that enables
the learning loop (bandit updates, drift detection, retraining triggers).
"""

import json
import os
import sqlite3
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "output", "pipeline.db")


def _get_db():
    """Get a database connection, creating tables if needed."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _create_tables(conn)
    return conn


def _create_tables(conn):
    """Create all telemetry tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT UNIQUE NOT NULL,
            channel TEXT NOT NULL,
            topic TEXT,
            template_arm TEXT,
            script_path TEXT,
            audio_path TEXT,
            video_path TEXT,
            thumbnail_path TEXT,
            youtube_video_id TEXT,
            status TEXT DEFAULT 'planned',
            created_at TEXT DEFAULT (datetime('now')),
            published_at TEXT,

            -- Script metrics
            script_word_count INTEGER,
            script_visual_count INTEGER,

            -- Production metrics
            audio_duration_sec REAL,
            audio_size_kb REAL,
            video_duration_sec REAL,
            video_size_mb REAL,
            broll_generated INTEGER,
            broll_failed INTEGER,
            segment_duration REAL,

            -- Cost tracking
            tts_characters INTEGER,
            tts_cost_usd REAL,
            broll_api_calls INTEGER,
            broll_cost_usd REAL,
            thumbnail_api_calls INTEGER,
            render_time_sec REAL,
            youtube_quota_used INTEGER,
            total_cost_usd REAL,

            -- Risk scores (from preflight)
            risk_policy REAL,
            risk_copyright REAL,
            risk_misleading REAL,
            risk_inauthentic REAL,
            preflight_passed INTEGER,

            -- Quality assessment
            quality_score INTEGER,
            quality_details TEXT
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT NOT NULL,
            youtube_video_id TEXT,
            window TEXT NOT NULL,
            pulled_at TEXT DEFAULT (datetime('now')),

            -- YouTube Analytics KPIs
            views INTEGER,
            impressions INTEGER,
            ctr REAL,
            estimated_minutes_watched REAL,
            avg_view_duration_sec REAL,
            avg_view_percentage REAL,
            likes INTEGER,
            comments INTEGER,
            shares INTEGER,
            subscribers_gained INTEGER,
            subscribers_lost INTEGER,

            -- Computed reward
            reward REAL,
            reward_components TEXT,
            confidence TEXT,

            FOREIGN KEY (video_name) REFERENCES videos(video_name)
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT,
            timestamp TEXT DEFAULT (datetime('now')),
            decision_type TEXT NOT NULL,
            objective TEXT,
            alternatives TEXT,
            chosen_action TEXT,
            expected_impact TEXT,
            risk_rating TEXT,
            outcome TEXT,

            FOREIGN KEY (video_name) REFERENCES videos(video_name)
        );

        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT,
            timestamp TEXT DEFAULT (datetime('now')),
            incident_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT,
            resolution TEXT,
            resolved_at TEXT,

            FOREIGN KEY (video_name) REFERENCES videos(video_name)
        );

        CREATE TABLE IF NOT EXISTS template_arms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arm_name TEXT UNIQUE NOT NULL,
            arm_type TEXT NOT NULL,
            config TEXT NOT NULL,
            total_pulls INTEGER DEFAULT 0,
            total_reward REAL DEFAULT 0,
            avg_reward REAL DEFAULT 0,
            last_used TEXT,
            active INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel);
        CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
        CREATE INDEX IF NOT EXISTS idx_metrics_video ON metrics(video_name);
        CREATE INDEX IF NOT EXISTS idx_metrics_window ON metrics(window);
        CREATE INDEX IF NOT EXISTS idx_decisions_video ON decisions(video_name);
        CREATE INDEX IF NOT EXISTS idx_incidents_type ON incidents(incident_type);

        CREATE TABLE IF NOT EXISTS daily_quota (
            date TEXT PRIMARY KEY,
            api_quota_used INTEGER DEFAULT 0,
            upload_count INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS retention_curves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT NOT NULL,
            youtube_video_id TEXT,
            pulled_at TEXT DEFAULT (datetime('now')),
            elapsed_pct REAL,
            audience_watch_ratio REAL,
            relative_retention REAL
        );
        CREATE INDEX IF NOT EXISTS idx_retention_video ON retention_curves(video_name);

        CREATE TABLE IF NOT EXISTS facebook_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT NOT NULL,
            facebook_post_id TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT 'group',
            posted_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_fb_posts_video ON facebook_posts(video_name);
    """)
    conn.commit()

    # Shorts-specific columns (added for shorts module)
    for col_def in [
        "is_short INTEGER DEFAULT 0",
        "source_video TEXT",
        "platform TEXT DEFAULT 'youtube'",
        "caption_style TEXT",
    ]:
        col_name = col_def.split()[0]
        try:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {col_def}")
        except Exception:
            pass  # Column already exists

    # Learning loop columns
    for col_def in [
        ("videos", "caption_position TEXT"),
        ("videos", "crop_strategy TEXT"),
        ("videos", "hook_duration REAL"),
        ("videos", "hook_category TEXT"),
        ("videos", "title_formula TEXT"),
        ("videos", "voice_params TEXT"),
        ("videos", "segment_duration REAL"),
        ("videos", "shorts_arm TEXT"),
        ("videos", "posting_slot TEXT"),
        ("metrics", "engaged_views INTEGER"),
        ("metrics", "shorts_feed_share REAL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {col_def[0]} ADD COLUMN {col_def[1]}")
        except sqlite3.OperationalError:
            pass


# ── Video lifecycle tracking ──

def log_video_planned(video_name, channel, topic=None, template_arm=None):
    """Log a new video entering the pipeline."""
    conn = _get_db()
    conn.execute("""
        INSERT OR IGNORE INTO videos (video_name, channel, topic, template_arm, status)
        VALUES (?, ?, ?, ?, 'planned')
    """, (video_name, channel, topic, template_arm))
    conn.commit()
    conn.close()


def log_video_produced(video_name, **kwargs):
    """Update a video record with production details.

    Accepts any column name as keyword argument:
        script_path, audio_path, video_path, thumbnail_path,
        script_word_count, audio_duration_sec, video_duration_sec, video_size_mb,
        broll_generated, broll_failed, segment_duration, render_time_sec,
        tts_characters, tts_cost_usd, broll_api_calls, broll_cost_usd, etc.
    """
    if not kwargs:
        return

    conn = _get_db()

    # Ensure video exists
    conn.execute("""
        INSERT OR IGNORE INTO videos (video_name, channel, status)
        VALUES (?, ?, 'producing')
    """, (video_name, kwargs.pop("channel", "unknown")))

    sets = []
    vals = []
    for key, val in kwargs.items():
        sets.append(f"{key} = ?")
        vals.append(val)

    if sets:
        vals.append(video_name)
        conn.execute(f"""
            UPDATE videos SET {', '.join(sets)}, status = 'produced'
            WHERE video_name = ?
        """, vals)

    conn.commit()
    conn.close()


def log_video_preflight(video_name, preflight_result):
    """Log preflight compliance check result."""
    conn = _get_db()
    scores = preflight_result.get("risk_scores", {})
    conn.execute("""
        UPDATE videos SET
            risk_policy = ?,
            risk_copyright = ?,
            risk_misleading = ?,
            risk_inauthentic = ?,
            preflight_passed = ?,
            status = ?
        WHERE video_name = ?
    """, (
        scores.get("policy", 0),
        scores.get("copyright", 0),
        scores.get("misleading_metadata", 0),
        scores.get("inauthentic_content", 0),
        1 if preflight_result["publishable"] else 0,
        "preflight_passed" if preflight_result["publishable"] else "preflight_failed",
        video_name,
    ))
    conn.commit()
    conn.close()


def log_video_published(video_name, youtube_video_id, quota_used=None):
    """Log successful YouTube upload."""
    conn = _get_db()
    conn.execute("""
        UPDATE videos SET
            youtube_video_id = ?,
            youtube_quota_used = ?,
            status = 'published',
            published_at = datetime('now')
        WHERE video_name = ?
    """, (youtube_video_id, quota_used, video_name))
    conn.commit()
    conn.close()


def get_daily_quota(date_str=None):
    """Get today's quota usage. Returns (api_quota_used, upload_count)."""
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    conn = _get_db()
    row = conn.execute(
        "SELECT api_quota_used, upload_count FROM daily_quota WHERE date = ?",
        (date_str,)
    ).fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return 0, 0


def record_quota_usage(api_units, date_str=None):
    """Record quota usage for today. Adds to existing total."""
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    conn = _get_db()
    conn.execute("""
        INSERT INTO daily_quota (date, api_quota_used, upload_count, updated_at)
        VALUES (?, ?, 1, datetime('now'))
        ON CONFLICT(date) DO UPDATE SET
            api_quota_used = api_quota_used + excluded.api_quota_used,
            upload_count = upload_count + 1,
            updated_at = datetime('now')
    """, (date_str, api_units))
    conn.commit()
    conn.close()


def log_video_quality(video_name, score, details=None):
    """Log quality assessment score."""
    conn = _get_db()
    conn.execute("""
        UPDATE videos SET quality_score = ?, quality_details = ?
        WHERE video_name = ?
    """, (score, json.dumps(details) if details else None, video_name))
    conn.commit()
    conn.close()


def log_short_produced(video_name, channel, source_video=None, platform="youtube",
                       caption_style=None, video_duration_sec=None, video_size_mb=None,
                       shorts_arm=None, crop_strategy=None, caption_position=None):
    """Log a short video production with parent lineage."""
    conn = _get_db()
    conn.execute("""
        INSERT OR IGNORE INTO videos (video_name, channel, status, is_short,
                                       source_video, platform, caption_style,
                                       video_duration_sec, video_size_mb,
                                       shorts_arm, crop_strategy, caption_position)
        VALUES (?, ?, 'produced', 1, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (video_name, channel, source_video, platform, caption_style,
          video_duration_sec, video_size_mb, shorts_arm, crop_strategy,
          caption_position))
    conn.commit()
    conn.close()


# ── Cost tracking ──

def update_costs(video_name, **cost_kwargs):
    """Update cost fields and recompute total_cost_usd."""
    conn = _get_db()

    sets = []
    vals = []
    for key, val in cost_kwargs.items():
        sets.append(f"{key} = ?")
        vals.append(val)

    if sets:
        vals.append(video_name)
        conn.execute(f"UPDATE videos SET {', '.join(sets)} WHERE video_name = ?", vals)

    # Recompute total
    conn.execute("""
        UPDATE videos SET total_cost_usd = COALESCE(tts_cost_usd, 0) + COALESCE(broll_cost_usd, 0)
        WHERE video_name = ?
    """, (video_name,))

    conn.commit()
    conn.close()


# ── Metrics / Analytics ──

def log_metrics(video_name, window, youtube_video_id=None, **metric_kwargs):
    """Log YouTube Analytics metrics for a video at a specific time window.

    window: "6h", "24h", "48h", "7d", "28d"
    """
    conn = _get_db()
    cols = ["video_name", "youtube_video_id", "window"]
    vals = [video_name, youtube_video_id, window]

    for key, val in metric_kwargs.items():
        cols.append(key)
        vals.append(val)

    placeholders = ", ".join(["?"] * len(vals))
    col_str = ", ".join(cols)
    conn.execute(f"INSERT INTO metrics ({col_str}) VALUES ({placeholders})", vals)
    conn.commit()
    conn.close()


# ── Decision logging ──

def log_decision(video_name, decision_type, objective, chosen_action,
                 alternatives=None, expected_impact=None, risk_rating=None):
    """Log a pipeline decision for audit trail."""
    conn = _get_db()
    conn.execute("""
        INSERT INTO decisions (video_name, decision_type, objective, alternatives,
                              chosen_action, expected_impact, risk_rating)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (video_name, decision_type, objective,
          json.dumps(alternatives) if alternatives else None,
          chosen_action, expected_impact, risk_rating))
    conn.commit()
    conn.close()


# ── Incidents ──

def log_incident(video_name, incident_type, severity, description):
    """Log a pipeline incident (policy violation, copyright claim, anomaly)."""
    conn = _get_db()
    conn.execute("""
        INSERT INTO incidents (video_name, incident_type, severity, description)
        VALUES (?, ?, ?, ?)
    """, (video_name, incident_type, severity, description))
    conn.commit()
    conn.close()


# ── Retention curves ──

def log_retention_curve(video_name, youtube_video_id, retention_data):
    """Store audience retention curve data for a video.

    Args:
        retention_data: list of {elapsed_pct, watch_ratio, relative_perf} dicts
    """
    if not retention_data:
        return
    conn = _get_db()
    try:
        for point in retention_data:
            conn.execute("""
                INSERT INTO retention_curves (video_name, youtube_video_id,
                    elapsed_pct, audience_watch_ratio, relative_retention)
                VALUES (?, ?, ?, ?, ?)
            """, (video_name, youtube_video_id,
                  point.get("elapsed_pct", 0),
                  point.get("watch_ratio", 0),
                  point.get("relative_perf", 0)))
        conn.commit()
    finally:
        conn.close()


def get_retention_curve(video_name):
    """Retrieve stored retention curve for a video."""
    conn = _get_db()
    try:
        rows = conn.execute("""
            SELECT elapsed_pct, audience_watch_ratio, relative_retention
            FROM retention_curves
            WHERE video_name = ?
            ORDER BY elapsed_pct
        """, (video_name,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Queries for learning loop ──

def get_recent_performance(n_videos=20):
    """Get performance summary for last N published videos."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT v.video_name, v.channel, v.template_arm, v.quality_score,
               v.video_duration_sec, v.total_cost_usd,
               m.views, m.impressions, m.ctr, m.estimated_minutes_watched,
               m.avg_view_duration_sec, m.avg_view_percentage,
               m.likes, m.comments, m.shares,
               m.subscribers_gained, m.subscribers_lost,
               m.reward, m.window
        FROM videos v
        LEFT JOIN metrics m ON v.video_name = m.video_name
            AND m.window = (SELECT MAX(window) FROM metrics WHERE video_name = v.video_name)
        WHERE v.status = 'published'
        ORDER BY v.published_at DESC
        LIMIT ?
    """, (n_videos,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_arm_performance():
    """Get performance stats per template arm for bandit updates."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT arm_name, arm_type, total_pulls, total_reward, avg_reward, active
        FROM template_arms
        ORDER BY avg_reward DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_channel_summary(channel=None):
    """Get production and performance summary per channel."""
    conn = _get_db()
    where = "WHERE v.channel = ?" if channel else ""
    params = (channel,) if channel else ()
    rows = conn.execute(f"""
        SELECT v.channel,
               COUNT(*) as total_videos,
               SUM(CASE WHEN v.status = 'published' THEN 1 ELSE 0 END) as published,
               AVG(v.quality_score) as avg_quality,
               AVG(v.total_cost_usd) as avg_cost,
               AVG(v.video_duration_sec) / 60.0 as avg_duration_min,
               SUM(v.total_cost_usd) as total_cost
        FROM videos v
        {where}
        GROUP BY v.channel
        ORDER BY published DESC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cost_report(days=30):
    """Get cost breakdown for the last N days."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT
            COUNT(*) as videos_produced,
            SUM(tts_cost_usd) as total_tts,
            SUM(broll_cost_usd) as total_broll,
            SUM(total_cost_usd) as total_cost,
            SUM(broll_api_calls) as total_broll_calls,
            SUM(tts_characters) as total_tts_chars,
            SUM(youtube_quota_used) as total_quota,
            AVG(total_cost_usd) as avg_cost_per_video
        FROM videos
        WHERE created_at >= datetime('now', ?)
    """, (f"-{days} days",)).fetchone()
    conn.close()
    return dict(rows) if rows else {}


def detect_performance_drift(n_recent=5, n_baseline=20, threshold=0.15):
    """Detect if recent video performance has drifted from baseline.

    Returns dict with drift_detected (bool), metrics comparison, and confidence.
    """
    conn = _get_db()

    recent = conn.execute("""
        SELECT AVG(m.reward) as avg_reward, COUNT(*) as count
        FROM videos v
        JOIN metrics m ON v.video_name = m.video_name
        WHERE v.status = 'published'
        AND m.window IN ('7d', '28d')
        ORDER BY v.published_at DESC
        LIMIT ?
    """, (n_recent,)).fetchone()

    baseline = conn.execute("""
        SELECT AVG(m.reward) as avg_reward, COUNT(*) as count
        FROM videos v
        JOIN metrics m ON v.video_name = m.video_name
        WHERE v.status = 'published'
        AND m.window IN ('7d', '28d')
        ORDER BY v.published_at DESC
        LIMIT ? OFFSET ?
    """, (n_baseline, n_recent)).fetchone()

    conn.close()

    if not recent or not baseline or not baseline["avg_reward"]:
        return {"drift_detected": False, "reason": "insufficient_data"}

    pct_change = (recent["avg_reward"] - baseline["avg_reward"]) / abs(baseline["avg_reward"])

    return {
        "drift_detected": abs(pct_change) > threshold,
        "direction": "regression" if pct_change < -threshold else "improvement" if pct_change > threshold else "stable",
        "pct_change": pct_change,
        "recent_avg_reward": recent["avg_reward"],
        "baseline_avg_reward": baseline["avg_reward"],
        "recent_count": recent["count"],
        "baseline_count": baseline["count"],
    }


# ── Facebook group posting tracking ──

def log_facebook_post(video_name, facebook_post_id, target="group"):
    """Record that a video was shared to Facebook (page or group)."""
    conn = _get_db()
    conn.execute(
        "INSERT INTO facebook_posts (video_name, facebook_post_id, target) VALUES (?, ?, ?)",
        (video_name, facebook_post_id, target),
    )
    conn.commit()
    conn.close()


def was_posted_to_facebook(video_name, target=None):
    """Check if a video was already shared to Facebook. Optionally filter by target."""
    conn = _get_db()
    if target:
        row = conn.execute(
            "SELECT 1 FROM facebook_posts WHERE video_name = ? AND target = ? LIMIT 1",
            (video_name, target),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM facebook_posts WHERE video_name = ? LIMIT 1",
            (video_name,),
        ).fetchone()
    conn.close()
    return row is not None
