"""Thompson Sampling multi-armed bandit for video packaging optimization.

Optimizes the combination of voice profile, script format, and thumbnail style
per channel. Uses Beta distributions for exploration/exploitation.

The template_arms table in the telemetry DB stores arm statistics.
The decisions table logs every arm selection for audit trail.
"""

import json
import os
import random
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default thumbnail styles for arm creation
THUMBNAIL_STYLES = {
    "bold_text": {
        "layout": "text_dominant",
        "font_size": "large",
        "contrast": "high",
        "emoji": False,
    },
    "clean_minimal": {
        "layout": "image_focus",
        "font_size": "medium",
        "contrast": "medium",
        "emoji": False,
    },
    "curiosity_gap": {
        "layout": "split",
        "font_size": "large",
        "contrast": "high",
        "emoji": True,
    },
}

# Reward normalization range (from compute_reward: min=-20, max=80 with CTR term)
REWARD_MIN = -20
REWARD_MAX = 80


def _get_db():
    """Get database connection via telemetry module."""
    from utils.telemetry import _get_db as telemetry_db
    return telemetry_db()


def _normalize_reward(raw_reward):
    """Normalize reward from [-20, 80] to [0, 1] for Beta distribution.

    Args:
        raw_reward: Raw reward from compute_reward()

    Returns:
        Float in [0, 1]
    """
    return max(0.0, min(1.0, (raw_reward - REWARD_MIN) / (REWARD_MAX - REWARD_MIN)))


def _thompson_sample(alpha, beta_param):
    """Sample from Beta(alpha, beta) distribution.

    Args:
        alpha: Success count + 1 (prior)
        beta_param: Failure count + 1 (prior)

    Returns:
        Sampled value in [0, 1]
    """
    return random.betavariate(max(alpha, 0.01), max(beta_param, 0.01))


