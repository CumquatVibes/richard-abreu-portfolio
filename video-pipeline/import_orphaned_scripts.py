#!/usr/bin/env python3
"""Import orphaned scripts from output/scripts/ into pipeline.db.

Scans all .txt script files on disk, compares against existing video_name entries
in the database, and creates 'planned' video rows for any untracked scripts.

Extracts metadata from:
  1. Script frontmatter (---title:, channel:, format:---)
  2. Script headers (# Channel:, # Topic:, etc.)
  3. Filename structure (ChannelPrefix_Topic_Slug_Timestamp.txt)

Links .json SEO sidecar files when they share the same base name.

Usage:
    python import_orphaned_scripts.py                  # Dry run (default)
    python import_orphaned_scripts.py --commit         # Actually insert into DB
    python import_orphaned_scripts.py --channel RichTech  # Only import for one channel
"""

import argparse
import json
import os
import re
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "output", "pipeline.db")
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")

# Map filename prefixes to DB channel names (must match CHANNEL_MAP in upload script)
PREFIX_TO_CHANNEL = {
    "CumquatGaming": "CumquatGaming",
    "CumquatMotivation": "CumquatMotivation",
    "CumquatShortform": "CumquatShortform",
    "CumquatVibes": "CumquatVibes",
    "EvaReyes": "EvaReyes",
    "HowToMeditate": "HowToMeditate",
    "HowToUseAI": "HowToUseAI",
    "RichAnimation": "RichAnimation",
    "RichArt": "RichArt",
    "RichBeauty": "RichBeauty",
    "RichBusiness": "RichBusiness",
    "RichCars": "RichCars",
    "RichComedy": "RichComedy",
    "RichCooking": "RichCooking",
    "RichCrypto": "RichCrypto",
    "RichDance": "RichDance",
    "RichDesign": "RichDesign",
    "RichDIY": "RichDIY",
    "RichDiy": "RichDIY",
    "RichEducation": "RichEducation",
    "RichFamily": "RichFamily",
    "RichFashion": "RichFashion",
    "RichFinance": "RichFinance",
    "RichFitness": "RichFitness",
    "RichFood": "RichFood",
    "RichGaming": "RichGaming",
    "RichHistory": "RichHistory",
    "RichHorror": "RichHorror",
    "RichKids": "RichKids",
    "RichLifestyle": "RichLifestyle",
    "RichMemes": "RichMemes",
    "RichMind": "RichMind",
    "RichMovie": "RichMovie",
    "RichMusic": "RichMusic",
    "RichNature": "RichNature",
    "RichPets": "RichPets",
    "RichPhotography": "RichPhotography",
    "RichReviews": "RichReviews",
    "RichScience": "RichScience",
    "RichSports": "RichSports",
    "RichTech": "RichTech",
    "RichTraining": "RichTraining",
    "RichTravel": "RichTravel",
    "RichVlogging": "RichVlogging",
}

# Legacy prefixes that can't be mapped reliably
LEGACY_PATTERN = re.compile(r'^(rich\w+|cumquat\w+|howto\w+|eva\w+)\d+', re.IGNORECASE)


def parse_frontmatter(filepath):
    """Extract YAML-like frontmatter from script file."""
    meta = {}
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read(2000)  # Only need the top
    except OSError:
        return meta

    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        # Try header-style metadata (# Channel: ..., # Topic: ...)
        for line in lines[:15]:
            line = line.strip()
            m = re.match(r'^#\s*(Channel|Topic|Format|Words|Est\. Duration|Generated)\s*:\s*(.+)', line)
            if m:
                key = m.group(1).lower().replace(" ", "_").replace(".", "")
                meta[key] = m.group(2).strip()
        return meta

    # Parse --- delimited frontmatter
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r'^(\w[\w\s]*?):\s*(.+)', line)
        if m:
            meta[m.group(1).strip().lower()] = m.group(2).strip()
    return meta


