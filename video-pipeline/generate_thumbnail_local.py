#!/usr/bin/env python3
from __future__ import annotations
"""Local thumbnail generator using Pillow — no API calls.

Creates YouTube thumbnails (1280x720) with bold text overlays and
channel-specific branding.  Three styles available for bandit selection:
  - bold_text: Large white text on dark gradient with accent color
  - clean_minimal: Light background, dark text, thin accent bar
  - curiosity_gap: Split layout with colored text + dark mystery panel

Usage:
    python generate_thumbnail_local.py --title "7 SECRET AI Tools" --channel rich_tech --style bold_text
    python generate_thumbnail_local.py --title "7 SECRET AI Tools" --channel rich_tech
    python generate_thumbnail_local.py --batch
"""

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import string
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "thumbnails")
DB_PATH = os.path.join(BASE_DIR, "output", "pipeline.db")
CHANNELS_CONFIG = os.path.join(BASE_DIR, "channels_config.json")

WIDTH, HEIGHT = 1280, 720
STYLES = ["bold_text", "clean_minimal", "curiosity_gap"]

# ---------------------------------------------------------------------------
# Channel colors — pulled from channels_config.json visual_theme values
# Keys match channel keys in the config.  Each entry has:
#   primary  – accent color used for highlights / branding
#   bg_start – dark end of the gradient
#   bg_end   – lighter end of the gradient
# ---------------------------------------------------------------------------
CHANNEL_COLORS = {
    "cumquat_vibes":      {"primary": "#FF8800", "bg_start": "#0D0D12", "bg_end": "#1C1410"},
    "cumquat_gaming":     {"primary": "#7B2FF7", "bg_start": "#0A0A0A", "bg_end": "#1A0A2A"},
    "cumquat_shortform":  {"primary": "#FF6B35", "bg_start": "#0A0A0A", "bg_end": "#1A1000"},
    "cumquat_motivation": {"primary": "#D4AF37", "bg_start": "#1A1A1A", "bg_end": "#2A2510"},
    "rich_tech":          {"primary": "#00D4FF", "bg_start": "#0D0D0D", "bg_end": "#0D1A22"},
    "rich_animation":     {"primary": "#FF4081", "bg_start": "#121212", "bg_end": "#1A0A14"},
    "rich_fashion":       {"primary": "#1A1A1A", "bg_start": "#0D0D0D", "bg_end": "#1A1A1A"},
    "rich_family":        {"primary": "#4CAF50", "bg_start": "#1A2A1A", "bg_end": "#0A1A0A"},
    "rich_beauty":        {"primary": "#E91E63", "bg_start": "#1A0A10", "bg_end": "#2A1020"},
    "rich_cooking":       {"primary": "#FF5722", "bg_start": "#1B1210", "bg_end": "#2A1A10"},
    "rich_education":     {"primary": "#2196F3", "bg_start": "#0A1628", "bg_end": "#0D1A30"},
    "rich_history":       {"primary": "#8D6E63", "bg_start": "#1A1510", "bg_end": "#2A2018"},
    "rich_nature":        {"primary": "#2E7D32", "bg_start": "#0A1A0A", "bg_end": "#102A10"},
    "rich_crypto":        {"primary": "#F7931A", "bg_start": "#0D0D1A", "bg_end": "#1A1510"},
    "rich_science":       {"primary": "#6200EA", "bg_start": "#0A0A1A", "bg_end": "#1A0A2A"},
    "rich_travel":        {"primary": "#00BCD4", "bg_start": "#0A1A20", "bg_end": "#0D2230"},
    "rich_vlogging":      {"primary": "#FF0000", "bg_start": "#1A0000", "bg_end": "#2A0A0A"},
    "rich_gaming":        {"primary": "#76FF03", "bg_start": "#0A0A0A", "bg_end": "#0A1A0A"},
    "rich_reviews":       {"primary": "#FF6F00", "bg_start": "#1A1200", "bg_end": "#2A1C00"},
    "rich_kids":          {"primary": "#FF9800", "bg_start": "#1A1400", "bg_end": "#2A2000"},
    "rich_pets":          {"primary": "#FF7043", "bg_start": "#1A1510", "bg_end": "#2A1C14"},
    "rich_horror":        {"primary": "#FF0000", "bg_start": "#0A0000", "bg_end": "#1A0000"},
    "rich_movie":         {"primary": "#FFD700", "bg_start": "#0D0D1A", "bg_end": "#1A1A10"},
    "rich_business":      {"primary": "#1B5E20", "bg_start": "#0A1A0A", "bg_end": "#0D200D"},
    "rich_fitness":       {"primary": "#D50000", "bg_start": "#1A0A0A", "bg_end": "#2A1010"},
    "rich_music":         {"primary": "#AA00FF", "bg_start": "#1A0A2A", "bg_end": "#220D38"},
    "rich_finance":       {"primary": "#00FF66", "bg_start": "#0A1A0A", "bg_end": "#0D220D"},
    "rich_cars":          {"primary": "#E65100", "bg_start": "#1A1000", "bg_end": "#2A1800"},
    "rich_lifestyle":     {"primary": "#455A64", "bg_start": "#121212", "bg_end": "#1E2428"},
    "rich_photography":   {"primary": "#37474F", "bg_start": "#1A1A1A", "bg_end": "#262A2E"},
    "rich_sports":        {"primary": "#1565C0", "bg_start": "#0A0A1A", "bg_end": "#0D1430"},
    "rich_food":          {"primary": "#BF360C", "bg_start": "#1A0A00", "bg_end": "#2A1200"},
    "rich_memes":         {"primary": "#FFD600", "bg_start": "#1A1A00", "bg_end": "#2A2A0A"},
    "rich_design":        {"primary": "#FFFFFF", "bg_start": "#0A0A0A", "bg_end": "#1A1A1A"},
    "rich_comedy":        {"primary": "#FF6D00", "bg_start": "#1A1A00", "bg_end": "#2A2000"},
    "rich_diy":           {"primary": "#795548", "bg_start": "#1A1510", "bg_end": "#2A2018"},
    "rich_dance":         {"primary": "#D500F9", "bg_start": "#0A001A", "bg_end": "#1A0A2A"},
    "eva_reyes":          {"primary": "#FFD700", "bg_start": "#1A0A20", "bg_end": "#2A1430"},
    "rich_mind":          {"primary": "#9B59B6", "bg_start": "#0A0A1A", "bg_end": "#1A102A"},
    "how_to_meditate":    {"primary": "#7E57C2", "bg_start": "#0A0A1A", "bg_end": "#14102A"},
    "how_to_use_ai":      {"primary": "#00BFA5", "bg_start": "#0D0D1A", "bg_end": "#0D1A1A"},
}

