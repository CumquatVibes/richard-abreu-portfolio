#!/usr/bin/env python3
"""Generate B-roll images for a video script using Gemini image generation."""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = "gemini-2.5-flash-preview-image-generation"


def extract_visuals(script_path):
    """Extract [VISUAL: ...] directions from a script."""
    with open(script_path) as f:
        content = f.read()
    visuals = re.findall(r'\[VISUAL:\s*(.+?)\]', content)
    return visuals


def _classify_visual(prompt):
    """Classify a visual cue into categories for style-appropriate generation.

    Returns one of: 'product', 'product_lifestyle', 'place', 'person', 'screenshot', 'generic'
    """
    lower = prompt.lower()

    # Product on white background / studio
    product_studio = {"product photo", "product image", "product shot", "clean white background",
                      "studio lighting"}
    if any(kw in lower for kw in product_studio):
        return "product"

    # Product in use / lifestyle context
    product_lifestyle = {"in use", "lifestyle", "hands using", "being used",
                         "in action", "real-world"}
    if any(kw in lower for kw in product_lifestyle):
        return "product_lifestyle"

    # Place / location / landmark / skyline
    place_kw = {"aerial", "exterior photo", "skyline", "landmark", "cityscape",
                "landscape of", "photo of", "view of", "destination"}
    if any(kw in lower for kw in place_kw):
        return "place"

    # Person portrait
    person_kw = {"photo portrait", "portrait of", "headshot"}
    if any(kw in lower for kw in person_kw):
        return "person"

    # App / software screenshot
    screenshot_kw = {"screenshot", "interface", "dashboard", "app screen", "ui of"}
    if any(kw in lower for kw in screenshot_kw):
        return "screenshot"

    return "generic"


def generate_image(prompt, output_path):
    """Generate a single B-roll image with style matched to content type."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

    visual_type = _classify_visual(prompt)

    if visual_type == "product":
        enhanced = (
            f"Clean product photography, 16:9 aspect ratio, modern minimalist style, "
            f"soft studio lighting, white or light gradient background. {prompt}. "
            f"High resolution, professional product photo, sharp details, centered composition, "
            f"no text overlay, no watermarks."
        )
    elif visual_type == "product_lifestyle":
        enhanced = (
            f"Lifestyle product photography, 16:9 aspect ratio, natural lighting, "
            f"warm tones, real-world context. {prompt}. "
            f"High resolution, authentic lifestyle shot, shallow depth of field, "
            f"product clearly visible, no text, no watermarks."
        )
    elif visual_type == "place":
        enhanced = (
            f"Professional travel/location photography, 16:9 aspect ratio, "
            f"golden hour or dramatic lighting, stunning composition. {prompt}. "
            f"Ultra high resolution, photorealistic, vibrant colors, "
            f"wide establishing shot, no text, no watermarks."
        )
    elif visual_type == "person":
        enhanced = (
            f"Professional portrait photography, 16:9 aspect ratio, "
            f"dramatic lighting, editorial style. {prompt}. "
            f"High resolution, sharp focus on face, cinematic grade, "
            f"no text, no watermarks."
        )
    elif visual_type == "screenshot":
        enhanced = (
            f"Clean UI screenshot mockup, 16:9 aspect ratio, "
            f"modern dark theme interface design. {prompt}. "
            f"High resolution, crisp text, professional software interface, "
            f"realistic app design, no watermarks."
        )
    else:
        enhanced = (
            f"Cinematic 16:9 aspect ratio, dark moody aesthetic, high contrast, "
            f"professional video B-roll shot. {prompt}. "
            f"Ultra-realistic, photographic quality, no text, no watermarks."
        )

    payload = json.dumps({
        "contents": [{"parts": [{"text": enhanced}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.8}
    }).encode()

    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    img_data = base64.b64decode(part["inlineData"]["data"])
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    return len(img_data) / 1024
        return 0
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, 'read') else str(e)
        print(f"  Error {e.code}: {err[:150]}")
        return 0


def main():
    script_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        BASE_DIR, "output", "scripts",
        "RichMind_7_Dark_Psychology_Tricks_That_Manipulators_Use_on_You_Every_Day_20260219_155540.txt"
    )

    # Extract channel and topic from filename
    basename = os.path.splitext(os.path.basename(script_path))[0]
    channel = basename.split("_")[0]

    output_dir = os.path.join(BASE_DIR, "output", "broll", basename)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating B-roll for: {basename}")
    print(f"Output: {output_dir}\n")

    visuals = extract_visuals(script_path)
    print(f"Found {len(visuals)} visual directions\n")

    generated = 0
    for i, visual in enumerate(visuals, 1):
        filename = f"broll_{i:02d}.png"
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath):
            print(f"[{i}/{len(visuals)}] SKIP (exists): {filename}")
            generated += 1
            continue

        print(f"[{i}/{len(visuals)}] {visual[:80]}...")
        size_kb = generate_image(visual, filepath)
        if size_kb:
            print(f"  -> {filename} ({size_kb:.0f} KB)")
            generated += 1
        else:
            print(f"  -> FAILED")

        if i < len(visuals):
            time.sleep(2)

    print(f"\nDone! {generated}/{len(visuals)} B-roll images generated.")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
