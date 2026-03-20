#!/usr/bin/env python3
"""Mac ↔ PC communication sync.

Generates a machine-readable status snapshot of this machine's pipeline state,
writes pending task files, and commits/pushes to git so the other machine can pull.

Usage:
    python sync_comms.py                  # Generate status + push
    python sync_comms.py --check          # Show pending tasks for this machine
    python sync_comms.py --send "message" # Quick message to the other machine
    python sync_comms.py --send "message" --priority high --type request
"""

import argparse
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from glob import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "output", "pipeline.db")
COMMS_DIR = os.path.join(BASE_DIR, "comms")
STATUS_DIR = os.path.join(COMMS_DIR, "status")

# Detect which machine we're on
IS_MAC = platform.system() == "Darwin"
MACHINE = "mac" if IS_MAC else "pc"
OTHER = "pc" if IS_MAC else "mac"
OUTBOX = os.path.join(COMMS_DIR, f"{MACHINE}_to_{OTHER}")
INBOX = os.path.join(COMMS_DIR, f"{OTHER}_to_{MACHINE}")

for d in [OUTBOX, INBOX, STATUS_DIR]:
    os.makedirs(d, exist_ok=True)


def get_db_status():
    """Get pipeline database summary."""
    if not os.path.exists(DB_PATH):
        return {"error": "pipeline.db not found"}

    conn = sqlite3.connect(DB_PATH)
    status_counts = {}
    for row in conn.execute("SELECT status, COUNT(*) FROM videos GROUP BY status"):
        status_counts[row[0]] = row[1]

    # Per-channel breakdown for produced (ready to upload)
    produced_by_channel = {}
    for row in conn.execute(
        "SELECT channel, COUNT(*) FROM videos WHERE status='produced' GROUP BY channel ORDER BY COUNT(*) DESC"
    ):
        produced_by_channel[row[0]] = row[1]

    # Videos with D:\ paths (need sync from PC)
    pc_only = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE video_path LIKE 'D:%'"
    ).fetchone()[0]

    # Videos missing audio (need TTS)
    need_tts = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE status='planned' AND (audio_path IS NULL OR audio_path = '')"
    ).fetchone()[0]

    # Recent uploads
    recent = conn.execute(
        "SELECT channel, topic, published_at FROM videos WHERE status='published' ORDER BY published_at DESC LIMIT 5"
    ).fetchall()

    conn.close()

    return {
        "totals": status_counts,
        "produced_by_channel": produced_by_channel,
        "pc_only_videos": pc_only,
        "need_tts": need_tts,
        "recent_uploads": [
            {"channel": r[0], "topic": r[1], "published_at": r[2]} for r in recent
        ],
    }


def get_disk_status():
    """Get disk usage for pipeline output."""
    dirs = {
        "videos": os.path.join(BASE_DIR, "output", "videos"),
        "audio": os.path.join(BASE_DIR, "output", "audio"),
        "scripts": os.path.join(BASE_DIR, "output", "scripts"),
    }
    result = {}
    for name, path in dirs.items():
        if os.path.exists(path):
            files = [f for f in os.listdir(path) if not f.startswith(".")]
            result[name] = {"count": len(files)}
        else:
            result[name] = {"count": 0}
    return result


def get_cron_health():
    """Check if cron jobs ran recently (Mac only)."""
    if not IS_MAC:
        return {"note": "cron check only available on Mac"}

    logs = {
        "daily_upload": os.path.join(BASE_DIR, "output", "logs", "daily_upload_scheduler.log"),
        "daily_analysis": os.path.join(BASE_DIR, "output", "daily_analysis", "cron.log"),
        "seo_audit": os.path.join(BASE_DIR, "output", "logs", "seo_audit.log"),
        "facebook_bot": os.path.join(BASE_DIR, "output", "logs", "facebook_bot_cron.log"),
    }
    result = {}
    for name, path in logs.items():
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            age_hours = (time.time() - mtime) / 3600
            result[name] = {
                "last_modified": datetime.fromtimestamp(mtime).isoformat(),
                "age_hours": round(age_hours, 1),
                "healthy": age_hours < 48,
            }
        else:
            result[name] = {"status": "log_not_found"}
    return result


def generate_status():
    """Generate and save machine status snapshot."""
    status = {
        "machine": MACHINE,
        "generated_at": datetime.now().isoformat(),
        "hostname": platform.node(),
        "pipeline_db": get_db_status(),
        "disk": get_disk_status(),
        "cron": get_cron_health(),
    }

    path = os.path.join(STATUS_DIR, f"{MACHINE}_status.json")
    with open(path, "w") as f:
        json.dump(status, f, indent=2)
    print(f"Status snapshot saved: {path}")
    return status