# Fallback for unknown channels
_DEFAULT_COLORS = {"primary": "#FFFFFF", "bg_start": "#0D0D0D", "bg_end": "#1A1A1A"}

# Channel display names (best-effort mapping)
_CHANNEL_DISPLAY = None


def _load_channel_display_names() -> dict:
    """Load pretty channel names from channels_config.json if available."""
    global _CHANNEL_DISPLAY
    if _CHANNEL_DISPLAY is not None:
        return _CHANNEL_DISPLAY
    _CHANNEL_DISPLAY = {}
    try:
        with open(CHANNELS_CONFIG) as f:
            cfg = json.load(f)
        for key, val in cfg.get("channels", {}).items():
            _CHANNEL_DISPLAY[key] = val.get("name", key)
    except Exception:
        pass
    return _CHANNEL_DISPLAY


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------
_FONT_SEARCH_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFCompactDisplay-Bold.otf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

_cached_font_path = None  # type: str | None


def _find_bold_font():
    """Return path to a usable bold sans-serif font, or None for default."""
    global _cached_font_path
    if _cached_font_path is not None:
        return _cached_font_path if _cached_font_path != "" else None
    for p in _FONT_SEARCH_PATHS:
        if os.path.exists(p):
            _cached_font_path = p
            return p
    _cached_font_path = ""
    return None


def _get_font(size: int):
    path = _find_bold_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _draw_gradient(img: Image.Image, c_start: str, c_end: str, direction: str = "vertical"):
    """Draw a linear gradient on *img* in-place."""
    draw = ImageDraw.Draw(img)
    rgb1 = _hex_to_rgb(c_start)
    rgb2 = _hex_to_rgb(c_end)
    w, h = img.size
    if direction == "vertical":
        for y in range(h):
            c = _lerp_color(rgb1, rgb2, y / max(h - 1, 1))
            draw.line([(0, y), (w, y)], fill=c)
    else:
        for x in range(w):
            c = _lerp_color(rgb1, rgb2, x / max(w - 1, 1))
            draw.line([(x, 0), (x, h)], fill=c)


# ---------------------------------------------------------------------------
# Text extraction — pick 3-5 "power words" from title
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "it", "its", "this", "that", "these", "those", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "about", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "up", "down", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "because", "if", "while", "your", "you",
    "my", "i", "me", "we", "us", "they", "them", "he", "she", "him",
    "her", "what", "which", "who", "whom", "his", "our", "their",
}