def parse_filename(filename):
    """Extract channel and topic from filename.

    Expected format: ChannelPrefix_Topic_Slug[_YYYYMMDD_HHMMSS].txt
    Returns (channel, topic, video_name) or (None, None, None) if unparseable.
    """
    base = os.path.splitext(filename)[0]

    # Try each known prefix (longest first to avoid partial matches)
    sorted_prefixes = sorted(PREFIX_TO_CHANNEL.keys(), key=len, reverse=True)
    for prefix in sorted_prefixes:
        if base.startswith(prefix + "_"):
            channel = PREFIX_TO_CHANNEL[prefix]
            slug = base[len(prefix) + 1:]
            # Strip trailing timestamp
            slug_clean = re.sub(r'_\d{8}_\d{6}$', '', slug)
            topic = slug_clean.replace("_", " ")
            return channel, topic, base
        elif base.startswith(prefix) and len(base) > len(prefix):
            # Handle cases without underscore separator (rare)
            channel = PREFIX_TO_CHANNEL[prefix]
            slug = base[len(prefix):]
            if slug.startswith("_"):
                slug = slug[1:]
            slug_clean = re.sub(r'_\d{8}_\d{6}$', '', slug)
            topic = slug_clean.replace("_", " ")
            return channel, topic, base

    # Check if it's a legacy format (richbusiness35, richtech1-c8u, etc.)
    if LEGACY_PATTERN.match(base):
        return None, None, None  # Skip legacy, can't reliably map

    return None, None, None


def get_word_count(filepath):
    """Count words in a script file."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return len(f.read().split())
    except OSError:
        return 0


def count_visuals(filepath):
    """Count [VISUAL: ...] directions in a script."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return len(re.findall(r'\[VISUAL:', f.read()))
    except OSError:
        return 0


def find_seo_sidecar(script_path):
    """Find matching .json SEO sidecar for a script."""
    base = os.path.splitext(script_path)[0]
    json_path = base + ".json"
    if os.path.exists(json_path):
        try:
            with open(json_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Import orphaned scripts into pipeline DB")
    parser.add_argument("--commit", action="store_true", help="Actually insert (default is dry run)")
    parser.add_argument("--channel", type=str, help="Only import for a specific channel")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get all existing video_names
    existing = set(
        row[0] for row in conn.execute("SELECT video_name FROM videos").fetchall()
    )
    print(f"Existing videos in DB: {len(existing)}")

    # Scan all script files
    script_files = sorted(f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".txt"))
    print(f"Script files on disk:  {len(script_files)}")

    imported = 0
    skipped_exists = 0
    skipped_legacy = 0
    skipped_channel = 0
    errors = []

    for filename in script_files:
        filepath = os.path.join(SCRIPTS_DIR, filename)
        base = os.path.splitext(filename)[0]

        # Already tracked?
        if base in existing:
            skipped_exists += 1
            continue

        # Parse channel and topic from filename
        channel, topic_from_name, video_name = parse_filename(filename)
        if not channel:
            skipped_legacy += 1
            continue

        # Channel filter
        if args.channel and channel != args.channel:
            skipped_channel += 1
            continue

        # Enrich from frontmatter
        meta = parse_frontmatter(filepath)
        topic = meta.get("topic", topic_from_name)
        fmt = meta.get("format", "")

        # Script metrics
        word_count = get_word_count(filepath)
        visual_count = count_visuals(filepath)

        # Relative script path (consistent with existing records)
        rel_path = os.path.join("output", "scripts", filename)

        row = {
            "video_name": video_name,
            "channel": channel,
            "topic": topic,
            "script_path": rel_path,
            "status": "planned",
            "script_word_count": word_count,
            "script_visual_count": visual_count,
        }

        if args.commit:
            try:
                cols = list(row.keys())
                placeholders = ",".join(["?"] * len(cols))
                col_names = ",".join(cols)
                values = [row[c] for c in cols]
                conn.execute(
                    f"INSERT INTO videos ({col_names}) VALUES ({placeholders})",
                    values,
                )
                imported += 1
            except sqlite3.IntegrityError as e:
                errors.append(f"{video_name}: {e}")
        else:
            imported += 1
            if imported <= 10:
                seo = find_seo_sidecar(filepath)
                seo_note = f" [+SEO sidecar]" if seo else ""
                print(f"  WOULD IMPORT: {channel}/{topic[:60]}  ({word_count}w){seo_note}")

    if args.commit:
        conn.commit()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"  {'IMPORTED' if args.commit else 'WOULD IMPORT'}: {imported}")
    print(f"  Already in DB:   {skipped_exists}")
    print(f"  Legacy (skipped): {skipped_legacy}")
    if args.channel:
        print(f"  Other channels:  {skipped_channel}")
    if errors:
        print(f"  Errors:          {len(errors)}")
        for e in errors[:10]:
            print(f"    x {e}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