def create_task(subject, details, priority="normal", task_type="info"):
    """Create a new task file for the other machine."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = subject.lower().replace(" ", "_")[:40]
    filename = f"{timestamp}_{slug}.json"

    task = {
        "from": MACHINE,
        "to": OTHER,
        "created": datetime.now().isoformat(),
        "priority": priority,
        "status": "pending",
        "type": task_type,
        "subject": subject,
        "details": details,
        "completed_at": None,
    }

    path = os.path.join(OUTBOX, filename)
    with open(path, "w") as f:
        json.dump(task, f, indent=2)
    print(f"Task created: {path}")
    return path


def check_inbox():
    """Show pending tasks from the other machine."""
    tasks = sorted(glob(os.path.join(INBOX, "*.json")))
    pending = []
    for path in tasks:
        with open(path) as f:
            task = json.load(f)
        if task.get("status") == "pending":
            pending.append((path, task))

    if not pending:
        print(f"No pending tasks from {OTHER}.")
        return

    print(f"\n{'='*60}")
    print(f"  PENDING TASKS FROM {OTHER.upper()} ({len(pending)})")
    print(f"{'='*60}")
    for path, task in pending:
        pri = f"[{task['priority'].upper()}]" if task.get("priority") != "normal" else ""
        print(f"\n  {pri} {task['subject']}")
        print(f"  Type: {task.get('type', 'info')} | Created: {task['created'][:16]}")
        print(f"  {task['details'][:200]}")
        print(f"  File: {os.path.basename(path)}")


def mark_done(filename):
    """Mark a task as completed."""
    path = os.path.join(INBOX, filename)
    if not os.path.exists(path):
        print(f"Task not found: {filename}")
        return
    with open(path) as f:
        task = json.load(f)
    task["status"] = "done"
    task["completed_at"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(task, f, indent=2)
    print(f"Marked done: {filename}")


def git_sync():
    """Commit and push comms changes, then pull."""
    repo_dir = os.path.dirname(BASE_DIR)  # Parent repo
    try:
        # Stage comms directory
        subprocess.run(
            ["git", "add", "video-pipeline/comms/"],
            cwd=repo_dir, capture_output=True, timeout=30,
        )
        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_dir, capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", f"comms: {MACHINE} status update {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
                cwd=repo_dir, capture_output=True, timeout=30,
            )
            subprocess.run(
                ["git", "push"],
                cwd=repo_dir, capture_output=True, timeout=60,
            )
            print("Pushed comms to git.")
        else:
            print("No comms changes to push.")

        # Pull other machine's updates
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=repo_dir, capture_output=True, timeout=60,
        )
        print("Pulled latest from remote.")
    except Exception as e:
        print(f"Git sync error: {str(e)[:200]}")


def main():
    parser = argparse.ArgumentParser(description="Mac ↔ PC pipeline comms")
    parser.add_argument("--check", action="store_true", help="Show pending tasks")
    parser.add_argument("--send", type=str, help="Quick message to other machine")
    parser.add_argument("--priority", default="normal", choices=["low", "normal", "high", "critical"])
    parser.add_argument("--type", dest="task_type", default="info",
                        choices=["sync_videos", "run_tts", "rerender", "info", "request"])
    parser.add_argument("--done", type=str, help="Mark a task filename as done")
    parser.add_argument("--no-git", action="store_true", help="Skip git sync")
    parser.add_argument("--status-only", action="store_true", help="Only generate status, no git")
    args = parser.parse_args()

    if args.check:
        check_inbox()
        return

    if args.done:
        mark_done(args.done)
        return

    # Always generate fresh status
    status = generate_status()

    # Print quick summary
    db = status["pipeline_db"]
    if "totals" in db:
        t = db["totals"]
        print(f"  DB: {t.get('published',0)} published, {t.get('produced',0)} produced, {t.get('planned',0)} planned")
        if db.get("pc_only_videos"):
            print(f"  PC-only videos needing sync: {db['pc_only_videos']}")
        if db.get("need_tts"):
            print(f"  Scripts needing TTS: {db['need_tts']}")

    if args.send:
        create_task(args.send, args.send, priority=args.priority, task_type=args.task_type)

    if not args.no_git and not args.status_only:
        git_sync()


if __name__ == "__main__":
    main()
