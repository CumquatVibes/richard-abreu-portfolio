#!/usr/bin/env python3
"""MCP Server for the YouTube Video Production Pipeline.

Exposes pipeline operations as tools for Claude to invoke autonomously.
Uses FastMCP with STDIO transport.

Run: .venv-mcp/bin/python3.13 mcp_server.py
"""

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime
from glob import glob

# Add pipeline dir to path for imports
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPELINE_DIR)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("video-pipeline", instructions="""
YouTube Video Production Pipeline controller.
Manages 38 faceless channels + 1 avatar channel (CumquatVibes).
Use these tools to generate content, produce videos, upload to YouTube,
check analytics, and optimize performance.
""")

# Paths
OUTPUT_DIR = os.path.join(PIPELINE_DIR, "output")
SCRIPTS_DIR = os.path.join(OUTPUT_DIR, "scripts")
AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
VIDEOS_DIR = os.path.join(OUTPUT_DIR, "videos")
BROLL_DIR = os.path.join(OUTPUT_DIR, "broll")
REPORT_DIR = os.path.join(OUTPUT_DIR, "reports")
CHANNELS_CONFIG = os.path.join(PIPELINE_DIR, "channels_config.json")


def _capture(func, *args, **kwargs):
    """Call a function, capturing stdout. Returns (result, captured_output)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = func(*args, **kwargs)
    return result, buf.getvalue()


def _count_files(directory, pattern="*"):
    """Count files matching pattern in directory."""
    if not os.path.isdir(directory):
        return 0
    return len(glob(os.path.join(directory, pattern)))


def _json_response(**kwargs):
    """Format a JSON response string."""
    return json.dumps(kwargs, indent=2, default=str)


# ── Tool 1: Pipeline Status ──

@mcp.tool()
def pipeline_status() -> str:
    """Get current pipeline status: file counts, uploads, costs, and quota usage."""
    scripts = _count_files(SCRIPTS_DIR, "*.txt")
    audio = _count_files(AUDIO_DIR, "*.mp3")
    videos = _count_files(VIDEOS_DIR, "*.mp4")
    thumbnails = _count_files(os.path.join(OUTPUT_DIR, "thumbnails"), "*.png")

    # Upload report
    report_path = os.path.join(REPORT_DIR, "youtube_upload_report.json")
    uploaded = 0
    failed = 0
    if os.path.exists(report_path):
        with open(report_path) as f:
            report = json.load(f)
        for r in report.get("results", []):
            if r.get("status") == "success":
                uploaded += 1
            elif r.get("status") == "failed":
                failed += 1

    # Cost report from telemetry
    cost_info = {}
    try:
        from utils.telemetry import get_cost_report
        cost_info = get_cost_report(30)
    except Exception:
        pass

    return _json_response(
        scripts=scripts,
        audio_files=audio,
        videos=videos,
        thumbnails=thumbnails,
        uploaded_to_youtube=uploaded,
        failed_uploads=failed,
        pending_upload=videos - uploaded,
        cost_report_30d=cost_info,
        timestamp=datetime.now().isoformat(),
    )


# ── Tool 2: List Channels ──

@mcp.tool()
def list_channels(tier: str = "all") -> str:
    """List available YouTube channels and their configuration.

    Args:
        tier: Filter by tier - 'priority', 'secondary', 'growth', or 'all'
    """
    with open(CHANNELS_CONFIG) as f:
        config = json.load(f)

    channels = config.get("channels", {})
    result = []
    for key, ch in channels.items():
        entry = {
            "key": key,
            "name": ch.get("name", key),
            "niche": ch.get("niche", ""),
            "type": ch.get("type", ""),
            "faceless": ch.get("faceless", True),
            "voice_profile": ch.get("voice_profile", ""),
            "formats": ch.get("formats", []),
        }
        if tier == "all" or ch.get("tier", "") == tier:
            result.append(entry)

    return _json_response(count=len(result), channels=result)


# ── Tool 3: Generate Topics ──

@mcp.tool()
def generate_topics(channel_id: str, count: int = 5) -> str:
    """Generate video topic ideas for a channel using Gemini AI.

    Args:
        channel_id: Channel key from channels_config.json (e.g., 'rich_tech', 'rich_horror')
        count: Number of topics to generate (1-20)
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PIPELINE_DIR, "..", "shopify-theme", ".env"))

    with open(CHANNELS_CONFIG) as f:
        config = json.load(f)

    channel = config.get("channels", {}).get(channel_id)
    if not channel:
        return _json_response(error=f"Channel '{channel_id}' not found")

    niche = channel.get("niche", "")
    sub_topics = channel.get("sub_topics", [])
    formats = channel.get("formats", [])

    # Use Gemini to generate topics
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"""Generate {count} YouTube video topic ideas for a channel about: {niche}

Sub-topics to draw from: {', '.join(sub_topics[:10])}
Content formats available: {', '.join(formats[:5])}

Requirements:
- Each topic should be a compelling, click-worthy video title
- Mix evergreen and trending topics
- Include the target number in listicle titles (e.g., "7 Tips...")
- Keep titles under 70 characters
- Make them SEO-friendly for YouTube search

Return ONLY a JSON array of title strings, nothing else."""

    try:
        response = model.generate_content(prompt)
        topics = json.loads(response.text.strip().strip("```json").strip("```"))
        return _json_response(channel=channel_id, count=len(topics), topics=topics)
    except Exception as e:
        return _json_response(error=str(e)[:200])


