#!/usr/bin/env python3
"""Run competitive audits for YouTube channels.

Usage:
    python3 competitive_audit.py                          # all faceless channels
    python3 competitive_audit.py rich_tech cumquat_gaming  # specific channels
"""

import json
import os
import sys
from datetime import datetime

from utils.competitive import get_competitive_brief

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config():
    with open(os.path.join(BASE_DIR, "channels_config.json")) as f:
        return json.load(f)


def main():
    config = load_config()
    channels = config.get("channels", {})

    if len(sys.argv) > 1:
        target_channels = sys.argv[1:]
    else:
        target_channels = [
            k for k, v in channels.items() if v.get("faceless", False)
        ]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("=" * 60)
    print(f"  COMPETITIVE AUDIT — {len(target_channels)} channels")
    print(f"  {timestamp}")
    print("=" * 60)

    success = 0
    failed = 0

    for i, ch_key in enumerate(target_channels, 1):
        ch = channels.get(ch_key)
        if not ch:
            print(f"\n[{i}/{len(target_channels)}] SKIP: {ch_key} not in config")
            failed += 1
            continue

        print(f"\n[{i}/{len(target_channels)}] {ch.get('name', ch_key)} ({ch_key})")
        print("-" * 40)

        brief = get_competitive_brief(ch_key)
        if brief:
            # Show first 3 lines of the brief as preview
            preview = "\n".join(brief.strip().split("\n")[:3])
            print(f"  {preview}")
            success += 1
        else:
            print("  No brief generated")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  AUDIT COMPLETE: {success} success, {failed} failed")
    # Estimate: 100 units per search + 2 units per video stats = ~102 units/channel
    quota_est = success * 102
    print(f"  Estimated YouTube quota used: ~{quota_est} units")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
