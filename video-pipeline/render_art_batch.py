#!/usr/bin/env python3
"""Render 3 RichArt 1-hour 4K slideshow videos."""

import glob
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(__file__))
from utils.ambient import assemble_art_slideshow

BASE = os.path.dirname(__file__)
VIDEOS_DIR = os.path.join(BASE, "output", "videos")
BROLL_DIR = os.path.join(BASE, "output", "broll")
DB_PATH = os.path.join(BASE, "output", "pipeline.db")

COLLECTIONS = [
    {
        "name": "RichArt_Van_Gogh_Complete_Collection_Turn_Your_TV_Into_Art",
        "broll": "RichArt_Van_Gogh_Complete_Collection_Turn_Your_TV_Into_Art",
        "output": "RichArt_Van_Gogh_Complete_Collection_1Hr_4K_Slideshow.mp4",
    },
    {
        "name": "RichArt_Japanese_Woodblock_Prints_Hokusai_Hiroshige_4K",
        "broll": "RichArt_Japanese_Woodblock_Prints_Hokusai_Hiroshige_4K",
        "output": "RichArt_Japanese_Woodblock_Prints_1Hr_4K_Slideshow.mp4",
    },
    {
        "name": "RichArt_Impressionist_Masters_Monet_Renoir_Degas_1Hr_4K_Slideshow",
        "broll": "RichArt_Impressionist_Masters_Monet_Renoir_Degas_1Hr_4K_Slideshow",
        "output": "RichArt_Impressionist_Masters_1Hr_4K_Slideshow.mp4",
    },
]


def register_video(video_name, output_path, duration_sec, size_mb):
    """Register video in pipeline.db."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO videos (video_name, channel, status, video_path, "
        "video_duration_sec, video_size_mb) VALUES (?, ?, ?, ?, ?, ?)",
        (video_name, "RichArt", "produced", output_path, duration_sec, size_mb)
    )
    conn.commit()
    conn.close()


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else [c["name"] for c in COLLECTIONS]

    for col in COLLECTIONS:
        if col["name"] not in targets and not any(t in col["name"] for t in targets):
            continue

        broll_dir = os.path.join(BROLL_DIR, col["broll"])
        output_path = os.path.join(VIDEOS_DIR, col["output"])

        # Get sorted images
        images = sorted(glob.glob(os.path.join(broll_dir, "broll_*.jpg")))
        if not images:
            print(f"SKIP {col['name']}: no images found")
            continue

        # Calculate duration per image for 1 hour total
        duration_per_image = 3600 // len(images)

        print(f"\n{'='*60}")
        print(f"RENDERING: {col['name']}")
        print(f"  Images: {len(images)}")
        print(f"  Duration per image: {duration_per_image}s ({duration_per_image/60:.1f} min)")
        print(f"  Total: {len(images) * duration_per_image}s")
        print(f"  Output: {output_path}")
        print(f"{'='*60}")

        success, size_mb, duration_sec = assemble_art_slideshow(
            images=images,
            output_path=output_path,
            duration_per_image=duration_per_image,
            resolution="4k",
            verbose=True,
        )

        if success:
            print(f"\n  SUCCESS: {size_mb:.0f} MB, {duration_sec/3600:.1f}h")
            register_video(
                col["output"].replace(".mp4", ""),
                f"output/videos/{col['output']}",
                duration_sec, size_mb,
            )
        else:
            print(f"\n  FAILED: {col['name']}")


if __name__ == "__main__":
    main()
