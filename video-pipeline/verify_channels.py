#!/usr/bin/env python3
"""Automate YouTube channel phone verification for custom thumbnails.

Opens the YouTube Studio channel switcher and verification page for each
unverified channel. Tracks progress so you can resume where you left off.

Usage:
    python3 verify_channels.py              # Start/resume interactive verification
    python3 verify_channels.py --batch      # Open all channels automatically (no prompts)
    python3 verify_channels.py --batch 5    # Open 5 channels at a time with 10s delay
    python3 verify_channels.py --priority   # Open only priority channels (have uploaded videos)
    python3 verify_channels.py --status     # Show verification status
    python3 verify_channels.py --check-api  # Check via API which channels need verification
    python3 verify_channels.py --reset      # Reset progress and start over
"""

import json
import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
PROGRESS_PATH = os.path.join(BASE_DIR, "output", "verification_progress.json")

# Channels with uploaded videos get priority
PRIORITY_CHANNELS = [
    "Eva Reyes", "How to Use AI", "RichHorror",
    "RichMind", "RichPets", "RichTech",
]


def load_channels():
    """Load all channels from channel_tokens.json."""
    with open(CHANNEL_TOKENS_PATH) as f:
        return json.load(f)


PHONE_NUMBERS = [
    {"number": "9173553882", "label": "Primary", "max_per_year": 2},
    {"number": "7574094333", "label": "Secondary", "max_per_year": 2},
]


