#!/usr/bin/env python3
"""Mac/PC pipeline sync — keeps both machines in harmony.

WORKFLOW:
  Windows PC  → renders videos, bakes outros → status: 'produced'
  Mac Mini    → uploads to YouTube, tracks analytics → status: 'published'

GOLDEN RULES (no stepping on each other's toes):
  1. Windows NEVER uploads to YouTube
  2. Mac NEVER renders or re-encodes production videos
  3. pipeline.db on Mac is the MASTER copy for published/analytics data
  4. pipeline.db on Windows is the source for newly produced videos
  5. Sync always: Windows produces a DIFF, Mac MERGES the diff

SYNC COMMANDS:
  # From Windows — export changes for Mac to ingest:
  python sync_pipeline.py export

  # From Mac — import Windows changes into Mac's DB:
  python sync_pipeline.py import --file sync_export_YYYYMMDD.json

  # From Windows — pull Mac's DB (overwrites local, keeps produced entries):
  python sync_pipeline.py pull --mac richardabreu@192.168.4.106

  # Full sync: push Windows-produced + pull Mac-published:
  python sync_pipeline.py full --mac richardabreu@192.168.4.106
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

# ── Path resolution ──────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
if BASE.startswith("/d/") or BASE.startswith("/D/"):
    BASE = "D:" + BASE[2:].replace("/", os.sep)
elif BASE.startswith("/c/") or BASE.startswith("/C/"):
    BASE = "C:" + BASE[2:].replace("/", os.sep)
BASE = os.path.normpath(BASE)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB_PATH     = os.path.join(BASE, "output", "pipeline.db")
REPORTS_DIR = os.path.join(BASE, "output", "reports")
MAC_DB_PATH = "~/Projects/RichardAbreuPortfolio/video-pipeline/output/pipeline.db"
SSH_KEY     = os.path.expanduser("~/.ssh/id_ed25519")


# ── Export: Windows → JSON diff ─────────────────────────────────────────────

def export_windows_changes(output_path=None):
    """Export videos produced on Windows that Mac doesn't know about yet.

    Exports all rows with status='produced' plus any outro_baked updates.
    Mac will MERGE these (INSERT OR IGNORE + UPDATE specific fields).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get all produced videos (the Windows PC's contribution)
    rows = conn.execute("""
        SELECT * FROM videos
        WHERE status = 'produced'
        ORDER BY created_at
    """).fetchall()

    export_data = {
        "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_machine": "windows_pc",
        "db_path": DB_PATH,
        "videos": [dict(r) for r in rows],
        "total": len(rows)
    }

    conn.close()

    if not output_path:
        output_path = os.path.join(
            REPORTS_DIR,
            f"sync_export_{time.strftime('%Y%m%d_%H%M%S')}.json"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported {len(rows)} produced video(s) to {output_path}")
    for r in rows:
        r_dict = dict(r)
        status_suffix = " [outro baked]" if r_dict.get("outro_baked") else ""
        print(f"  - {r_dict['video_name']} [{r_dict['channel']}]{status_suffix}")

    return output_path


# ── Import: Mac ingests Windows diff ─────────────────────────────────────────

def import_windows_changes(json_path, db_path=None):
    """Import Windows-produced videos into Mac's DB without overwriting published data.

    Rules:
    - If video doesn't exist in Mac DB: INSERT it
    - If video exists with status='published': skip (don't downgrade)
    - If video exists with status='produced': UPDATE size/duration/outro_baked
    - Never change youtube_video_id, published_at, or status='published'
    """
    if not os.path.exists(json_path):
        print(f"ERROR: File not found: {json_path}")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", [])
    print(f"Importing {len(videos)} video(s) from {data.get('source_machine', 'unknown')}")
    print(f"  Export time: {data.get('export_time', 'unknown')}")

    target_db = db_path or DB_PATH
    conn = sqlite3.connect(target_db)

    # Ensure outro_baked column exists
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(videos)").fetchall()]
    if "outro_baked" not in existing_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN outro_baked INTEGER DEFAULT 0")

    inserted = 0
    updated = 0
    skipped = 0

    for v in videos:
        # Use BEGIN IMMEDIATE to acquire write lock before read-then-write
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT status, youtube_video_id FROM videos WHERE video_name = ?",
                (v["video_name"],)
            ).fetchone()

            if existing is None:
                # New video — insert it
                cols = [c for c in v.keys() if c != "id"]
                placeholders = ",".join(["?"] * len(cols))
                col_names = ",".join(cols)
                values = [v[c] for c in cols]
                try:
                    conn.execute(
                        f"INSERT INTO videos ({col_names}) VALUES ({placeholders})",
                        values
                    )
                    inserted += 1
                    print(f"  INSERT: {v['video_name']}")
                except sqlite3.Error as e:
                    print(f"  INSERT ERROR {v['video_name']}: {e}")

            elif existing[0] == "published":
                # Already published on YouTube — never overwrite
                skipped += 1
                print(f"  SKIP (published): {v['video_name']}")

            else:
                # Update non-critical fields, but NEVER downgrade from published
                conn.execute("""
                    UPDATE videos SET
                        video_path = ?,
                        video_size_mb = ?,
                        video_duration_sec = ?,
                        outro_baked = COALESCE(?, outro_baked),
                        status = CASE WHEN status != 'published' THEN ? ELSE status END
                    WHERE video_name = ? AND status != 'published'
                """, (
                    v.get("video_path"),
                    v.get("video_size_mb"),
                    v.get("video_duration_sec"),
                    v.get("outro_baked"),
                    v.get("status", "produced"),
                    v["video_name"]
                ))
                updated += 1
                print(f"  UPDATE: {v['video_name']}")

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"  SYNC ERROR {v['video_name']}: {e}")

    conn.close()

    print(f"\nSync complete: {inserted} inserted, {updated} updated, {skipped} skipped")
    return True


