#!/usr/bin/env python3
"""Delete abandoned/stuck YouTube videos and update upload report.

These videos uploaded successfully but YouTube failed to process them.
They need to be removed from YouTube and re-uploaded.

Usage:
    python3 cleanup_abandoned.py --dry-run    # List what would be deleted
    python3 cleanup_abandoned.py              # Actually delete
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(BASE_DIR, "output", "reports", "youtube_upload_report.json")

# Videos confirmed stuck or abandoned as of 2026-03-02
DEAD_VIDEO_IDS = [
    # Abandoned (20) - YouTube API returns "not found"
    "vFJhZE0SP10", "1lVxwEjVTZc", "GhJ51EY1cP8", "_o_1KTehh5U", "DHCIDQJ7EgY",
    "YpO3dxr9GvE", "twiv4HslqPs", "L5mVReEfji4", "YhW54e5Uq18", "5Sc5rI8_wGA",
    "C1kSDUflctw", "QfdtZdLiVSo", "-wY-D4D-AWA", "tUfI6PH69iY", "cU5HZulFBw4",
    "M442zqV2j9A", "HbCYGZCWYFo", "3s99rQaan8w", "XSzJp74-eRw", "k392UKLR82I",
    # Stuck processing 9+ days (16) - uploadStatus="uploaded", fileDetails={}
    "n2mafDiTa6s", "K-uXiZi7RKA", "gR62sBNN1RU", "hIgMChl3AIc", "noBj9QEmKdo",
    "OY7qWw0O7M8", "1mDs_t_Ud_0", "MoO48R0AUTI", "0vm8rEWg9Is", "zlRCz9SCG0c",
    "P_peoWQSMbc", "jApS6FAWVrA", "hZaxEohoOks", "q99naxFiFY4", "Nk7BOnP-TaU",
    "2YPLLFNGjZM",
]


def load_tokens():
    with open(os.path.join(BASE_DIR, "google_token.json")) as f:
        default = json.load(f)
    with open(os.path.join(BASE_DIR, "channel_tokens.json")) as f:
        channels = json.load(f)
    return default, channels


def refresh_token(token_data, default_token):
    refresh = token_data.get("refresh_token")
    client_id = token_data.get("client_id") or default_token.get("client_id")
    client_secret = token_data.get("client_secret") or default_token.get("client_secret")
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token"
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["access_token"]


def delete_video(video_id, access_token):
    url = "https://www.googleapis.com/youtube/v3/videos?id=" + video_id
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + access_token
    }, method="DELETE")
    try:
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True  # Already gone
        body = e.read().decode()
        print("    Delete error %d: %s" % (e.code, body[:200]))
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    with open(REPORT_PATH) as f:
        report = json.load(f)

    default_token, channel_tokens = load_tokens()

    # Map video_id -> report entry
    dead_entries = []
    for r in report["results"]:
        if r.get("video_id") in DEAD_VIDEO_IDS:
            dead_entries.append(r)

    # Group by channel
    by_channel = {}
    for entry in dead_entries:
        by_channel.setdefault(entry["channel"], []).append(entry)

    prefix = "DRY RUN: " if dry_run else ""
    print("%sCleaning up %d dead videos" % (prefix, len(dead_entries)))
    print("Channels affected: %d" % len(by_channel))

    deleted = 0
    failed = 0
    token_cache = {}

    for channel in sorted(by_channel):
        entries = by_channel[channel]
        print("\n  %s: %d videos" % (channel, len(entries)))

        if not dry_run:
            # Get access token for this channel
            if channel not in token_cache:
                ch_token = channel_tokens.get(channel)
                if ch_token:
                    try:
                        token_cache[channel] = refresh_token(ch_token, default_token)
                    except Exception as e:
                        print("    Token refresh failed, using default: %s" % e)
                        token_cache[channel] = refresh_token(default_token, default_token)
                else:
                    token_cache[channel] = refresh_token(default_token, default_token)

        for entry in entries:
            vid = entry["video_id"]
            name = entry["file"][:65]
            if dry_run:
                print("    Would delete: %s (%s)" % (name, vid))
            else:
                if delete_video(vid, token_cache[channel]):
                    print("    Deleted: %s" % name)
                    deleted += 1
                else:
                    print("    FAILED: %s" % name)
                    failed += 1
                time.sleep(0.5)

    if not dry_run:
        # Update report: remove dead entries
        report["results"] = [r for r in report["results"]
                             if r.get("video_id") not in DEAD_VIDEO_IDS]
        report["uploaded"] = len(report["results"])
        today = time.strftime("%Y-%m-%d")
        report["cleanup_note"] = "Removed %d dead videos on %s" % (deleted, today)

        with open(REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)
        print("\nDone: %d deleted, %d failed" % (deleted, failed))
        print("Report updated: %d remaining" % len(report["results"]))
    else:
        print("\nDry run: %d videos would be deleted" % len(dead_entries))


if __name__ == "__main__":
    main()
