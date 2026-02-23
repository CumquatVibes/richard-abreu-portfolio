#!/usr/bin/env python3
"""Generate portrait backgrounds and portraits using Gemini Imagen API."""

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
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not set")
    sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "portraits")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Reference image for face consistency
REF_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "images", "hero-portrait.png")


def load_reference_image():
    """Load and base64-encode the reference image."""
    if not os.path.exists(REF_IMAGE_PATH):
        print(f"WARNING: Reference image not found at {REF_IMAGE_PATH}")
        return None
    with open(REF_IMAGE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def generate_image_gemini(prompt, ref_image_b64=None, filename="output"):
    """Generate an image using Gemini 2.0 Flash with image generation."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent?key={API_KEY}"

    # Build content parts
    parts = []

    # If reference image provided, include it
    if ref_image_b64:
        parts.append({
            "inlineData": {
                "mimeType": "image/png",
                "data": ref_image_b64
            }
        })
        parts.append({
            "text": f"Using the person in this reference photo, generate the following image. Maintain exact facial identity, skin tone, hairstyle, and proportions:\n\n{prompt}"
        })
    else:
        parts.append({"text": prompt})

    payload = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "temperature": 0.8,
        }
    }).encode("utf-8")

    req = Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

            # Extract image from response
            candidates = data.get("candidates", [])
            if not candidates:
                print("  No candidates in response")
                return False

            content = candidates[0].get("content", {})
            parts_resp = content.get("parts", [])

            for part in parts_resp:
                if "inlineData" in part:
                    img_data = base64.b64decode(part["inlineData"]["data"])
                    mime = part["inlineData"].get("mimeType", "image/png")
                    ext = "png" if "png" in mime else "jpg"
                    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{ext}")
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    size_kb = len(img_data) / 1024
                    print(f"  -> Saved: {filename}.{ext} ({size_kb:.0f} KB)")
                    return True

            # If no image found, check for text response
            for part in parts_resp:
                if "text" in part:
                    print(f"  Text response: {part['text'][:200]}")

            return False

    except HTTPError as e:
        error_body = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        print(f"  API Error {e.code}: {error_body[:300]}")
        return False
    except Exception as e:
        print(f"  Error: {str(e)[:200]}")
        return False


# Priority prompts to generate first (background-only versions)
BACKGROUND_PROMPTS = [
    {
        "id": 1,
        "name": "warm_orange_podcast_studio",
        "prompt": "A professional indoor podcast studio setup in 16:9 aspect ratio, featuring a seamless warm orange paper backdrop mounted on support stands, visible studio equipment including softbox key lights, LED panel fill lights, overhead strip light, light stands, cables, and clamps. A modern desk centered in frame with a laptop, microphone on boom arm, headphones resting on the table, wooden floor with subtle reflections. Camera placed at eye-level, straight-on angle, moderate depth of field with background slightly soft but equipment still readable. Shot on Sony A7R IV, 50mm lens, f/2.8 for gentle background separation. Three-point lighting setup: key light from front-left, soft fill from right, subtle backlight separating the desk from backdrop. Cinematic warm studio color grading, clean shadows, realistic studio ambience, ultra-detailed, photorealistic."
    },
    {
        "id": 3,
        "name": "cinematic_film_studio_dark",
        "prompt": "A cinematic film studio setup with a dark, moody atmosphere, empty director's chair centered in the frame, three professional tungsten studio lights on stands positioned in a triangular arrangement (key light front-right, fill light front-left, backlight behind chair), visible barn doors on lights, subtle haze in the air for light beams, textured concrete floor, minimal film set props including a floor fan and wooden apple box, deep shadows with controlled highlights, shallow depth of field with soft background falloff, dramatic contrast lighting, teal-grey cinematic color grading, low-key studio ambiance, shot on a RED Komodo, 50mm lens, f/2.8 for strong subject separation, ISO 200, cinematic studio lighting, ultra-realistic, high detail, 16:9 aspect ratio, no people present."
    },
    {
        "id": 6,
        "name": "white_creator_studio",
        "prompt": "A photorealistic modern content-creator studio interior, shot in aspect ratio 16:9, featuring a clean minimalist workspace setup. The scene includes a white desk centered against a seamless paper backdrop mounted on a roll system, a white ergonomic chair tucked behind the desk, professional softbox lights on adjustable stands positioned on both sides, a camera mounted on a tripod in the foreground, and additional studio lighting equipment visible around the space. A tall indoor plant adds a natural accent to the left side, with a neutral-toned rug on the floor and exposed concrete ceiling giving an industrial-modern aesthetic. Camera angle: eye-level, straight-on, slight front-facing. Framing: wide to medium-wide shot, full studio visible. Lighting: soft cinematic studio lighting, neutral white key light with subtle warm fill. Style: modern YouTuber / content creator studio. Ultra-photorealistic, real photography look, ultra-high resolution, 8K detail, sharp textures, realistic materials, accurate shadows, clean highlights, professional color grading."
    },
    {
        "id": 20,
        "name": "warm_podcast_plants",
        "prompt": "Create an ultra-high-resolution photorealistic studio interior captured with a professional cinema or full-frame mirrorless camera. Aspect ratio 16:9, true 8K capture quality, zero noise, extreme sharpness, high dynamic range. Warm, modern podcast / content-creator studio. Rich warm orange-to-amber gradient wall lighting across the background. Large green tropical plants with clearly defined leaves positioned behind and to the sides. Black ergonomic studio chair positioned behind the desk. Natural wooden desk surface visible in the foreground. Professional podcast microphone mounted on a black boom arm extending toward the chair position. Soft key light shaping the scene evenly. Warm backlighting creating depth behind the plants. No harsh shadows. No overexposed highlights. Balanced contrast with natural falloff. No people. Cinema camera look, ISO 50, f/5.6, 35mm prime."
    },
    {
        "id": 56,
        "name": "amber_gradient_podcast_set",
        "prompt": "Ultra-high-resolution photorealistic podcast studio, true 8K, 16:9. Warm amber-to-orange gradient wall lighting. Large tropical green plants with sharp leaf detail behind the desk. Black ergonomic studio chair centered. Natural wooden desk in foreground with realistic grain. Professional podcast microphone on black boom arm extending toward chair. Soft key light, warm backlight on plants, realistic contact shadows. No people present. Cinema camera look, ISO 50, f/5.6, 35mm prime."
    },
    {
        "id": 34,
        "name": "blue_halo_portrait_bg",
        "prompt": "16:9 cinematic studio background setup for a portrait. A strong blue halo backlight creating a luminous circular gradient. Dark background fading smoothly from deep navy to black with a soft vignette, enhancing depth and focus. High contrast, professional studio lighting, cinematic color grading, ultra-detailed, photorealistic, modern editorial style. No people present."
    },
]

# Portrait prompts (with person) — priority set
PORTRAIT_PROMPTS = [
    {
        "id": 1,
        "name": "warm_orange_podcast_portrait",
        "prompt": "A cinematic 16:9 professional studio scene. The person given in the reference image is seated at a modern desk, centered in the frame, framed from mid-torso up. The subject maintains a natural, confident expression and upright professional posture. The desk setup is clean with a laptop in front. Lighting is cinematic: soft warm key light from front-left, gentle fill from right, subtle rim glow. The background features a warm orange seamless studio backdrop. Shot in a professional full-frame cinematic style, 50mm lens at f/2.8, crisp facial focus, smooth bokeh, cinematic warm color grading, ultra-realistic detail."
    },
    {
        "id": 3,
        "name": "directors_chair_moody_portrait",
        "prompt": "A powerful cinematic 16:9 portrait. The person given in the reference image is seated in a director's chair, perfectly centered. The subject sits with a calm, confident, and intense expression, wearing a tailored black suit. Lighting is dramatic and cinematic with deep contrast. Soft illumination shapes the face, edge glow separates shoulders from background. Gentle atmospheric haze enhances depth. Dark, refined film studio backdrop. Shot at 50mm f/2.8, creamy blur, sharp facial focus, teal-grey cinematic color grading, ultra-realistic skin detail, editorial portrait quality."
    },
    {
        "id": 20,
        "name": "warm_podcast_plants_portrait",
        "prompt": "Ultra-high-resolution photorealistic studio portrait in 16:9. The person given in the reference image is seated naturally at a wooden desk, front-facing. Expression is relaxed, confident, friendly, and professional. Warm modern podcast studio: rich orange-to-amber gradient wall, large green tropical plants behind. Black studio chair. Wooden desk in foreground. Soft key light on face, warm backlighting through plants. Realistic skin texture, natural imperfections. Seamless integration with environment. Cinema camera look, 8K clarity, f/4-f/5.6. Photorealistic, indistinguishable from a real professional studio photograph."
    },
]


def main():
    ref_image = load_reference_image()

    mode = sys.argv[1] if len(sys.argv) > 1 else "backgrounds"

    if mode == "backgrounds":
        prompts = BACKGROUND_PROMPTS
        print(f"Generating {len(prompts)} background images...\n")
        for i, p in enumerate(prompts, 1):
            print(f"[{i}/{len(prompts)}] #{p['id']}: {p['name']}")
            generate_image_gemini(p["prompt"], filename=f"bg_{p['id']:02d}_{p['name']}_{TIMESTAMP}")
            if i < len(prompts):
                time.sleep(2)

    elif mode == "portraits":
        if not ref_image:
            print("ERROR: Need reference image for portraits")
            sys.exit(1)
        prompts = PORTRAIT_PROMPTS
        print(f"Generating {len(prompts)} portrait images with face reference...\n")
        for i, p in enumerate(prompts, 1):
            print(f"[{i}/{len(prompts)}] #{p['id']}: {p['name']}")
            generate_image_gemini(p["prompt"], ref_image_b64=ref_image, filename=f"portrait_{p['id']:02d}_{p['name']}_{TIMESTAMP}")
            if i < len(prompts):
                time.sleep(3)

    elif mode == "all":
        print(f"Generating {len(BACKGROUND_PROMPTS)} backgrounds + {len(PORTRAIT_PROMPTS)} portraits...\n")
        for i, p in enumerate(BACKGROUND_PROMPTS, 1):
            print(f"[BG {i}/{len(BACKGROUND_PROMPTS)}] #{p['id']}: {p['name']}")
            generate_image_gemini(p["prompt"], filename=f"bg_{p['id']:02d}_{p['name']}_{TIMESTAMP}")
            time.sleep(2)

        if ref_image:
            print("\nNow generating portraits with face reference...\n")
            for i, p in enumerate(PORTRAIT_PROMPTS, 1):
                print(f"[PORTRAIT {i}/{len(PORTRAIT_PROMPTS)}] #{p['id']}: {p['name']}")
                generate_image_gemini(p["prompt"], ref_image_b64=ref_image, filename=f"portrait_{p['id']:02d}_{p['name']}_{TIMESTAMP}")
                time.sleep(3)

    print("\nDone!")


if __name__ == "__main__":
    main()