def _extract_power_words(title: str, max_words: int = 5) -> str:
    """Pull the most impactful 3-5 words from the title."""
    # Remove punctuation except ? and !
    clean = re.sub(r"[^\w\s?!]", " ", title)
    words = clean.split()

    # Keep numbers and non-stop words, preserve order
    power = [w for w in words if w.lower() not in _STOP_WORDS or w.isdigit()]

    # If everything got filtered, fall back to first few words
    if len(power) < 2:
        power = words[:max_words]

    # Cap at max_words
    power = power[:max_words]

    # If we still have too many, trim to fit nicely
    if len(power) > 4:
        power = power[:4]

    return " ".join(power).upper()


# ---------------------------------------------------------------------------
# Text rendering helpers
# ---------------------------------------------------------------------------

def _fit_text_size(draw: ImageDraw.Draw, text: str, max_width: int,
                   max_height: int, start_size: int = 120,
                   min_size: int = 36) -> tuple[ImageFont.FreeTypeFont, int]:
    """Find the largest font size that fits *text* within max_width/max_height.
    Returns (font, size)."""
    for size in range(start_size, min_size - 1, -2):
        font = _get_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= max_width and th <= max_height:
            return font, size
    return _get_font(min_size), min_size


def _draw_text_with_shadow(draw, xy, text,
                           font, fill,
                           shadow_color=(0, 0, 0),
                           shadow_offset: int = 4):
    """Draw text with a heavy drop shadow for readability."""
    x, y = xy
    # Draw shadow layers for thickness
    for dx in range(-shadow_offset, shadow_offset + 1):
        for dy in range(-shadow_offset, shadow_offset + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)
    draw.text(xy, text, font=font, fill=fill)


def _draw_text_with_outline(draw: ImageDraw.Draw, xy: tuple, text: str,
                            font, fill, outline_color=(0, 0, 0),
                            outline_width=3):
    """Draw text with an outline (stroke) for readability."""
    x, y = xy
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if abs(dx) + abs(dy) == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text(xy, text, font=font, fill=fill)


def _multiline_fit(draw: ImageDraw.Draw, text: str, max_width: int,
                   max_height: int, start_size: int = 120,
                   min_size: int = 36):
    """Word-wrap *text* and find the largest font that fits.
    Returns (lines, font, line_height)."""
    words = text.split()
    for size in range(start_size, min_size - 1, -2):
        font = _get_font(size)
        # Wrap words
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = w
            else:
                current = test
        if current:
            lines.append(current)

        # Check total height
        sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
        line_h = int((sample_bbox[3] - sample_bbox[1]) * 1.2)
        total_h = line_h * len(lines)
        if total_h <= max_height:
            return lines, font, line_h

    font = _get_font(min_size)
    sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = int((sample_bbox[3] - sample_bbox[1]) * 1.2)
    return [text], font, line_h


# ---------------------------------------------------------------------------
# Thumbnail style renderers
# ---------------------------------------------------------------------------

def _render_bold_text(title: str, channel: str) -> Image.Image:
    """Large white bold text on dark gradient, accent color highlights."""
    colors = CHANNEL_COLORS.get(channel, _DEFAULT_COLORS)
    img = Image.new("RGB", (WIDTH, HEIGHT))
    _draw_gradient(img, colors["bg_start"], colors["bg_end"])

    draw = ImageDraw.Draw(img)
    primary = _hex_to_rgb(colors["primary"])

    # Accent stripe at top
    draw.rectangle([(0, 0), (WIDTH, 8)], fill=primary)

    # Main text
    power_text = _extract_power_words(title)
    max_w = int(WIDTH * 0.85)
    max_h = int(HEIGHT * 0.50)
    lines, font, line_h = _multiline_fit(draw, power_text, max_w, max_h,
                                         start_size=140, min_size=48)

    total_h = line_h * len(lines)
    y_start = (HEIGHT - total_h) // 2 - 30  # nudge up slightly

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (WIDTH - tw) // 2
        y = y_start + i * line_h
        _draw_text_with_shadow(draw, (x, y), line, font, fill=(255, 255, 255),
                               shadow_offset=5)

    # Accent underline below text
    underline_y = y_start + total_h + 15
    bar_w = min(int(WIDTH * 0.4), 500)
    bar_x = (WIDTH - bar_w) // 2
    draw.rectangle([(bar_x, underline_y), (bar_x + bar_w, underline_y + 6)],
                   fill=primary)

    # Channel name at bottom right
    _draw_channel_badge(draw, channel, colors)

    return img