def load_progress():
    """Load verification progress."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"verified": [], "skipped": [], "started_at": None, "phone_usage": {}}


def save_progress(progress):
    """Save verification progress."""
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, "w") as f:
        json.dump(progress, f, indent=2)


def refresh_token(creds):
    """Get a fresh access token for a channel."""
    from urllib.parse import urlencode
    data = urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data,
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  method="POST")
    resp = json.loads(urlopen(req, timeout=30).read().decode())
    return resp["access_token"]


def check_thumbnail_permission(access_token, channel_id):
    """Check if a channel can set custom thumbnails by querying channel status.

    Returns True if verified, False if not, None if unknown.
    """
    url = (
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=status&id={channel_id}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        resp = json.loads(urlopen(req, timeout=15).read().decode())
        items = resp.get("items", [])
        if items:
            # longUploadsStatus indicates verification level
            status = items[0].get("status", {})
            long_uploads = status.get("longUploadsStatus", "")
            # "allowed" or "eligible" means phone-verified
            if long_uploads in ("allowed", "eligible"):
                return True
            # Check if channel is verified via made-for-kids or other flags
            # The most reliable check is attempting a thumbnail set,
            # but that costs quota. longUploadsStatus is a good proxy.
            return False
        return None
    except HTTPError as e:
        if e.code == 403:
            return None  # quota or permission issue
        return None
    except Exception:
        return None


def check_all_channels_api():
    """Check verification status of all channels via API."""
    channels = load_channels()
    progress = load_progress()

    print("Checking channel verification status via API...")
    print("=" * 60)

    verified = []
    unverified = []
    errors = []

    for name, creds in sorted(channels.items()):
        channel_id = creds.get("channel_id", "unknown")
        try:
            token = refresh_token(creds)
            status = check_thumbnail_permission(token, channel_id)
            if status is True:
                verified.append(name)
                print(f"  [OK] {name} ({channel_id})")
            elif status is False:
                unverified.append(name)
                print(f"  [!!] {name} ({channel_id}) — NEEDS VERIFICATION")
            else:
                errors.append(name)
                print(f"  [??] {name} ({channel_id}) — could not determine")
        except Exception as e:
            errors.append(name)
            print(f"  [!!] {name} — error: {str(e)[:60]}")

    print()
    print(f"Verified:   {len(verified)}")
    print(f"Unverified: {len(unverified)}")
    print(f"Unknown:    {len(errors)}")

    return unverified


def show_status():
    """Show current verification progress."""
    channels = load_channels()
    progress = load_progress()

    verified = progress.get("verified", [])
    skipped = progress.get("skipped", [])
    remaining = [n for n in channels if n not in verified and n not in skipped]

    print("Channel Verification Status")
    print("=" * 60)
    print(f"Total channels:  {len(channels)}")
    print(f"Verified:        {len(verified)}")
    print(f"Skipped:         {len(skipped)}")
    print(f"Remaining:       {len(remaining)}")
    print()

    if verified:
        print("Verified:")
        for ch in sorted(verified):
            print(f"  [OK] {ch}")
        print()

    if skipped:
        print("Skipped:")
        for ch in sorted(skipped):
            print(f"  [--] {ch}")
        print()

    if remaining:
        # Show priority channels first
        priority = [ch for ch in PRIORITY_CHANNELS if ch in remaining]
        others = [ch for ch in sorted(remaining) if ch not in priority]

        print("Remaining:")
        for ch in priority:
            print(f"  [!!] {ch} (PRIORITY — has uploaded videos)")
        for ch in others:
            print(f"  [  ] {ch}")


def open_channel_verification(channel_name, channel_id):
    """Open YouTube Studio for a channel and then the verification page."""
    # Step 1: Open YouTube Studio to switch to the brand account context
    studio_url = f"https://studio.youtube.com/channel/{channel_id}"
    webbrowser.open(studio_url)
    time.sleep(2)

    # Step 2: Open the verification page
    verify_url = "https://www.youtube.com/verify"
    webbrowser.open(verify_url)


def run_verification():
    """Interactive verification flow for all channels."""
    channels = load_channels()
    progress = load_progress()

    if not progress.get("started_at"):
        progress["started_at"] = datetime.now().isoformat()

    verified = set(progress.get("verified", []))
    skipped = set(progress.get("skipped", []))

    # Build ordered list: priority channels first, then alphabetical
    remaining = [n for n in channels if n not in verified and n not in skipped]
    priority = [ch for ch in PRIORITY_CHANNELS if ch in remaining]
    others = sorted([ch for ch in remaining if ch not in PRIORITY_CHANNELS])
    ordered = priority + others

    if not ordered:
        print("All channels have been verified or skipped!")
        show_status()
        return

    print("YouTube Channel Phone Verification")
    print("=" * 60)
    print(f"Channels to verify: {len(ordered)} ({len(priority)} priority)")
    print()
    # Phone number tracking
    phone_usage = progress.get("phone_usage", {})
    for ph in PHONE_NUMBERS:
        if ph["number"] not in phone_usage:
            phone_usage[ph["number"]] = 0

    print("PHONE NUMBERS:")
    for ph in PHONE_NUMBERS:
        used = phone_usage.get(ph["number"], 0)
        remaining_uses = ph["max_per_year"] - used
        status = f"{used}/{ph['max_per_year']} used" if remaining_uses > 0 else "EXHAUSTED"
        print(f"  {ph['label']}: {ph['number']} ({status})")

    total_phone_slots = sum(max(ph["max_per_year"] - phone_usage.get(ph["number"], 0), 0) for ph in PHONE_NUMBERS)
    print(f"  Total verification slots remaining: {total_phone_slots}")
    if total_phone_slots < len(ordered):
        print(f"  WARNING: Not enough phone slots ({total_phone_slots}) for all channels ({len(ordered)})")
        print(f"  You'll need additional phone numbers for the remaining channels.")
    print()

    print("FLOW:")
    print("  - The script opens YouTube Studio (to switch brand account context)")
    print("  - Then opens the verification page")
    print()
    print("Commands at each step:")
    print("  1        = Verified with phone 1 ({})".format(PHONE_NUMBERS[0]["number"]))
    print("  2        = Verified with phone 2 ({})".format(PHONE_NUMBERS[1]["number"]))
    print("  [Enter]  = Verified (no phone tracking)")
    print("  s        = Skip this channel (come back later)")
    print("  q        = Quit and save progress")
    print("  r        = Re-open the verification page")
    print()

    input("Press Enter to start...")
    print()

    for i, name in enumerate(ordered, 1):
        creds = channels[name]
        channel_id = creds.get("channel_id", "unknown")
        is_priority = name in PRIORITY_CHANNELS

        print(f"[{i}/{len(ordered)}] {name}")
        print(f"  Channel ID: {channel_id}")
        print(f"  Studio: https://studio.youtube.com/channel/{channel_id}")
        if is_priority:
            print(f"  ** PRIORITY — has uploaded videos waiting for thumbnails **")
        print()
        print("  Opening YouTube Studio and verification page...")

        open_channel_verification(name, channel_id)

        # Show which phone to use next
        for ph in PHONE_NUMBERS:
            used = phone_usage.get(ph["number"], 0)
            if used < ph["max_per_year"]:
                print(f"  Suggested phone: {ph['label']} ({ph['number']}) — {used}/{ph['max_per_year']} used")
                break

        while True:
            action = input(f"\n  [{name}] Done? [1=phone1 / 2=phone2 / Enter=verified / s=skip / q=quit / r=reopen]: ").strip().lower()

            if action in ("", "1", "2"):
                verified.add(name)
                progress["verified"] = sorted(verified)

                # Track phone usage
                if action in ("1", "2"):
                    phone_idx = int(action) - 1
                    phone_num = PHONE_NUMBERS[phone_idx]["number"]
                    phone_usage[phone_num] = phone_usage.get(phone_num, 0) + 1
                    progress["phone_usage"] = phone_usage
                    print(f"  -> VERIFIED with {PHONE_NUMBERS[phone_idx]['label']} ({phone_num})")
                    print(f"     Phone {action} usage: {phone_usage[phone_num]}/{PHONE_NUMBERS[phone_idx]['max_per_year']}")
                else:
                    print(f"  -> Marked as VERIFIED")

                save_progress(progress)
                print(f"  Total verified: {len(verified)}")
                break
            elif action == "s":
                skipped.add(name)
                progress["skipped"] = sorted(skipped)
                save_progress(progress)
                print(f"  -> SKIPPED (will come back later)")
                break
            elif action == "q":
                progress["phone_usage"] = phone_usage
                save_progress(progress)
                print(f"\n  Progress saved. {len(verified)} verified, {len(skipped)} skipped.")
                print(f"  Run again to continue where you left off.")
                return
            elif action == "r":
                print("  Re-opening...")
                open_channel_verification(name, channel_id)
            else:
                print("  Unknown command. Use 1, 2, Enter, s, q, or r.")

        print()

    print("=" * 60)
    print(f"DONE! {len(verified)} channels verified, {len(skipped)} skipped.")
    save_progress(progress)

    if skipped:
        print(f"\nSkipped channels ({len(skipped)}):")
        for ch in sorted(skipped):
            print(f"  {ch}")
        print("\nRun this script again to retry skipped channels.")


def run_batch(limit=None, priority_only=False):
    """Non-interactive batch mode: opens verification pages automatically.

    Args:
        limit: Max channels to open per batch (None = all)
        priority_only: Only open priority channels
    """
    channels = load_channels()
    progress = load_progress()
    verified = set(progress.get("verified", []))
    skipped = set(progress.get("skipped", []))

    remaining = [n for n in channels if n not in verified and n not in skipped]
    priority = [ch for ch in PRIORITY_CHANNELS if ch in remaining]
    others = sorted([ch for ch in remaining if ch not in PRIORITY_CHANNELS])

    if priority_only:
        ordered = priority
    else:
        ordered = priority + others

    if limit:
        ordered = ordered[:limit]

    if not ordered:
        print("No channels to verify!")
        show_status()
        return

    print(f"Opening verification pages for {len(ordered)} channels...")
    print(f"  Delay: 10 seconds between each (to switch brand account context)")
    print()

    for i, name in enumerate(ordered, 1):
        creds = channels[name]
        channel_id = creds.get("channel_id", "unknown")
        is_priority = name in PRIORITY_CHANNELS
        tag = " ** PRIORITY **" if is_priority else ""

        print(f"[{i}/{len(ordered)}] {name}{tag}")
        print(f"  Channel ID: {channel_id}")
        print(f"  Studio:  https://studio.youtube.com/channel/{channel_id}")
        print(f"  Verify:  https://www.youtube.com/verify")

        # Open Studio first to switch brand account context
        studio_url = f"https://studio.youtube.com/channel/{channel_id}"
        subprocess.run(["open", studio_url], check=False)
        time.sleep(3)

        # Open verification page
        subprocess.run(["open", "https://www.youtube.com/verify"], check=False)

        if i < len(ordered):
            print(f"  Waiting 10s before next channel...\n")
            time.sleep(10)
        else:
            print()

    print("=" * 60)
    print(f"Opened {len(ordered)} channels.")
    print(f"Complete the phone verification in each browser tab.")
    print(f"Then run: python3 verify_channels.py --status")


if __name__ == "__main__":
    if not os.path.exists(CHANNEL_TOKENS_PATH):
        print(f"Error: {CHANNEL_TOKENS_PATH} not found")
        sys.exit(1)

    if "--status" in sys.argv:
        show_status()
    elif "--check-api" in sys.argv:
        check_all_channels_api()
    elif "--reset" in sys.argv:
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)
            print("Progress reset.")
        else:
            print("No progress file to reset.")
    elif "--batch" in sys.argv:
        # Parse optional limit: --batch 5
        idx = sys.argv.index("--batch")
        limit = None
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            limit = int(sys.argv[idx + 1])
        run_batch(limit=limit, priority_only=False)
    elif "--priority" in sys.argv:
        run_batch(priority_only=True)
    else:
        run_verification()