def initialize_arms(channel_id, channel_config=None):
    """Create initial arms for a channel from its config.

    Generates arms from existing voice profiles and thumbnail styles.
    Skips arms that already exist in the database.

    Args:
        channel_id: Channel key (e.g., 'rich_tech')
        channel_config: Optional channel config dict. If None, loads from channels_config.json.

    Returns:
        List of created arm dicts
    """
    if channel_config is None:
        config_path = os.path.join(BASE_DIR, "channels_config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                full_config = json.load(f)
            channel_config = full_config.get("channels", {}).get(channel_id, {})

    voice_profile = channel_config.get("voice_profile", "neutral_male")
    formats = channel_config.get("formats", ["listicle", "explainer"])

    conn = _get_db()
    created = []

    for fmt in formats:
        for thumb_name, thumb_config in THUMBNAIL_STYLES.items():
            arm_name = f"{channel_id}__{voice_profile}__{fmt}__{thumb_name}"
            config = {
                "channel_id": channel_id,
                "voice_profile": voice_profile,
                "format": fmt,
                "thumbnail_style": thumb_name,
                "thumbnail_config": thumb_config,
            }

            try:
                conn.execute("""
                    INSERT OR IGNORE INTO template_arms
                    (arm_name, arm_type, config, total_pulls, total_reward, avg_reward, active)
                    VALUES (?, ?, ?, 0, 0, 0, 1)
                """, (arm_name, "packaging", json.dumps(config)))
                created.append({"arm_name": arm_name, "config": config})
            except sqlite3.IntegrityError:
                pass  # Already exists

    conn.commit()
    conn.close()
    return created


def select_arm(channel_id, context=None):
    """Select an arm using Thompson Sampling.

    For each active arm matching the channel:
    1. Compute alpha = (avg_reward * total_pulls) + 1
    2. Compute beta = ((1 - avg_reward) * total_pulls) + 1
    3. Sample from Beta(alpha, beta)
    4. Pick the arm with the highest sample

    If no arms exist for the channel, initializes them first.

    Args:
        channel_id: Channel key
        context: Optional context dict (unused for now, reserved for contextual bandits)

    Returns:
        dict with arm_name, config, sampled_value, exploration_info
    """
    conn = _get_db()

    # Get active arms for this channel
    rows = conn.execute("""
        SELECT arm_name, config, total_pulls, total_reward, avg_reward
        FROM template_arms
        WHERE active = 1 AND arm_name LIKE ?
    """, (f"{channel_id}__%",)).fetchall()

    if not rows:
        # Initialize arms for this channel
        conn.close()
        initialize_arms(channel_id)
        conn = _get_db()
        rows = conn.execute("""
            SELECT arm_name, config, total_pulls, total_reward, avg_reward
            FROM template_arms
            WHERE active = 1 AND arm_name LIKE ?
        """, (f"{channel_id}__%",)).fetchall()

    if not rows:
        conn.close()
        return {"error": f"No arms available for channel {channel_id}"}

    # Thompson Sampling
    best_arm = None
    best_sample = -1

    candidates = []
    for row in rows:
        pulls = row["total_pulls"]
        avg = row["avg_reward"] if row["avg_reward"] else 0.5

        # Beta distribution parameters
        alpha = (avg * pulls) + 1
        beta_param = ((1 - avg) * pulls) + 1
        sampled = _thompson_sample(alpha, beta_param)

        candidates.append({
            "arm_name": row["arm_name"],
            "config": json.loads(row["config"]),
            "total_pulls": pulls,
            "avg_reward": round(avg, 4),
            "sampled_value": round(sampled, 4),
        })

        if sampled > best_sample:
            best_sample = sampled
            best_arm = candidates[-1]

    conn.close()

    # Log the decision
    from utils.telemetry import log_decision
    log_decision(
        video_name=None,
        decision_type="arm_selection",
        objective="maximize_reward",
        chosen_action=best_arm["arm_name"],
        alternatives=json.dumps([c["arm_name"] for c in candidates]),
        expected_impact=f"sampled_value={best_sample:.4f}",
        risk_rating="low",
    )

    return {
        "arm_name": best_arm["arm_name"],
        "config": best_arm["config"],
        "sampled_value": best_arm["sampled_value"],
        "total_candidates": len(candidates),
        "exploration_rate": sum(1 for c in candidates if c["total_pulls"] < 3) / len(candidates),
    }


def select_arm_by_type(channel_id, arm_type, context=None):
    """Thompson Sampling selection filtered by arm_type.

    Same algorithm as select_arm() but only considers arms matching
    the specified arm_type.
    """
    conn = _get_db()
    try:
        rows = conn.execute("""
            SELECT arm_name, config, total_pulls, total_reward, avg_reward
            FROM template_arms
            WHERE active = 1 AND arm_type = ? AND arm_name LIKE ?
        """, (arm_type, f"{channel_id}__%")).fetchall()

        if not rows:
            # Auto-initialize arms for this type if none exist
            _auto_initialize(channel_id, arm_type, conn)
            rows = conn.execute("""
                SELECT arm_name, config, total_pulls, total_reward, avg_reward
                FROM template_arms
                WHERE active = 1 AND arm_type = ? AND arm_name LIKE ?
            """, (arm_type, f"{channel_id}__%")).fetchall()

        if not rows:
            return {"error": f"No arms found for {channel_id}/{arm_type}"}

        best_arm = None
        best_sample = -1

        for row in rows:
            pulls = row["total_pulls"]
            avg = row["avg_reward"]
            alpha = (avg * pulls) + 1
            beta_val = ((1 - avg) * pulls) + 1
            sampled = random.betavariate(max(alpha, 0.01), max(beta_val, 0.01))
            if sampled > best_sample:
                best_sample = sampled
                best_arm = row

        arm_name = best_arm["arm_name"]
        config = json.loads(best_arm["config"]) if best_arm["config"] else {}

        # Log the decision
        from utils.telemetry import log_decision
        log_decision(
            video_name="",
            decision_type=f"{arm_type}_selection",
            objective=f"optimize_{arm_type}",
            chosen_action=arm_name,
            expected_impact=f"sampled={best_sample:.4f}",
        )

        return {
            "arm_name": arm_name,
            "arm_type": arm_type,
            "config": config,
            "sampled_value": best_sample,
        }
    finally:
        conn.close()


# --- Arm type definitions ---

TITLE_FORMULAS = [
    "I Tried {topic} for 30 Days...",
    "{topic}: The Complete Beginner's Guide ({year})",
    "Stop Making This {topic} Mistake...",
    "{number} {topic} Tips That Actually Work",
    "Why {topic} Is Not What You Think",
    "The Truth About {topic} Nobody Tells You",
    "How I {topic} (Step by Step)",
    "{topic} in {year}: Everything Changed",
    "Watch This Before You {topic}",
    "I Was Wrong About {topic}",
    "{number} {topic} Hacks You Need to Know",
    "The Ultimate {topic} Guide for Beginners",
]

HOOK_CATEGORIES = [
    "curiosity_gap", "pattern_interrupt", "bold_claim",
    "personal_story", "social_proof", "controversy", "value_promise",
]

SHORTS_CROP_STRATEGIES = ["center", "left_third", "right_third"]
SHORTS_CAPTION_STYLES = ["capcut", "minimal", "karaoke"]
SHORTS_CAPTION_POSITIONS = ["center", "bottom", "top"]

VOICE_PARAM_PRESETS = {
    "default": {"stability": 0.55, "speed": 1.0, "style": 0.25},
    "high_energy": {"stability": 0.25, "speed": 1.1, "style": 0.55},
    "calm_authority": {"stability": 0.65, "speed": 0.95, "style": 0.15},
    "conversational": {"stability": 0.40, "speed": 1.0, "style": 0.35},
    "dramatic": {"stability": 0.35, "speed": 0.95, "style": 0.45},
}

POSTING_SLOTS = [
    "weekday_morning", "weekday_noon", "weekday_afternoon",
    "weekday_evening", "weekend_morning", "weekend_afternoon",
    "weekend_evening",
]


def _auto_initialize(channel_id, arm_type, conn):
    """Auto-initialize arms for a given type when none exist."""
    if arm_type == "title_formula":
        _init_arms(conn, channel_id, arm_type,
                   [(str(i), {"formula_index": i, "formula": f})
                    for i, f in enumerate(TITLE_FORMULAS)])
    elif arm_type == "hook_category":
        _init_arms(conn, channel_id, arm_type,
                   [(cat, {"hook_category": cat}) for cat in HOOK_CATEGORIES])
    elif arm_type == "shorts_config":
        configs = []
        for crop in SHORTS_CROP_STRATEGIES:
            for style in SHORTS_CAPTION_STYLES:
                for pos in SHORTS_CAPTION_POSITIONS:
                    key = f"{crop}_{style}_{pos}"
                    configs.append((key, {
                        "crop_strategy": crop,
                        "caption_style": style,
                        "caption_position": pos,
                    }))
        _init_arms(conn, channel_id, arm_type, configs)
    elif arm_type == "voice_params":
        _init_arms(conn, channel_id, arm_type,
                   [(name, params) for name, params in VOICE_PARAM_PRESETS.items()])
    elif arm_type == "posting_schedule":
        _init_arms(conn, channel_id, arm_type,
                   [(slot, {"posting_slot": slot}) for slot in POSTING_SLOTS])


def _init_arms(conn, channel_id, arm_type, items):
    """Insert arm records for a channel/type combination."""
    for key, config in items:
        arm_name = f"{channel_id}__{arm_type}__{key}"
        try:
            conn.execute("""
                INSERT OR IGNORE INTO template_arms
                (arm_name, arm_type, config, total_pulls, total_reward, avg_reward, active)
                VALUES (?, ?, ?, 0, 0, 0, 1)
            """, (arm_name, arm_type, json.dumps(config)))
        except Exception:
            pass
    conn.commit()


def update_arm(arm_name, reward, video_name=None):
    """Update arm statistics after observing a reward.

    Args:
        arm_name: Arm identifier
        reward: Raw reward from compute_reward() (range: [-20, 70])
        video_name: Associated video name for audit trail

    Returns:
        Updated arm stats dict
    """
    normalized = _normalize_reward(reward)

    conn = _get_db()
    conn.execute("""
        UPDATE template_arms SET
            total_pulls = total_pulls + 1,
            total_reward = total_reward + ?,
            avg_reward = (total_reward + ?) / (total_pulls + 1),
            last_used = ?
        WHERE arm_name = ?
    """, (normalized, normalized, datetime.now().isoformat(), arm_name))
    conn.commit()

    # Fetch updated stats
    row = conn.execute("""
        SELECT arm_name, total_pulls, total_reward, avg_reward
        FROM template_arms WHERE arm_name = ?
    """, (arm_name,)).fetchone()
    conn.close()

    if not row:
        return {"error": f"Arm '{arm_name}' not found"}

    # Log the outcome
    from utils.telemetry import log_decision
    log_decision(
        video_name=video_name,
        decision_type="arm_reward_update",
        objective="update_bandit_stats",
        chosen_action=arm_name,
        expected_impact=f"raw={reward:.2f}, norm={normalized:.4f}, pulls={row['total_pulls']}, avg={row['avg_reward']:.4f}",
    )

    return {
        "arm_name": row["arm_name"],
        "total_pulls": row["total_pulls"],
        "total_reward": round(row["total_reward"], 4),
        "avg_reward": round(row["avg_reward"], 4),
        "last_reward_raw": reward,
        "last_reward_normalized": round(normalized, 4),
    }


def get_arm_report(channel_id=None):
    """Get performance report for all arms.

    Args:
        channel_id: Optional channel filter

    Returns:
        List of arm stats dicts sorted by avg_reward descending
    """
    conn = _get_db()

    if channel_id:
        rows = conn.execute("""
            SELECT arm_name, arm_type, config, total_pulls, total_reward, avg_reward, last_used, active
            FROM template_arms
            WHERE arm_name LIKE ?
            ORDER BY avg_reward DESC
        """, (f"{channel_id}__%",)).fetchall()
    else:
        rows = conn.execute("""
            SELECT arm_name, arm_type, config, total_pulls, total_reward, avg_reward, last_used, active
            FROM template_arms
            ORDER BY avg_reward DESC
        """).fetchall()

    conn.close()

    return [
        {
            "arm_name": r["arm_name"],
            "arm_type": r["arm_type"],
            "config": json.loads(r["config"]) if r["config"] else {},
            "total_pulls": r["total_pulls"],
            "total_reward": round(r["total_reward"], 4) if r["total_reward"] else 0,
            "avg_reward": round(r["avg_reward"], 4) if r["avg_reward"] else 0,
            "last_used": r["last_used"],
            "active": bool(r["active"]),
        }
        for r in rows
    ]


def deactivate_arm(arm_name):
    """Deactivate an underperforming arm.

    Args:
        arm_name: Arm to deactivate

    Returns:
        Success boolean
    """
    conn = _get_db()
    conn.execute("UPDATE template_arms SET active = 0 WHERE arm_name = ?", (arm_name,))
    conn.commit()
    conn.close()
    return True