def _render_clean_minimal(title: str, channel: str) -> Image.Image:
    """Clean white/light background, dark text, thin accent bar at bottom."""
    colors = CHANNEL_COLORS.get(channel, _DEFAULT_COLORS)
    primary = _hex_to_rgb(colors["primary"])

    # Light background with very subtle gradient
    img = Image.new("RGB", (WIDTH, HEIGHT), (248, 248, 248))
    draw = ImageDraw.Draw(img)

    # Subtle top-to-bottom warmth
    for y in range(HEIGHT):
        t = y / HEIGHT
        gray = int(248 - t * 10)
        draw.line([(0, y), (WIDTH, y)], fill=(gray, gray, gray + 2))

    # Main text — dark
    power_text = _extract_power_words(title)
    max_w = int(WIDTH * 0.75)
    max_h = int(HEIGHT * 0.45)
    lines, font, line_h = _multiline_fit(draw, power_text, max_w, max_h,
                                         start_size=120, min_size=44)

    total_h = line_h * len(lines)
    y_start = (HEIGHT - total_h) // 2 - 20

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (WIDTH - tw) // 2
        y = y_start + i * line_h
        draw.text((x, y), line, font=font, fill=(28, 28, 30))

    # Thin accent line at bottom
    draw.rectangle([(0, HEIGHT - 12), (WIDTH, HEIGHT)], fill=primary)

    # Channel name at bottom-left in dark text
    display = _load_channel_display_names().get(channel, channel.replace("_", " ").title())
    small_font = _get_font(22)
    draw.text((30, HEIGHT - 50), display, font=small_font, fill=(100, 100, 100))

    return img