# ── Tool 4: Generate Script ──

@mcp.tool()
def generate_script(channel_id: str, topic: str, format_type: str = "listicle") -> str:
    """Generate a video script for a specific topic and channel.

    Args:
        channel_id: Channel key (e.g., 'rich_tech')
        topic: Video topic/title
        format_type: Script format ('listicle', 'explainer', 'tutorial', 'compilation', 'news_recap')
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PIPELINE_DIR, "..", "shopify-theme", ".env"))

    with open(CHANNELS_CONFIG) as f:
        config = json.load(f)

    channel = config.get("channels", {}).get(channel_id)
    if not channel:
        return _json_response(error=f"Channel '{channel_id}' not found")

    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    model = genai.GenerativeModel("gemini-2.0-flash")

    ch_name = channel.get("name", channel_id)
    niche = channel.get("niche", "")
    word_target = channel.get("word_count_target", 2000)

    prompt = f"""Write a YouTube video script for the channel "{ch_name}" (niche: {niche}).

Topic: {topic}
Format: {format_type}
Target length: {word_target} words

Script requirements:
- Start with a strong hook (first 15 seconds are critical for retention)
- Include [VISUAL: description] tags for B-roll image generation
- Include [CHAPTER: title] tags for YouTube chapters
- Use conversational, engaging tone
- End with a clear call-to-action
- Include at least 8 visual directions
- Do NOT include any music or sound effect directions
- Write for a voiceover narration (no on-camera references)

