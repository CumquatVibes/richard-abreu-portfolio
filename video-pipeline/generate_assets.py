#!/usr/bin/env python3
"""
Batch Asset Generator for YouTube Video Pipeline

Generates a full library of reusable visual assets using Gemini's image models:
  - B-roll images (8 per pillar + 8 generic = 48)
  - Thumbnail backgrounds (4 per pillar = 20)
  - Channel art: end screens + lower thirds (8)

Usage:
    python generate_assets.py              # Generate all assets
    python generate_assets.py --dry-run    # Preview without API calls
    python generate_assets.py --category broll        # Only b-roll
    python generate_assets.py --category thumbnails   # Only thumbnails
    python generate_assets.py --category channel_art  # Only channel art
"""

import argparse
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Import from the existing pipeline
# ---------------------------------------------------------------------------

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from produce_video import ImageGenerator, load_api_keys, BROLL_DIR

# ---------------------------------------------------------------------------
# Extended Prompt Library
# ---------------------------------------------------------------------------

# New prompts that complement the existing 3-4 per pillar in ImageGenerator.BROLL_PROMPTS.
# These expand visual variety: close-ups, wide shots, abstract/texture,
# lifestyle/editorial, and text-friendly (negative space for captions).

EXTENDED_BROLL_PROMPTS = {
    "art": [
        # Close-up / detail
        "extreme close-up of paint palette with vibrant mixed colors, amber-lit studio, shallow depth of field, 4K macro photography",
        "close-up of stylus tip drawing on a glowing tablet screen, dark background, warm amber side lighting, cinematic",
        # Wide / establishing
        "wide shot of a creative studio with canvases on easels and warm string lights, moody cinematic atmosphere, editorial photography",
        "wide angle of art gallery wall with framed prints, dramatic spotlight lighting, dark navy walls with amber accents, 4K",
        # Abstract / texture
        "abstract paint texture background, rich amber and deep navy blue brushstrokes, oil paint on canvas close-up, 4K",
        "abstract digital art visualization, flowing shapes in warm amber and dark tones, generative design, cinematic wallpaper",
        # Lifestyle / editorial
        "lifestyle shot of artist's hands holding a completed canvas print, natural window light, warm tones, editorial photography",
        # Text-friendly (negative space)
        "minimalist dark navy background with single paintbrush and amber paint splash on the right, large empty left side for text, 4K",
    ],
    "tech": [
        # Close-up / detail
        "extreme close-up of circuit board traces with amber and blue LED reflections, macro photography, dark background, 4K",
        "close-up of fingers swiping on a tablet showing API documentation, dark mode interface, warm desk lamp glow, cinematic",
        # Wide / establishing
        "wide shot of multi-monitor developer workstation in dark room, screens glowing with code, ambient blue and amber lighting, 4K",
        "wide angle of server rack room with blinking amber and blue status LEDs, cinematic perspective, moody tech aesthetic",
        # Abstract / texture
        "abstract network visualization with glowing amber nodes and dark navy connecting lines, futuristic data flow, 4K wallpaper",
        "abstract geometric wireframe pattern transitioning from dark to amber, tech-inspired digital art, cinematic quality",
        # Lifestyle / editorial
        "lifestyle shot of developer at standing desk reviewing pull request on ultrawide monitor, warm ambient lighting, editorial",
        # Text-friendly (negative space)
        "dark navy gradient background with small glowing amber circuit pattern in bottom-right corner, large empty space for text overlay, 4K",
    ],
    "business": [
        # Close-up / detail
        "extreme close-up of hand writing in leather-bound notebook with fountain pen, warm golden lighting, shallow depth of field, 4K",
        "close-up of phone screen showing revenue dashboard with green growth chart, dark background, warm lighting, cinematic",
        # Wide / establishing
        "wide shot of modern co-working space with large windows and warm sunset light, entrepreneurs at desks, cinematic composition",
        "wide angle of product packaging and shipping materials on a workspace table, warm overhead lighting, ecommerce aesthetic, 4K",
        # Abstract / texture
        "abstract upward arrows and growth chart visualization, dark navy background with amber accents, business data art, 4K",
        "abstract geometric pattern of interconnected golden hexagons on dark navy background, network concept, cinematic wallpaper",
        # Lifestyle / editorial
        "lifestyle overhead shot of brainstorming session with sticky notes coffee and laptop, warm lighting, flat lay editorial, 4K",
        # Text-friendly (negative space)
        "dark navy gradient with subtle amber chart line in bottom portion, clean large empty area for text overlay, professional, 4K",
    ],
    "wellness": [
        # Close-up / detail
        "extreme close-up of zen stones stacked with morning dew drops, warm golden sunlight, shallow depth of field, 4K",
        "close-up of hands holding warm tea in ceramic mug, soft natural window light, earth tones, peaceful photography",
        # Wide / establishing
        "wide shot of sunrise over calm ocean with amber sky, peaceful cinematic landscape, meditation backdrop, 4K",
        "wide angle of minimalist yoga space with natural wood floor and warm morning light streaming in, serene atmosphere",
        # Abstract / texture
        "abstract flowing water ripple pattern in warm amber and earth tones, zen-inspired, calming texture background, 4K",
        "abstract gradient of warm sunrise colors blending into deep navy, smooth meditation-inspired digital art, 4K wallpaper",
        # Lifestyle / editorial
        "lifestyle shot of journal open on wooden desk with candle and plant, warm natural lighting, wellness editorial photography",
        # Text-friendly (negative space)
        "soft dark gradient background with small amber lotus silhouette in bottom-right corner, large negative space for text, 4K",
    ],
    "products": [
        # Close-up / detail
        "extreme close-up of premium t-shirt fabric texture with screen-printed art detail, dramatic side lighting, 4K macro",
        "close-up of art print corner showing paper texture and color vibrancy, dark surface, warm studio lighting, product photography",
        # Wide / establishing
        "wide shot of artist merch display with prints and apparel on dark shelving, warm gallery lighting, retail showcase, 4K",
        "wide angle of open shipping box with branded tissue paper revealing art print, unboxing scene, warm lighting, editorial",
        # Abstract / texture
        "abstract collage of overlapping art print edges on dark textured surface, warm amber spotlight, creative chaos, 4K",
        "abstract dark navy background with scattered amber and warm-toned geometric brand elements, premium feel, 4K wallpaper",
        # Lifestyle / editorial
        "lifestyle shot of person hanging framed art print on modern apartment wall, warm afternoon light, home decor editorial, 4K",
        # Text-friendly (negative space)
        "dark product photography backdrop with single art print propped up on right side, large empty left area for text overlay, 4K",
    ],
    "generic": [
        # Close-up / detail
        "extreme close-up of vintage camera lens with amber light reflections, dark background, shallow depth of field, 4K macro",
        "close-up of leather journal spine and bookmark tassel, warm ambient light, dark surface, editorial detail shot",
        # Wide / establishing
        "wide shot of modern creative loft space with exposed brick and warm pendant lights, cinematic atmosphere, 4K",
        "wide angle of city skyline at golden hour through large window, silhouette perspective, warm amber tones, cinematic",
        # Abstract / texture
        "abstract dark navy and amber gradient with subtle bokeh light particles, smooth cinematic background, 4K wallpaper",
        "abstract flowing amber liquid on dark background, paint-in-water effect, high contrast, cinematic slow motion look, 4K",
        # Lifestyle / editorial
        "lifestyle overhead shot of creative desk with coffee notebook headphones and tablet, dark surface, warm lighting, 4K flat lay",
        # Text-friendly (negative space)
        "minimalist dark navy background with soft amber glow in bottom-right corner, large clean space for text overlay, 4K",
    ],
}