def _render_curiosity_gap(title: str, channel: str) -> Image.Image:
    """Split layout — left bold colored text, right dark mystery panel."""
    colors = CHANNEL_COLORS.get(channel, _DEFAULT_COLORS)
    primary = _hex_to_rgb(colors["primary"])
    bg_dark = _hex_to_rgb(colors["bg_start"])

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    split_x = int(WIDTH * 0.58)

    # Left panel — dark with subtle gradient
    left = Image.new("RGB", (split_x, HEIGHT))
    _draw_gradient(left, colors["bg_end"], colors["bg_start"])
    img.paste(left, (0, 0))

    # Right panel — deeper dark
    right_color = _lerp_color(bg_dark, (0, 0, 0), 0.3)
    draw.rectangle([(split_x, 0), (WIDTH, HEIGHT)], fill=right_color)

    # Vertical accent stripe at split
    draw.rectangle([(split_x - 3, 0), (split_x + 3, HEIGHT)], fill=primary)

    # Left side: bold text with "?" or "..."
    power_text = _extract_power_words(title, max_words=4)
    # Append curiosity trigger
    if "?" not in power_text:
        power_text += "?"

    max_w = int(split_x * 0.82)
    max_h = int(HEIGHT * 0.55)
    lines, font, line_h = _multiline_fit(draw, power_text, max_w, max_h,
                                         start_size=110, min_size=42)

    total_h = line_h * len(lines)
    y_start = (HEIGHT - total_h) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (split_x - tw) // 2
        y = y_start + i * line_h
        _draw_text_with_outline(draw, (x, y), line, font, fill=primary,
                                outline_color=(0, 0, 0), outline_width=3)

    # Right side: subtle "?" watermark
    wm_font = _get_font(300)
    wm_color = tuple(min(c + 20, 255) for c in right_color)
    right_cx = split_x + (WIDTH - split_x) // 2
    bbox = draw.textbbox((0, 0), "?", font=wm_font)
    wm_w = bbox[2] - bbox[0]
    wm_h = bbox[3] - bbox[1]
    draw.text((right_cx - wm_w // 2, (HEIGHT - wm_h) // 2 - 40),
              "?", font=wm_font, fill=wm_color)

    # Channel name at bottom of right panel
    display = _load_channel_display_names().get(channel, channel.replace("_", " ").title())
    small_font = _get_font(20)
    bbox = draw.textbbox((0, 0), display, font=small_font)
    tw = bbox[2] - bbox[0]
    draw.text((right_cx - tw // 2, HEIGHT - 50), display, font=small_font,
              fill=tuple(min(c + 60, 255) for c in right_color))

    return img


def _draw_channel_badge(draw: ImageDraw.Draw, channel: str, colors: dict):
    """Draw small channel name at bottom-right corner."""
    display = _load_channel_display_names().get(channel, channel.replace("_", " ").title())
    small_font = _get_font(22)
    primary = _hex_to_rgb(colors["primary"])

    bbox = draw.textbbox((0, 0), display, font=small_font)
    tw = bbox[2] - bbox[0]
    x = WIDTH - tw - 30
    y = HEIGHT - 50
    _draw_text_with_shadow(draw, (x, y), display, small_font, fill=primary,
                           shadow_offset=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_STYLE_RENDERERS = {
    "bold_text": _render_bold_text,
    "clean_minimal": _render_clean_minimal,
    "curiosity_gap": _render_curiosity_gap,
}


def generate_thumbnail_local(title: str, channel: str,
                             style=None,
                             output_dir=None):
    """Generate a YouTube thumbnail locally and return the output path.

    Parameters
    ----------
    title : str
        Video title.
    channel : str
        Channel key (e.g. "rich_tech").
    style : str, optional
        One of "bold_text", "clean_minimal", "curiosity_gap".
        If None, one is chosen at random.
    output_dir : str, optional
        Directory to save the thumbnail. Defaults to output/thumbnails/.

    Returns
    -------
    str
        Absolute path to the generated PNG thumbnail.
    """
    if style is None:
        style = random.choice(STYLES)
    if style not in _STYLE_RENDERERS:
        raise ValueError(f"Unknown style '{style}'. Choose from: {STYLES}")

    renderer = _STYLE_RENDERERS[style]
    img = renderer(title, channel)

    # Build output path
    out = output_dir or OUTPUT_DIR
    os.makedirs(out, exist_ok=True)

    # Deterministic but short filename
    slug = re.sub(r"[^\w]+", "_", title.lower()).strip("_")[:60]
    fname = f"{channel}_{slug}_thumb.png"
    path = os.path.join(out, fname)

    img.save(path, "PNG", optimize=True)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Batch mode — process produced videos missing thumbnails from pipeline.db
# ---------------------------------------------------------------------------

def _batch_generate():
    """Generate thumbnails for all produced videos that don't have one yet."""
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Videos that are produced but have no thumbnail_path set
    rows = conn.execute("""
        SELECT video_name, channel, topic
        FROM videos
        WHERE status IN ('produced', 'uploaded', 'published')
          AND (thumbnail_path IS NULL OR thumbnail_path = '')
        ORDER BY created_at DESC
    """).fetchall()

    if not rows:
        print("No produced videos missing thumbnails.")
        conn.close()
        return

    print(f"Found {len(rows)} video(s) missing thumbnails.\n")

    generated = 0
    skipped = 0

    for row in rows:
        video_name = row["video_name"]
        channel = row["channel"]
        title = row["topic"] or video_name.replace("_", " ")

        # Check if thumbnail already exists on disk
        slug = re.sub(r"[^\w]+", "_", title.lower()).strip("_")[:60]
        expected = os.path.join(OUTPUT_DIR, f"{channel}_{slug}_thumb.png")
        if os.path.exists(expected):
            print(f"  SKIP (exists): {expected}")
            # Update DB to point to existing file
            conn.execute("UPDATE videos SET thumbnail_path = ? WHERE video_name = ?",
                         (expected, video_name))
            skipped += 1
            continue

        try:
            path = generate_thumbnail_local(title, channel)
            conn.execute("UPDATE videos SET thumbnail_path = ? WHERE video_name = ?",
                         (path, video_name))
            generated += 1
            print(f"  OK: {path}")
        except Exception as e:
            print(f"  FAIL ({video_name}): {e}")

    conn.commit()
    conn.close()

    print(f"\nDone. Generated: {generated}, Skipped: {skipped}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube thumbnails locally with Pillow."
    )
    parser.add_argument("--title", type=str, help="Video title")
    parser.add_argument("--channel", type=str, help="Channel key (e.g. rich_tech)")
    parser.add_argument("--style", type=str, choices=STYLES,
                        help="Thumbnail style (random if omitted)")
    parser.add_argument("--batch", action="store_true",
                        help="Generate for all produced videos missing thumbnails")
    parser.add_argument("--output-dir", type=str,
                        help="Override output directory")

    args = parser.parse_args()

    if args.batch:
        _batch_generate()
        return

    if not args.title or not args.channel:
        parser.error("--title and --channel are required (or use --batch)")

    path = generate_thumbnail_local(
        title=args.title,
        channel=args.channel,
        style=args.style,
        output_dir=args.output_dir,
    )
    print(f"Thumbnail saved: {path}")
    print(f"Style: {args.style or 'random'}")
    print(f"Size: {WIDTH}x{HEIGHT}")


if __name__ == "__main__":
    main()