# ── SSH helpers ──────────────────────────────────────────────────────────────

def ssh_cmd(mac_host, remote_cmd, timeout=30):
    """Run a command on Mac via SSH."""
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes",
         "-o", "StrictHostKeyChecking=no",
         "-o", f"ConnectTimeout={timeout}",
         mac_host, remote_cmd],
        capture_output=True, text=True
    )
    return result


def scp_to_mac(local_path, mac_host, remote_path, timeout=120):
    """Copy a file to Mac via SCP."""
    result = subprocess.run(
        ["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes",
         "-o", "StrictHostKeyChecking=no",
         local_path, f"{mac_host}:{remote_path}"],
        capture_output=True, text=True, timeout=timeout
    )
    return result.returncode == 0


def scp_from_mac(mac_host, remote_path, local_path, timeout=120):
    """Copy a file from Mac via SCP."""
    result = subprocess.run(
        ["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes",
         "-o", "StrictHostKeyChecking=no",
         f"{mac_host}:{remote_path}", local_path],
        capture_output=True, text=True, timeout=timeout
    )
    return result.returncode == 0


# ── Full sync ─────────────────────────────────────────────────────────────────

def full_sync(mac_host):
    """Two-way sync: push Windows produced videos, pull Mac published data.

    Step 1: Pull Mac's current DB to a temp copy
    Step 2: Export Windows changes to JSON
    Step 3: Import Windows changes into Mac DB copy (merge)
    Step 4: Push merged DB back to Mac
    Step 5: Update local Windows DB with Mac's published data
    """
    print(f"\nFull sync with Mac: {mac_host}")
    print(f"{'='*60}\n")

    # Step 1: Pull Mac's DB
    print("[1/5] Pulling Mac DB...")
    mac_db_temp = os.path.join(REPORTS_DIR, "mac_pipeline_temp.db")
    os.makedirs(REPORTS_DIR, exist_ok=True)

    if not scp_from_mac(mac_host, MAC_DB_PATH, mac_db_temp):
        print("  FAILED: Could not pull Mac DB. Is SSH working?")
        print("  Check: ssh -i ~/.ssh/id_ed25519 richardabreu@192.168.4.106 echo ok")
        return False

    print(f"  Pulled Mac DB to {mac_db_temp}")

    # Step 2: Export Windows changes
    print("\n[2/5] Exporting Windows changes...")
    export_path = export_windows_changes()

    # Step 3: Import Windows changes into Mac DB copy
    print("\n[3/5] Merging Windows changes into Mac DB...")
    if not import_windows_changes(export_path, db_path=mac_db_temp):
        print("  FAILED: Merge failed")
        return False

    # Step 4: Push merged DB back to Mac
    print("\n[4/5] Pushing merged DB to Mac...")
    # First backup Mac's current DB
    backup_cmd = f"cp {MAC_DB_PATH} {MAC_DB_PATH}.backup_{time.strftime('%Y%m%d_%H%M%S')}"
    ssh_cmd(mac_host, backup_cmd)

    if not scp_to_mac(mac_db_temp, mac_host, MAC_DB_PATH):
        print("  FAILED: Could not push merged DB to Mac")
        return False

    print("  Pushed merged DB to Mac")

    # Step 5: Update local Windows DB with Mac's published data
    print("\n[5/5] Updating Windows DB with Mac's published data...")
    mac_conn = sqlite3.connect(mac_db_temp)
    mac_conn.row_factory = sqlite3.Row
    published = mac_conn.execute("""
        SELECT video_name, status, youtube_video_id, published_at
        FROM videos WHERE status = 'published'
    """).fetchall()
    mac_conn.close()

    win_conn = sqlite3.connect(DB_PATH)
    for row in published:
        win_conn.execute("""
            UPDATE videos SET
                status = 'published',
                youtube_video_id = COALESCE(?, youtube_video_id),
                published_at = COALESCE(?, published_at)
            WHERE video_name = ?
        """, (row["youtube_video_id"], row["published_at"], row["video_name"]))
    win_conn.commit()
    win_conn.close()

    # Cleanup
    if os.path.exists(mac_db_temp):
        os.remove(mac_db_temp)

    print(f"  Updated {len(published)} published video statuses in Windows DB")
    print(f"\nFull sync complete!")
    print(f"  Mac's DB now has Windows-produced videos")
    print(f"  Windows DB now has Mac's published statuses")
    return True