THUMBNAIL_PROMPTS = {
    "art": [
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy (#101922) with dramatic amber (#e8941f) paint splashes, high contrast, clear empty space on the left for text, bold cinematic lighting, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, deep dark creative studio with amber spotlight beam cutting across, high contrast, large text area on left, professional graphic design, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, abstract digital art canvas with amber and navy color explosion, bold dramatic, left side clear for text overlay, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy background with amber neon frame and art tools silhouette on right, high contrast, space for text on left, 4K",
    ],
    "tech": [
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy (#101922) with glowing amber (#e8941f) circuit lines, high contrast, clear space on left for text, futuristic tech aesthetic, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark background with holographic amber code particles, dramatic lighting, left side empty for text overlay, professional, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy with amber and blue glowing data visualization on right side, bold contrast, text space on left, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, moody dark tech workspace with amber accent screen glow, cinematic, large left area for text, 4K",
    ],
    "business": [
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy (#101922) with rising amber (#e8941f) graph line and golden light burst, high contrast, left side clear for text, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark professional backdrop with amber spotlight and subtle dollar sign pattern, bold, text area on left, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy with amber geometric shapes suggesting growth and success, high contrast, empty left for text, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, moody dark office scene with dramatic amber window light on right, cinematic, large text space on left, 4K",
    ],
    "wellness": [
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy (#101922) with warm amber (#e8941f) sunrise glow, serene but bold, clear left side for text, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, deep dark blue sky fading to warm amber horizon, dramatic contrast, text space on left, peaceful yet bold, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy with soft amber candlelight glow on right side, zen atmosphere, high contrast, left area for text, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark background with amber light rays breaking through, spiritual/uplifting feel, bold contrast, text space on left, 4K",
    ],
    "products": [
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy (#101922) with dramatic amber (#e8941f) product spotlight beam, premium feel, clear left side for text, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark luxurious background with amber accent lighting and subtle texture, high contrast, text area on left, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark navy with golden amber ribbon or swoosh on right side, premium product launch feel, left space for text, 4K",
        "YouTube thumbnail background, 16:9 aspect ratio, dark background with amber sparkle and confetti effect on right, new drop energy, bold contrast, text space on left, 4K",
    ],
}

CHANNEL_ART_PROMPTS = {
    "end_screens": [
        "YouTube end screen background, 16:9 aspect ratio, dark navy (#101922) base with subtle amber (#e8941f) geometric border pattern, two rectangular placeholder areas on right for video cards, circular area bottom-right for subscribe button, clean professional design, 4K",
        "YouTube end screen background, 16:9 aspect ratio, dark navy gradient with amber accent lines framing two video card zones on the right third, subscribe button space bottom-right, minimal elegant design, 4K",
        "YouTube end screen background, 16:9 aspect ratio, dark cinematic background with warm amber light accents, space for two video thumbnails on right side and subscribe button, brand-consistent dark navy tones, 4K",
        "YouTube end screen background, 16:9 aspect ratio, abstract dark navy with flowing amber energy lines connecting to video card placeholder areas on right, subscribe zone bottom-right, premium channel aesthetic, 4K",
    ],
    "lower_thirds": [
        "lower third graphic overlay background, wide horizontal dark navy (#101922) bar with 80% opacity, thin amber (#e8941f) accent line on top edge, semi-transparent, suitable for text overlay, clean modern design, 16:9 aspect ratio, 4K",
        "lower third graphic overlay background, wide semi-transparent dark banner at bottom, amber gradient accent on left edge fading right, professional broadcast style, 16:9 aspect ratio, 4K",
        "lower third graphic overlay background, dark navy semi-transparent rounded rectangle, amber accent dot and line on left side, modern YouTube style, 16:9 aspect ratio, 4K",
        "lower third graphic overlay background, horizontal dark navy bar with amber chevron accent on left, 75% opacity, sleek professional design for text overlay, 16:9 aspect ratio, 4K",
    ],
}

PILLARS = ["art", "tech", "business", "wellness", "products"]

# ---------------------------------------------------------------------------
# Generation Logic
# ---------------------------------------------------------------------------


def count_existing(directory):
    """Count existing image files in a directory."""
    if not directory.exists():
        return 0
    return len([f for f in directory.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])


def build_manifest(categories=None):
    """
    Build a list of all images to generate.

    Returns list of dicts: {category, subcategory, prompt, model, output_dir, filename_prefix}
    """
    manifest = []
    cats = categories or ["broll", "thumbnails", "channel_art"]

    if "broll" in cats:
        for pillar in PILLARS + ["generic"]:
            prompts = EXTENDED_BROLL_PROMPTS[pillar]
            output_dir = BROLL_DIR / pillar
            for i, prompt in enumerate(prompts):
                filename_prefix = f"broll_{pillar}_batch_{i + 1}"
                manifest.append({
                    "category": "broll",
                    "subcategory": pillar,
                    "prompt": prompt,
                    "model": "nano-banana",
                    "output_dir": output_dir,
                    "filename_prefix": filename_prefix,
                })

    if "thumbnails" in cats:
        for pillar in PILLARS:
            prompts = THUMBNAIL_PROMPTS[pillar]
            output_dir = BROLL_DIR / "thumbnails" / pillar
            for i, prompt in enumerate(prompts):
                filename_prefix = f"thumb_{pillar}_{i + 1}"
                manifest.append({
                    "category": "thumbnails",
                    "subcategory": pillar,
                    "prompt": prompt,
                    "model": "nano-banana-pro",
                    "output_dir": output_dir,
                    "filename_prefix": filename_prefix,
                })

    if "channel_art" in cats:
        for art_type, prompts in CHANNEL_ART_PROMPTS.items():
            output_dir = BROLL_DIR / "channel_art" / art_type
            for i, prompt in enumerate(prompts):
                filename_prefix = f"{art_type}_{i + 1}"
                manifest.append({
                    "category": "channel_art",
                    "subcategory": art_type,
                    "prompt": prompt,
                    "model": "nano-banana-pro",
                    "output_dir": output_dir,
                    "filename_prefix": filename_prefix,
                })

    return manifest


def filter_existing(manifest):
    """Remove items from manifest where the output file already exists (skip duplicates)."""
    filtered = []
    for item in manifest:
        output_dir = Path(item["output_dir"])
        prefix = item["filename_prefix"]
        # Check if any file with this prefix already exists
        if output_dir.exists():
            existing = [f for f in output_dir.iterdir() if f.stem.startswith(prefix)]
            if existing:
                continue
        filtered.append(item)
    return filtered


def print_summary(manifest, skipped_count):
    """Print a summary of what will be generated."""
    by_category = {}
    for item in manifest:
        cat = item["category"]
        by_category.setdefault(cat, []).append(item)

    print("=" * 60)
    print("  BATCH ASSET GENERATION PLAN")
    print("=" * 60)
    print()

    total = len(manifest)

    if "broll" in by_category:
        items = by_category["broll"]
        pillars = {}
        for item in items:
            pillars.setdefault(item["subcategory"], []).append(item)
        print(f"  B-Roll Images ({len(items)} images, nano-banana/free tier)")
        for pillar, pitems in pillars.items():
            existing = count_existing(BROLL_DIR / pillar)
            print(f"    {pillar:12s}: {len(pitems)} new  (existing: {existing})")
        print()

    if "thumbnails" in by_category:
        items = by_category["thumbnails"]
        pillars = {}
        for item in items:
            pillars.setdefault(item["subcategory"], []).append(item)
        print(f"  Thumbnail Backgrounds ({len(items)} images, nano-banana-pro)")
        for pillar, pitems in pillars.items():
            print(f"    {pillar:12s}: {len(pitems)} new")
        print()

    if "channel_art" in by_category:
        items = by_category["channel_art"]
        types = {}
        for item in items:
            types.setdefault(item["subcategory"], []).append(item)
        print(f"  Channel Art ({len(items)} images, nano-banana-pro)")
        for art_type, aitems in types.items():
            print(f"    {art_type:12s}: {len(aitems)} new")
        print()

    if skipped_count > 0:
        print(f"  Skipping {skipped_count} already-existing images")
        print()

    print(f"  TOTAL: {total} images to generate")
    print(f"  Estimated time: ~{total * 3} seconds ({total * 3 // 60} min {total * 3 % 60} sec)")
    print("=" * 60)


def generate_all(manifest, generator, dry_run=False, delay=2.0):
    """
    Generate all images in the manifest.

    Args:
        manifest: List of generation items from build_manifest()
        generator: ImageGenerator instance
        dry_run: If True, print what would be generated without API calls
        delay: Seconds to wait between API calls (rate limiting)
    """
    total = len(manifest)
    if total == 0:
        print("\nNothing to generate — all assets already exist!")
        return

    succeeded = 0
    failed = 0

    for idx, item in enumerate(manifest):
        progress = f"[{idx + 1}/{total}]"
        label = f"{item['category']}/{item['subcategory']}"
        print(f"\n{progress} {label} — {item['filename_prefix']}")
        print(f"  Model: {item['model']}")
        print(f"  Prompt: {item['prompt'][:90]}...")

        if dry_run:
            print(f"  -> (dry run, skipping API call)")
            succeeded += 1
            continue

        output_dir = Path(item["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from google.genai import types

            client = generator._get_client()
            model_id = ImageGenerator.MODELS[item["model"]]
            is_imagen = model_id.startswith("imagen-")

            timestamp = int(time.time())
            filename = f"{item['filename_prefix']}_{timestamp}.png"
            filepath = output_dir / filename

            if is_imagen:
                response = client.models.generate_images(
                    model=model_id,
                    prompt=item["prompt"],
                    config=types.GenerateImagesConfig(number_of_images=1),
                )
                if response.generated_images:
                    response.generated_images[0].image.save(str(filepath))
                else:
                    print(f"  -> No image returned")
                    failed += 1
                    continue
            else:
                response = client.models.generate_content(
                    model=model_id,
                    contents=f"Generate an image: {item['prompt']}",
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                image_saved = False
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        with open(filepath, "wb") as f:
                            f.write(part.inline_data.data)
                        image_saved = True
                        break
                if not image_saved:
                    print(f"  -> No image returned")
                    failed += 1
                    continue

            size_kb = filepath.stat().st_size / 1024
            print(f"  -> Saved: {filepath.name} ({size_kb:.0f} KB)")
            succeeded += 1

        except Exception as exc:
            print(f"  -> FAILED: {exc}")
            failed += 1

        # Rate-limit delay (skip after the last item)
        if idx < total - 1 and not dry_run:
            time.sleep(delay)

    print("\n" + "=" * 60)
    print(f"  DONE: {succeeded} succeeded, {failed} failed, {total} total")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch-generate visual assets for the YouTube video pipeline"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be generated without making API calls"
    )
    parser.add_argument(
        "--category", choices=["broll", "thumbnails", "channel_art"],
        help="Generate only a specific category (default: all)"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Seconds between API calls for rate limiting (default: 2.0)"
    )
    parser.add_argument(
        "--include-existing", action="store_true",
        help="Regenerate even if output files already exist"
    )
    parser.add_argument(
        "--model", choices=list(ImageGenerator.MODELS.keys()),
        help="Override the model for all generations (e.g. nano-banana if nano-banana-pro is 503-ing)"
    )
    args = parser.parse_args()

    # Load API key
    if not args.dry_run:
        keys = load_api_keys()
        api_key = keys.get("gemini_api_key")
        if not api_key:
            print("[ERROR] GEMINI_API_KEY not found in .env file.")
            print("[ERROR] Add GEMINI_API_KEY=your_key to shopify-theme/.env")
            sys.exit(1)
        generator = ImageGenerator(api_key)
    else:
        generator = None

    # Build manifest
    categories = [args.category] if args.category else None
    manifest = build_manifest(categories)

    # Apply model override if specified
    if args.model:
        for item in manifest:
            item["model"] = args.model

    full_count = len(manifest)

    if not args.include_existing:
        manifest = filter_existing(manifest)

    skipped = full_count - len(manifest)

    # Show summary
    print_summary(manifest, skipped)

    if len(manifest) == 0:
        return

    if args.dry_run:
        print("\n-- DRY RUN MODE --\n")
        generate_all(manifest, generator, dry_run=True)
        return

    # Single confirmation prompt
    print()
    print("Proceed with generation? (y/n) ", end="", flush=True)
    answer = input().strip().lower()
    if answer not in ("y", "yes"):
        print("Cancelled.")
        return

    print()
    generate_all(manifest, generator, dry_run=False, delay=args.delay)


if __name__ == "__main__":
    main()
