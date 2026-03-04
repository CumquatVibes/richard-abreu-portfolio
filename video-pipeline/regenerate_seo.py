#!/usr/bin/env python3
"""Regenerate SEO metadata for existing scripts using Gemini.

Finds scripts with weak SEO (generic descriptions, single-word tags, unresolved
template variables) and regenerates them with the improved FacelessSEO class.

Usage:
    python3 regenerate_seo.py                    # all scripts
    python3 regenerate_seo.py --channel richtech  # specific channel prefix
    python3 regenerate_seo.py --dry-run           # preview without writing
"""

import json
import os
import sys
import re
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")

# Load env
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, "..", "shopify-theme", ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Load channel config
with open(os.path.join(BASE_DIR, "channels_config.json")) as f:
    CHANNELS = json.load(f)


def needs_regeneration(seo_path):
    """Check if an SEO file has known quality issues."""
    try:
        with open(seo_path) as f:
            data = json.load(f)
    except Exception:
        return True

    desc = data.get("description", "")
    tags = data.get("tags", [])

    # Check for known issues
    issues = []
    if "we break down everything you need to know" in desc:
        issues.append("generic_description")
    if "#{channel_hashtag}" in desc:
        issues.append("unresolved_template")
    # Check for single-word junk tags
    single_word_tags = [t for t in tags if " " not in t and len(t) < 8]
    if len(single_word_tags) > len(tags) * 0.5:
        issues.append("single_word_tags")
    # Check for filler tags
    filler = {"faceless youtube", "ai narration", "top 10", "facts"}
    if filler & set(t.lower() for t in tags):
        issues.append("filler_tags")

    return issues


def extract_topic_from_script(script_path):
    """Extract the topic line from a script file."""
    with open(script_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("# Topic:"):
                return line.replace("# Topic:", "").strip()
    return None


def extract_channel_from_script(script_path):
    """Extract the channel key from a script file."""
    with open(script_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("# Channel:"):
                return line.replace("# Channel:", "").strip()
    return None


def find_channel_config(channel_name):
    """Find channel config by name."""
    channels = CHANNELS.get("faceless_channels", {})
    for key, cfg in channels.items():
        if cfg.get("name", "").lower() == channel_name.lower():
            return cfg
    # Fallback: return a generic config
    return {"name": channel_name, "niche": "technology", "youtube_category": "28"}


def regenerate_seo_for_script(script_path, seo_path, dry_run=False):
    """Regenerate SEO metadata for a single script."""
    topic = extract_topic_from_script(script_path)
    channel_name = extract_channel_from_script(script_path)
    if not topic:
        return False, "no_topic"

    channel_config = find_channel_config(channel_name or "RichTech")

    # Read script text for chapter extraction
    with open(script_path, encoding="utf-8") as f:
        script_text = f.read()

    # Import and use the improved FacelessSEO
    sys.path.insert(0, BASE_DIR)
    from faceless_pipeline import FacelessSEO

    seo = FacelessSEO(channel_config, topic, script_text=script_text)
    seo_data = seo.generate()

    if dry_run:
        print(f"    Title: {seo_data['titles'][0]}")
        print(f"    Tags: {', '.join(seo_data['tags'][:5])}...")
        print(f"    Desc: {seo_data['description'][:100]}...")
        return True, "dry_run"

    with open(seo_path, "w", encoding="utf-8") as f:
        json.dump(seo_data, f, indent=2)
    return True, "regenerated"


def main():
    dry_run = "--dry-run" in sys.argv
    channel_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--channel"):
            if "=" in arg:
                channel_filter = arg.split("=", 1)[1]
            elif sys.argv.index(arg) + 1 < len(sys.argv):
                channel_filter = sys.argv[sys.argv.index(arg) + 1]

    # Find all SEO files
    seo_files = sorted(f for f in os.listdir(SCRIPTS_DIR) if f.endswith("_seo.json"))
    if channel_filter:
        seo_files = [f for f in seo_files if channel_filter.lower() in f.lower()]

    print(f"{'=' * 60}")
    print(f"  SEO Metadata Regenerator")
    print(f"  Found: {len(seo_files)} SEO files")
    if dry_run:
        print(f"  Mode: DRY RUN (no files will be modified)")
    print(f"{'=' * 60}\n")

    needs_fix = 0
    fixed = 0
    failed = 0

    for i, seo_file in enumerate(seo_files):
        seo_path = os.path.join(SCRIPTS_DIR, seo_file)
        script_file = seo_file.replace("_seo.json", ".txt")
        script_path = os.path.join(SCRIPTS_DIR, script_file)

        if not os.path.exists(script_path):
            continue

        issues = needs_regeneration(seo_path)
        if not issues:
            continue

        needs_fix += 1
        print(f"[{needs_fix}] {seo_file}")
        print(f"    Issues: {', '.join(issues)}")

        ok, status = regenerate_seo_for_script(script_path, seo_path, dry_run)
        if ok:
            fixed += 1
            print(f"    -> {status}")
        else:
            failed += 1
            print(f"    -> FAILED: {status}")

        # Rate limit Gemini calls
        if not dry_run and ok:
            time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"  COMPLETE")
    print(f"  Checked: {len(seo_files)} files")
    print(f"  Needed fix: {needs_fix}")
    print(f"  Fixed: {fixed}")
    print(f"  Failed: {failed}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