# ── Video sync: push produced videos to Mac ──────────────────────────────────

def push_videos_to_mac(mac_host, channel=None, outro_only=True):
    """Push produced (outro-baked) videos to Mac's video directory for upload.

    Only pushes videos with outro_baked=1 by default (fully ready for upload).
    Mac uploads them to YouTube; Windows should NOT upload directly.

    Args:
        mac_host: SSH host like richardabreu@192.168.4.106
        channel: Filter by channel (optional)
        outro_only: Only push videos with outro baked (default True)
    """
    conn = sqlite3.connect(DB_PATH)
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(videos)").fetchall()]
    outro_col = "outro_baked" if "outro_baked" in existing_cols else "0"

    query = f"""
        SELECT video_name, channel, video_path, video_size_mb
        FROM videos
        WHERE status = 'produced'
          AND video_path IS NOT NULL
          {'AND ' + outro_col + ' = 1' if outro_only else ''}
          {'AND channel = ?' if channel else ''}
        ORDER BY created_at DESC
    """
    rows = conn.execute(query, (channel,) if channel else ()).fetchall()
    conn.close()

    if not rows:
        print("No videos to push (looking for produced + outro_baked=1)")
        return True

    print(f"Pushing {len(rows)} video(s) to Mac...")
    mac_videos_dir = "~/Projects/RichardAbreuPortfolio/video-pipeline/output/videos/"

    success = 0
    for video_name, channel_name, video_path, size_mb in rows:
        local_path = resolve_path(video_path)
        if not local_path:
            print(f"  SKIP: {video_name} — file not found locally")
            continue

        print(f"  Pushing {os.path.basename(local_path)} ({size_mb:.0f} MB)...")
        if scp_to_mac(local_path, mac_host, mac_videos_dir, timeout=600):
            print(f"    OK")
            success += 1
        else:
            print(f"    FAILED")

    print(f"\nPushed {success}/{len(rows)} videos to Mac")
    print("Mac can now upload these to YouTube via the nightly pipeline")
    return success == len(rows)


