"""Alert dispatch for pipeline anomalies and drift detection.

Supports:
- Console/stderr logging (always active)
- macOS notification center (osascript)
- Optional: Slack webhook (set SLACK_WEBHOOK_URL env var)
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from enum import Enum

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    PERFORMANCE_REGRESSION = "performance_regression"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    QUOTA_EXHAUSTION = "quota_exhaustion"
    UPLOAD_FAILURE = "upload_failure"
    HIGH_RISK_SCORE = "high_risk_score"
    WEEKLY_DIGEST = "weekly_digest"


def send_alert(alert_type, severity, title, message, video_name=None, channel=None):
    """Dispatch an alert through all configured channels.

    Always logs to console/stderr. Also sends macOS notification for WARNING+.
    Optionally sends to Slack if SLACK_WEBHOOK_URL is set.

    Args:
        alert_type: AlertType enum value
        severity: AlertSeverity enum value
        title: Short alert title
        message: Detailed message
        video_name: Associated video (for incident logging)
        channel: Associated channel name

    Returns:
        dict with dispatch results
    """
    results = {}

    # Always log to console
    _alert_console(severity, title, message)
    results["console"] = True

    # Log incident to telemetry DB
    try:
        from utils.telemetry import log_incident
        log_incident(
            video_name=video_name,
            incident_type=alert_type.value if isinstance(alert_type, AlertType) else str(alert_type),
            severity=severity.value if isinstance(severity, AlertSeverity) else str(severity),
            description=f"{title}: {message}",
        )
        results["incident_logged"] = True
    except Exception as e:
        results["incident_logged"] = False
        results["incident_error"] = str(e)[:100]

    # macOS notification for warning and critical
    if severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL):
        try:
            _alert_macos(title, message[:200])
            results["macos"] = True
        except Exception:
            results["macos"] = False

    # Slack webhook (optional)
    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    if slack_url:
        try:
            _alert_slack(title, message, slack_url, severity)
            results["slack"] = True
        except Exception:
            results["slack"] = False

    return results


def _alert_console(severity, title, message):
    """Print alert to stderr."""
    icon = {"info": "i", "warning": "!", "critical": "X"}.get(
        severity.value if isinstance(severity, AlertSeverity) else severity, "?"
    )
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{icon}] [{timestamp}] {title}", file=sys.stderr)
    for line in message.split("\n"):
        print(f"    {line}", file=sys.stderr)


def _alert_macos(title, message):
    """Send macOS notification via osascript."""
    # Escape quotes for AppleScript
    safe_title = title.replace('"', '\\"')
    safe_message = message.replace('"', '\\"')[:200]
    script = f'display notification "{safe_message}" with title "Video Pipeline" subtitle "{safe_title}"'
    subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, timeout=5,
    )


def _alert_slack(title, message, webhook_url, severity=None):
    """Send alert to Slack webhook."""
    from urllib.request import Request, urlopen

    color = {
        AlertSeverity.INFO: "#36a64f",
        AlertSeverity.WARNING: "#ff9900",
        AlertSeverity.CRITICAL: "#ff0000",
    }.get(severity, "#808080")

    payload = {
        "attachments": [{
            "color": color,
            "title": f"Video Pipeline: {title}",
            "text": message[:1000],
            "ts": int(datetime.now().timestamp()),
        }]
    }

    req = Request(
        webhook_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urlopen(req, timeout=10)


def check_and_alert_drift(n_recent=5, n_baseline=20):
    """Run drift detection and send alerts if regression detected.

    Args:
        n_recent: Number of recent videos to check
        n_baseline: Baseline video count

    Returns:
        Drift detection result dict
    """
    from utils.telemetry import detect_performance_drift

    result = detect_performance_drift(n_recent, n_baseline)

    if result.get("drift_detected"):
        direction = result.get("direction", "unknown")
        pct = result.get("pct_change", 0)

        if direction == "regression":
            send_alert(
                AlertType.PERFORMANCE_REGRESSION,
                AlertSeverity.WARNING,
                "Performance Regression Detected",
                f"Recent {n_recent} videos show {abs(pct)*100:.1f}% decline vs baseline.\n"
                f"Recent avg reward: {result.get('recent_avg_reward', 0):.2f}\n"
                f"Baseline avg reward: {result.get('baseline_avg_reward', 0):.2f}",
            )
        elif direction == "improvement":
            send_alert(
                AlertType.PERFORMANCE_IMPROVEMENT,
                AlertSeverity.INFO,
                "Performance Improvement Detected",
                f"Recent {n_recent} videos show {pct*100:.1f}% improvement vs baseline.\n"
                f"Recent avg reward: {result.get('recent_avg_reward', 0):.2f}\n"
                f"Baseline avg reward: {result.get('baseline_avg_reward', 0):.2f}",
            )

    return result


def check_quota_status():
    """Check YouTube API quota usage and alert if near exhaustion.

    Reads the upload report to estimate quota usage.
    Uses the report's quota_used_this_run field (preferred) or counts
    only today's uploads by timestamp to avoid inflating the estimate
    with results accumulated from previous runs.

    Returns:
        dict with quota status
    """
    report_path = os.path.join(BASE_DIR, "output", "reports", "youtube_upload_report.json")
    if not os.path.exists(report_path):
        return {"status": "no_report", "estimated_usage": 0}

    with open(report_path) as f:
        report = json.load(f)

    daily_limit = 10000
    quota_per_upload = 1600
    quota_per_thumbnail = 50

    # Prefer the uploader's own quota tracking if available
    if "quota_used_this_run" in report:
        estimated_usage = report["quota_used_this_run"]
        successful = report.get("uploaded_this_run", 0)
    else:
        # Fallback: count only today's uploads by timestamp
        today = datetime.utcnow().strftime("%Y-%m-%d")
        successful = 0
        for r in report.get("results", []):
            if r.get("status") != "success":
                continue
            uploaded_at = r.get("uploaded_at", "")
            if uploaded_at.startswith(today):
                successful += 1
        estimated_usage = successful * (quota_per_upload + quota_per_thumbnail)

    pct_used = estimated_usage / daily_limit if daily_limit > 0 else 0

    status = {
        "estimated_usage": estimated_usage,
        "daily_limit": daily_limit,
        "pct_used": round(pct_used * 100, 1),
        "uploads_today": successful,
        "remaining_capacity": max(0, (daily_limit - estimated_usage) // quota_per_upload),
    }

    if pct_used >= 0.9:
        send_alert(
            AlertType.QUOTA_EXHAUSTION,
            AlertSeverity.CRITICAL,
            "YouTube Quota Near Exhaustion",
            f"Estimated {pct_used*100:.0f}% of daily quota used ({estimated_usage}/{daily_limit}).\n"
            f"{successful} uploads today. ~{status['remaining_capacity']} uploads remaining.",
        )
    elif pct_used >= 0.7:
        send_alert(
            AlertType.QUOTA_EXHAUSTION,
            AlertSeverity.WARNING,
            "YouTube Quota Warning",
            f"Estimated {pct_used*100:.0f}% of daily quota used. "
            f"~{status['remaining_capacity']} uploads remaining.",
        )

    return status


def generate_weekly_digest():
    """Generate a weekly performance summary across all channels.

    Returns:
        Formatted digest string
    """
    from utils.telemetry import get_channel_summary, get_cost_report, get_recent_performance

    channels = get_channel_summary()
    costs = get_cost_report(7)
    recent = get_recent_performance(20)

    lines = [
        "=" * 60,
        "WEEKLY PIPELINE DIGEST",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 60,
        "",
    ]

    # Channel overview
    total_videos = sum(c.get("total_videos", 0) for c in channels)
    total_published = sum(c.get("published", 0) for c in channels)
    lines.append(f"Videos: {total_videos} total, {total_published} published")
    lines.append(f"Channels active: {len(channels)}")
    lines.append("")

    # Cost summary
    if costs:
        lines.append("COSTS (7 days):")
        lines.append(f"  Total: ${costs.get('total_cost', 0) or 0:.2f}")
        lines.append(f"  TTS: ${costs.get('total_tts', 0) or 0:.2f}")
        lines.append(f"  B-roll: ${costs.get('total_broll', 0) or 0:.2f}")
        lines.append(f"  Avg per video: ${costs.get('avg_cost_per_video', 0) or 0:.2f}")
        lines.append("")

    # Top performers
    if recent:
        scored = [r for r in recent if r.get("reward")]
        if scored:
            scored.sort(key=lambda x: x.get("reward", 0), reverse=True)
            lines.append("TOP PERFORMERS:")
            for r in scored[:5]:
                lines.append(f"  {r['video_name']}: reward={r['reward']:.1f}, views={r.get('views', 0)}")
            lines.append("")

    # Bandit arm performance
    try:
        from utils.bandits import get_arm_report
        arms = get_arm_report()
        if arms:
            active_arms = [a for a in arms if a["active"] and a["total_pulls"] > 0]
            if active_arms:
                lines.append("BANDIT ARM PERFORMANCE:")
                for a in active_arms[:10]:
                    lines.append(f"  {a['arm_name']}: pulls={a['total_pulls']}, avg={a['avg_reward']:.3f}")
                lines.append("")
    except ImportError:
        pass

    digest = "\n".join(lines)

    # Send as alert
    send_alert(
        AlertType.WEEKLY_DIGEST,
        AlertSeverity.INFO,
        "Weekly Pipeline Digest",
        digest,
    )

    return digest


def check_retraining_triggers():
    """Check all triggers that should cause bandit arm resets or re-exploration.

    Returns list of (trigger_type, data) tuples.
    """
    triggers = []

    # 1. Performance drift
    try:
        from utils.telemetry import detect_performance_drift
        drift = detect_performance_drift(n_recent=5, n_baseline=20, threshold=0.15)
        if drift.get("drift_detected") and drift.get("direction") == "regression":
            triggers.append(("performance_drift", drift))
    except Exception:
        pass

    # 2. Stale arms (no pulls in 14+ days)
    try:
        from utils.telemetry import _get_db
        conn = _get_db()
        stale = conn.execute("""
            SELECT arm_name, arm_type, last_used
            FROM template_arms
            WHERE active = 1 AND total_pulls > 0
            AND last_used < datetime('now', '-14 days')
        """).fetchall()
        conn.close()
        if stale:
            triggers.append(("stale_arms", [dict(r) for r in stale]))
    except Exception:
        pass

    # 3. Recent copyright incidents
    try:
        from utils.telemetry import _get_db
        conn = _get_db()
        incidents = conn.execute("""
            SELECT * FROM incidents
            WHERE incident_type LIKE '%copyright%'
            AND created_at > datetime('now', '-7 days')
        """).fetchall()
        conn.close()
        if incidents:
            triggers.append(("copyright_spike", [dict(r) for r in incidents]))
    except Exception:
        pass

    return triggers


def execute_retraining(triggers):
    """Reset exploration for arms affected by triggers.

    Returns list of actions taken.
    """
    actions = []

    for trigger_type, data in triggers:
        if trigger_type == "performance_drift":
            # Reset low-pull arms to uniform prior (increase exploration)
            try:
                from utils.telemetry import _get_db
                conn = _get_db()
                reset = conn.execute("""
                    UPDATE template_arms
                    SET total_pulls = 0, total_reward = 0, avg_reward = 0
                    WHERE active = 1 AND total_pulls < 5
                """).rowcount
                conn.commit()
                conn.close()
                actions.append(f"Reset {reset} low-pull arms due to performance drift")
            except Exception as e:
                actions.append(f"Failed to reset arms: {e}")

        elif trigger_type == "stale_arms":
            # Reactivate stale arms with fresh prior
            try:
                from utils.telemetry import _get_db
                conn = _get_db()
                arm_names = [a["arm_name"] for a in data]
                for arm_name in arm_names:
                    conn.execute("""
                        UPDATE template_arms
                        SET total_pulls = 0, total_reward = 0, avg_reward = 0
                        WHERE arm_name = ?
                    """, (arm_name,))
                conn.commit()
                conn.close()
                actions.append(f"Reset {len(arm_names)} stale arms to uniform prior")
            except Exception as e:
                actions.append(f"Failed to reset stale arms: {e}")

        elif trigger_type == "copyright_spike":
            # Log incident and alert
            try:
                from utils.telemetry import log_incident
                log_incident(
                    "retraining_triggered",
                    severity="warning",
                    description=f"Copyright incidents detected: {len(data)} in last 7 days",
                    resolution="Conservative arms prioritized",
                )
                actions.append(f"Logged copyright retraining trigger ({len(data)} incidents)")
            except Exception as e:
                actions.append(f"Failed to log copyright trigger: {e}")

    # Alert about retraining
    if actions:
        try:
            send_alert(AlertType.PERFORMANCE_REGRESSION, AlertSeverity.WARNING,
                       "Retraining triggered",
                       f"Actions taken: {'; '.join(actions)}")
        except Exception:
            pass

    return actions