At the very top, include:
# Channel: {ch_name}
# Topic: {topic}
"""

    try:
        response = model.generate_content(prompt)
        script_text = response.text

        # Save to file
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        safe_topic = re.sub(r'[^\w\s-]', '', topic).replace(' ', '_')[:80]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = ch_name.replace(" ", "")
        filename = f"{prefix}_{safe_topic}_{timestamp}.txt"
        filepath = os.path.join(SCRIPTS_DIR, filename)

        with open(filepath, "w") as f:
            f.write(script_text)

        word_count = len(script_text.split())
        visual_count = len(re.findall(r'\[VISUAL:', script_text))

        return _json_response(
            channel=channel_id,
            topic=topic,
            filename=filename,
            filepath=filepath,
            word_count=word_count,
            visual_count=visual_count,
        )
    except Exception as e:
        return _json_response(error=str(e)[:200])


# Need re for script generation
import re


# ── Tool 5: Generate Audio ──

@mcp.tool()
def generate_audio(script_name: str) -> str:
    """Generate TTS voiceover for a script via ElevenLabs.

    Args:
        script_name: Script filename in output/scripts/ (with or without .txt)
    """
    if not script_name.endswith(".txt"):
        script_name += ".txt"

    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        return _json_response(error=f"Script not found: {script_path}")

    # Delegate to batch_generate_audio logic
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            from batch_generate_audio import generate_single_audio
            audio_path = generate_single_audio(script_path)
        return _json_response(
            script=script_name,
            audio_path=audio_path,
            logs=buf.getvalue(),
        )
    except ImportError:
        # Fallback: call the script directly
        result = subprocess.run(
            [sys.executable, os.path.join(PIPELINE_DIR, "batch_generate_audio.py")],
            capture_output=True, text=True, cwd=PIPELINE_DIR, timeout=300
        )
        return _json_response(
            script=script_name,
            stdout=result.stdout[-500:] if result.stdout else "",
            stderr=result.stderr[-500:] if result.stderr else "",
            returncode=result.returncode,
        )


# ── Tool 6: Produce Video ──

@mcp.tool()
def produce_video(script_name: str, segment_duration: int = 8, crossfade: float = 0.5) -> str:
    """Produce a video from script + audio: generate B-roll images and assemble with Ken Burns effects.

    Args:
        script_name: Script filename in output/scripts/ (with or without .txt)
        segment_duration: Seconds per B-roll image (default 8)
        crossfade: Crossfade duration between segments in seconds (default 0.5)
    """
    if not script_name.endswith(".txt"):
        script_name += ".txt"

    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        return _json_response(error=f"Script not found: {script_path}")

    basename = os.path.splitext(script_name)[0]

    # Find matching audio
    from utils.common import find_audio_for_script, strip_timestamp
    audio_path, audio_name = find_audio_for_script(basename)
    if not audio_path:
        return _json_response(error=f"No audio found for {script_name}. Expected: {audio_name}")

    # Get channel from filename
    channel = basename.split("_")[0] if "_" in basename else basename

    # Generate B-roll
    broll_dir = os.path.join(BROLL_DIR, strip_timestamp(basename))
    os.makedirs(broll_dir, exist_ok=True)

    buf = io.StringIO()
    with redirect_stdout(buf):
        from utils.broll import generate_broll, get_broll_template
        template = get_broll_template(channel)
        visuals = generate_broll(script_path, broll_dir, channel=channel)

    broll_logs = buf.getvalue()

    # Assemble video
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    video_name = strip_timestamp(basename) + ".mp4"
    video_path = os.path.join(VIDEOS_DIR, video_name)

    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        from utils.assembly import assemble_video
        success, size_mb, duration = assemble_video(
            audio_path, broll_dir, video_path,
            segment_duration=segment_duration,
            crossfade=crossfade,
        )

    return _json_response(
        script=script_name,
        video_path=video_path if success else None,
        success=success,
        size_mb=size_mb,
        duration_sec=duration,
        broll_count=len(glob(os.path.join(broll_dir, "*.png"))),
        logs=broll_logs[-500:] + buf2.getvalue()[-500:],
    )


# ── Tool 7: Upload Video ──

@mcp.tool()
def upload_video(video_name: str, privacy: str = "public") -> str:
    """Upload a produced video to its YouTube channel.

    Args:
        video_name: Video filename in output/videos/ (with or without .mp4)
        privacy: Upload privacy ('public', 'unlisted', 'private')
    """
    # Trigger the upload script for a single video
    result = subprocess.run(
        [sys.executable, os.path.join(PIPELINE_DIR, "upload_to_youtube.py")],
        capture_output=True, text=True, cwd=PIPELINE_DIR, timeout=600,
    )
    return _json_response(
        video=video_name,
        stdout=result.stdout[-1000:] if result.stdout else "",
        stderr=result.stderr[-500:] if result.stderr else "",
        returncode=result.returncode,
    )


# ── Tool 8: Run Preflight ──

@mcp.tool()
def run_preflight(script_name: str, title: str = "", description: str = "") -> str:
    """Run compliance preflight check on a video before upload.

    Args:
        script_name: Script filename in output/scripts/
        title: Video title (auto-generated if empty)
        description: Video description (auto-generated if empty)
    """
    if not script_name.endswith(".txt"):
        script_name += ".txt"

    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        return _json_response(error=f"Script not found: {script_path}")

    with open(script_path) as f:
        script_text = f.read()

    if not title:
        # Extract from script header
        for line in script_text.split("\n")[:5]:
            if line.startswith("# Topic:"):
                title = line.replace("# Topic:", "").strip()
                break
        if not title:
            title = os.path.splitext(script_name)[0].replace("_", " ")

    if not description:
        description = f"Video about: {title}. Created with AI voice and visuals."

    from utils.compliance import preflight_check, format_preflight_report
    result = preflight_check(
        script_text=script_text,
        title=title,
        description=description,
        tags=["ai", "2026"],
        is_synthetic=True,
    )

    return _json_response(
        script=script_name,
        report=format_preflight_report(result),
        publishable=result["publishable"],
        risk_scores=result["risk_scores"],
        violations_count=len(result["violations"]),
        required_fixes=result["required_fixes"],
    )


# ── Tool 9: Check Analytics ──

@mcp.tool()
def check_analytics(window: str = "7d") -> str:
    """Pull YouTube Analytics metrics for all published videos.

    Args:
        window: Time window - '7d' or '28d'
    """
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            from utils.analytics import pull_all_published_metrics
            pull_all_published_metrics(window)
        return _json_response(window=window, logs=buf.getvalue())
    except Exception as e:
        return _json_response(error=str(e)[:200], logs=buf.getvalue())


# ── Tool 10: Get Reward ──

@mcp.tool()
def get_reward(video_id: str) -> str:
    """Compute the multi-objective reward score for a YouTube video.

    Reward components: watch_time (0-20), retention (0-20), engagement (0-15),
    subscriber_growth (0-15), cost_penalty (0 to -10), risk_penalty (0 to -20).

    Args:
        video_id: YouTube video ID
    """
    from utils.analytics import query_video_metrics, compute_reward
    metrics = query_video_metrics(video_id)
    if not metrics:
        return _json_response(error=f"No metrics available for {video_id}")

    reward = compute_reward(metrics)
    return _json_response(
        video_id=video_id,
        metrics=metrics,
        reward=reward,
    )


# ── Tool 11: Detect Drift ──

@mcp.tool()
def detect_drift(n_recent: int = 5, n_baseline: int = 20) -> str:
    """Check if recent video performance has drifted from baseline.

    Compares average reward of recent N videos against baseline.
    Triggers alert if change exceeds 15%.

    Args:
        n_recent: Number of recent videos to compare (default 5)
        n_baseline: Number of baseline videos (default 20)
    """
    from utils.telemetry import detect_performance_drift
    result = detect_performance_drift(n_recent, n_baseline)
    return _json_response(**result)


# ── Tool 12: Get Cost Report ──

@mcp.tool()
def get_cost_report(days: int = 30) -> str:
    """Get cost breakdown for the pipeline over a period.

    Args:
        days: Number of days to report on (default 30)
    """
    from utils.telemetry import get_cost_report as _get_cost_report
    report = _get_cost_report(days)
    return _json_response(days=days, **report)


# ── Tool 13: Run Nightly Pipeline ──

@mcp.tool()
def run_nightly() -> str:
    """Trigger the full nightly pipeline: uploads, thumbnails, drive sync, analytics, optimization.

    This runs the run_channel_optimization.sh script which handles:
    1. Retry failed video uploads
    2. Backfill custom thumbnails
    3. Sync to Google Drive
    4. Pull YouTube Analytics
    5. Run channel optimization
    """
    result = subprocess.run(
        ["bash", os.path.join(PIPELINE_DIR, "run_channel_optimization.sh")],
        capture_output=True, text=True, cwd=PIPELINE_DIR, timeout=600,
    )

    # Read the latest log
    log_pattern = os.path.join(OUTPUT_DIR, "nightly_pipeline_log_*.txt")
    logs = sorted(glob(log_pattern))
    latest_log = ""
    if logs:
        with open(logs[-1]) as f:
            latest_log = f.read()[-2000:]  # Last 2000 chars

    return _json_response(
        returncode=result.returncode,
        log_tail=latest_log,
    )


# ── Tool 14: Optimize Channel ──

@mcp.tool()
def optimize_channel(channel_name: str) -> str:
    """Run SEO optimization for a specific YouTube channel (metadata, description, keywords).

    Args:
        channel_name: Channel name as it appears in channel_tokens.json
    """
    result = subprocess.run(
        [sys.executable, os.path.join(PIPELINE_DIR, "optimize_all_channels.py"), "update"],
        capture_output=True, text=True, cwd=PIPELINE_DIR, timeout=300,
    )
    return _json_response(
        channel=channel_name,
        stdout=result.stdout[-1000:] if result.stdout else "",
        stderr=result.stderr[-500:] if result.stderr else "",
        returncode=result.returncode,
    )


# ── Tool 15: Select Arm (Bandit) ──

@mcp.tool()
def select_arm(channel_id: str) -> str:
    """Select a template arm using Thompson Sampling bandit optimization.

    Returns the recommended combination of voice profile, script format,
    and thumbnail style for the next video on this channel.

    Args:
        channel_id: Channel key (e.g., 'rich_tech')
    """
    try:
        from utils.bandits import select_arm as _select_arm
        arm = _select_arm(channel_id)
        return _json_response(**arm)
    except ImportError:
        return _json_response(error="Bandits module not yet available")
    except Exception as e:
        return _json_response(error=str(e)[:200])


# ── Tool 16: Produce Shorts ──

@mcp.tool()
def produce_shorts(path: str = "both", channel: str = None, max_clips: int = 3,
                   dry_run: bool = False) -> str:
    """Produce shorts from long-form videos (path-a) and/or native shorts scripts (path-b).

    Args:
        path: "a" (repurpose long-form), "b" (native shorts), or "both"
        channel: Filter to specific channel (optional)
        max_clips: Max clips per source video for path A
        dry_run: If true, show what would be produced without producing
    """
    args = [sys.executable, os.path.join(PIPELINE_DIR, "batch_produce_shorts.py")]
    if path == "a":
        args.append("--path-a")
    elif path == "b":
        args.append("--path-b")
    if channel:
        args.extend(["--channel", channel])
    if dry_run:
        args.append("--dry-run")
    args.extend(["--max-clips", str(max_clips)])

    result = subprocess.run(
        args, capture_output=True, text=True, cwd=PIPELINE_DIR, timeout=600
    )
    return _json_response(
        path=path,
        channel=channel,
        max_clips=max_clips,
        dry_run=dry_run,
        stdout=result.stdout[-2000:] if result.stdout else "",
        stderr=result.stderr[-500:] if result.stderr else "",
        returncode=result.returncode,
    )


# ── Tool 17: Shorts Status ──

@mcp.tool()
def shorts_status() -> str:
    """Show status of shorts production: counts per channel, pending, produced."""
    shorts_dir = os.path.join(OUTPUT_DIR, "shorts")
    if not os.path.exists(shorts_dir):
        return "No shorts directory found. Run produce_shorts first."

    shorts = [f for f in os.listdir(shorts_dir) if f.endswith(".mp4")]
    if not shorts:
        return "No shorts produced yet."

    # Count by channel
    from collections import Counter
    channels = Counter()
    for s in shorts:
        channel = s.split("_")[0]
        channels[channel] += 1

    lines = [f"Total shorts: {len(shorts)}", ""]
    for ch, count in channels.most_common():
        lines.append(f"  {ch}: {count}")

    return "\n".join(lines)


# ── Tool 18: Learning Status ──

@mcp.tool()
def learning_status() -> str:
    """Get comprehensive learning loop status: arms, rewards, drift, decisions."""
    from utils.telemetry import (
        get_arm_performance, get_recent_performance,
        detect_performance_drift, _get_db,
    )

    report = {}

    # Arm summary by type
    try:
        conn = _get_db()
        arm_types = conn.execute("""
            SELECT arm_type, COUNT(*) as count,
                   SUM(total_pulls) as total_pulls,
                   AVG(avg_reward) as avg_reward
            FROM template_arms WHERE active = 1
            GROUP BY arm_type
        """).fetchall()
        conn.close()
        report["arm_types"] = {r["arm_type"]: {
            "count": r["count"],
            "total_pulls": r["total_pulls"] or 0,
            "avg_reward": round(r["avg_reward"] or 0, 4),
        } for r in arm_types}
    except Exception as e:
        report["arm_types"] = f"Error: {e}"

    # Recent performance
    try:
        recent = get_recent_performance(n=10)
        report["recent_videos"] = len(recent)
        if recent:
            avg_reward = sum(r.get("reward", 0) or 0 for r in recent) / len(recent)
            report["avg_recent_reward"] = round(avg_reward, 2)
    except Exception as e:
        report["recent_performance"] = f"Error: {e}"

    # Drift detection
    try:
        drift = detect_performance_drift()
        report["drift"] = drift
    except Exception as e:
        report["drift"] = f"Error: {e}"

    # Decision count
    try:
        conn = _get_db()
        decisions = conn.execute("""
            SELECT decision_type, COUNT(*) as count
            FROM decisions
            WHERE created_at > datetime('now', '-7 days')
            GROUP BY decision_type
        """).fetchall()
        conn.close()
        report["decisions_last_7d"] = {r["decision_type"]: r["count"] for r in decisions}
    except Exception as e:
        report["decisions_last_7d"] = f"Error: {e}"

    return json.dumps(report, indent=2)


# ── Tool 19: Arm Report ──

@mcp.tool()
def arm_report(channel_id: str, arm_type: str = "packaging") -> str:
    """Get bandit arm performance report for a channel filtered by arm type.

    Args:
        channel_id: Channel key (e.g., 'rich_tech')
        arm_type: Arm type to filter ('packaging', 'title_formula', 'hook_category',
                  'shorts_config', 'voice_params', 'posting_schedule')
    """
    from utils.telemetry import _get_db

    conn = _get_db()
    rows = conn.execute("""
        SELECT arm_name, arm_type, config, total_pulls, total_reward,
               avg_reward, last_used, active
        FROM template_arms
        WHERE arm_type = ? AND arm_name LIKE ?
        ORDER BY avg_reward DESC
    """, (arm_type, f"{channel_id}__%")).fetchall()
    conn.close()

    if not rows:
        return json.dumps({"message": f"No {arm_type} arms found for {channel_id}"})

    arms = []
    for r in rows:
        arms.append({
            "arm_name": r["arm_name"],
            "config": json.loads(r["config"]) if r["config"] else {},
            "total_pulls": r["total_pulls"],
            "avg_reward": round(r["avg_reward"], 4),
            "last_used": r["last_used"],
            "active": bool(r["active"]),
        })

    return json.dumps({"channel": channel_id, "arm_type": arm_type,
                        "arms": arms, "total": len(arms)}, indent=2)


# ── Tool 20: Check Retraining ──

@mcp.tool()
def check_retraining() -> str:
    """Check and execute retraining triggers (drift, stale arms, copyright)."""
    from utils.alerts import check_retraining_triggers, execute_retraining

    triggers = check_retraining_triggers()
    if not triggers:
        return json.dumps({"status": "ok", "message": "No retraining triggers active"})

    actions = execute_retraining(triggers)
    return json.dumps({
        "status": "retraining_executed",
        "triggers": [t[0] for t in triggers],
        "actions": actions,
    }, indent=2)


# ── Tool 21: Pull Retention ──

@mcp.tool()
def pull_retention(video_name: str) -> str:
    """Fetch and store audience retention curve for a published video.

    Args:
        video_name: The video name (e.g., 'RichTech_5_Budget_Tech_Gadgets')
    """
    from utils.analytics import query_audience_retention
    from utils.telemetry import _get_db, log_retention_curve

    # Look up YouTube video ID
    conn = _get_db()
    row = conn.execute("""
        SELECT youtube_video_id FROM videos WHERE video_name = ?
    """, (video_name,)).fetchone()
    conn.close()

    if not row or not row["youtube_video_id"]:
        return json.dumps({"error": f"No YouTube ID found for {video_name}"})

    youtube_id = row["youtube_video_id"]
    retention = query_audience_retention(youtube_id)

    if not retention:
        return json.dumps({"error": "Failed to fetch retention data",
                           "video_id": youtube_id})

    # Store in DB
    log_retention_curve(video_name, youtube_id, retention)

    # Find high-rewatch segments
    high_rewatch = [r for r in retention if r.get("watch_ratio", 0) > 1.0]

    return json.dumps({
        "video_name": video_name,
        "youtube_id": youtube_id,
        "data_points": len(retention),
        "high_rewatch_segments": len(high_rewatch),
        "avg_watch_ratio": round(sum(r["watch_ratio"] for r in retention) / len(retention), 3),
    }, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