def resolve_path(video_path):
    if os.path.isabs(video_path) and os.path.exists(video_path):
        return video_path
    candidate = os.path.normpath(os.path.join(BASE, video_path))
    if os.path.exists(candidate):
        return candidate
    fname = os.path.basename(video_path)
    candidate2 = os.path.join(BASE, "output", "videos", fname)
    if os.path.exists(candidate2):
        return candidate2
    return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mac/PC pipeline sync utility")
    sub = parser.add_subparsers(dest="cmd")

    exp = sub.add_parser("export", help="Export Windows-produced videos to JSON")
    exp.add_argument("--output", help="Output JSON path")

    imp = sub.add_parser("import", help="Import Windows JSON into Mac DB")
    imp.add_argument("--file", required=True, help="Path to export JSON")
    imp.add_argument("--db", help="Target DB path (default: local pipeline.db)")

    pull = sub.add_parser("pull", help="Pull Mac DB and update local published statuses")
    pull.add_argument("--mac", default="richardabreu@192.168.4.106", help="Mac SSH host")

    push_db = sub.add_parser("push-db", help="Push local DB changes to Mac")
    push_db.add_argument("--mac", default="richardabreu@192.168.4.106", help="Mac SSH host")

    push_vids = sub.add_parser("push-videos", help="Push produced+baked videos to Mac")
    push_vids.add_argument("--mac", default="richardabreu@192.168.4.106", help="Mac SSH host")
    push_vids.add_argument("--channel", help="Filter by channel")
    push_vids.add_argument("--all", action="store_true", help="Push even if outro not baked")

    full = sub.add_parser("full", help="Full two-way sync with Mac")
    full.add_argument("--mac", default="richardabreu@192.168.4.106", help="Mac SSH host")

    status = sub.add_parser("status", help="Show sync status (what's ready to push)")

    args = parser.parse_args()

    if args.cmd == "export":
        export_windows_changes(args.output)

    elif args.cmd == "import":
        import_windows_changes(args.file, args.db)

    elif args.cmd == "pull":
        mac_db_temp = os.path.join(REPORTS_DIR, "mac_pull_temp.db")
        os.makedirs(REPORTS_DIR, exist_ok=True)
        if scp_from_mac(args.mac, MAC_DB_PATH, mac_db_temp):
            mac_conn = sqlite3.connect(mac_db_temp)
            mac_conn.row_factory = sqlite3.Row
            published = mac_conn.execute(
                "SELECT video_name, youtube_video_id, published_at FROM videos WHERE status='published'"
            ).fetchall()
            mac_conn.close()
            win_conn = sqlite3.connect(DB_PATH)
            for row in published:
                win_conn.execute(
                    "UPDATE videos SET status='published', youtube_video_id=COALESCE(?,youtube_video_id), "
                    "published_at=COALESCE(?,published_at) WHERE video_name=?",
                    (row["youtube_video_id"], row["published_at"], row["video_name"])
                )
            win_conn.commit()
            win_conn.close()
            os.remove(mac_db_temp)
            print(f"Pulled {len(published)} published statuses from Mac")
        else:
            print("ERROR: Could not pull from Mac. Check SSH connection.")

    elif args.cmd == "push-videos":
        push_videos_to_mac(args.mac, args.channel, outro_only=not args.all)

    elif args.cmd == "full":
        full_sync(args.mac)

    elif args.cmd == "status":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(videos)").fetchall()]
        outro_col = "outro_baked" if "outro_baked" in existing_cols else "0"
        produced = conn.execute(
            f"SELECT video_name, channel, video_size_mb, COALESCE({outro_col},0) as ob FROM videos WHERE status='produced'"
        ).fetchall()
        published = conn.execute("SELECT COUNT(*) FROM videos WHERE status='published'").fetchone()[0]
        conn.close()

        print(f"\nPipeline Sync Status")
        print(f"{'='*50}")
        print(f"  Published (on YouTube): {published}")
        print(f"  Produced (ready to sync/upload): {len(produced)}")
        print()
        for r in produced:
            outro_tag = "[outro baked]" if r["ob"] else "[no outro yet]"
            print(f"    - {r['video_name']} [{r['channel']}] {outro_tag} ({r['video_size_mb'] or 0:.0f} MB)")
        print()
        print("Run 'python sync_pipeline.py full --mac richardabreu@192.168.4.106' when SSH is available")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
