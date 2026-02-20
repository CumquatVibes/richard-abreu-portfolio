#!/usr/bin/env python3
"""Generate all 66 portrait images using Gemini image generation with face reference."""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import urllib.parse

API_KEY = os.environ.get("GEMINI_API_KEY", "")
DRIVE_REFRESH_TOKEN = None
DRIVE_ACCESS_TOKEN = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "portraits")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REF_IMAGE_PATH = os.path.join(BASE_DIR, "..", "images", "hero-portrait.png")
RAW_PROMPTS_PATH = "/tmp/google_doc_content.txt"

# Model for image generation
MODEL = "gemini-2.0-flash-exp-image-generation"


def load_reference_image():
    with open(REF_IMAGE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def refresh_drive_token():
    global DRIVE_ACCESS_TOKEN
    token_path = os.path.join(BASE_DIR, "google_token.json")
    with open(token_path) as f:
        creds = json.load(f)
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urlopen(req).read())
    DRIVE_ACCESS_TOKEN = resp["access_token"]
    return DRIVE_ACCESS_TOKEN


def get_or_create_drive_folder(name, parent_id=None):
    """Get or create a Drive folder."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    search_url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name)"
    req = Request(search_url, headers={"Authorization": f"Bearer {DRIVE_ACCESS_TOKEN}"})
    result = json.loads(urlopen(req).read())
    if result.get("files"):
        return result["files"][0]["id"]
    # Create
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    req = Request("https://www.googleapis.com/drive/v3/files",
                  data=json.dumps(body).encode(),
                  headers={"Authorization": f"Bearer {DRIVE_ACCESS_TOKEN}", "Content-Type": "application/json"},
                  method="POST")
    result = json.loads(urlopen(req).read())
    return result["id"]


def upload_to_drive(filepath, parent_id):
    """Upload a file to Google Drive."""
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        file_data = f.read()
    boundary = "---BOUNDARY---"
    metadata = json.dumps({"name": filename, "parents": [parent_id]}).encode()
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + metadata
        + f"\r\n--{boundary}\r\nContent-Type: image/png\r\n\r\n".encode()
        + file_data
        + f"\r\n--{boundary}--".encode()
    )
    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink"
    req = Request(url, data=body, headers={
        "Authorization": f"Bearer {DRIVE_ACCESS_TOKEN}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }, method="POST")
    try:
        resp = urlopen(req)
        result = json.loads(resp.read())
        return result.get("webViewLink", result["id"])
    except HTTPError as e:
        print(f"    Drive upload error: {e.code}")
        return None


def generate_image(prompt, ref_image_b64, filename):
    """Generate image via Gemini."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    parts = []
    if ref_image_b64:
        parts.append({"inlineData": {"mimeType": "image/png", "data": ref_image_b64}})
        parts.append({"text": f"Using the person in this reference photo, generate the following image. Maintain exact facial identity, skin tone, hairstyle, and proportions:\n\n{prompt}"})
    else:
        parts.append({"text": prompt})

    payload = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.8}
    }).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    img_data = base64.b64decode(part["inlineData"]["data"])
                    filepath = os.path.join(OUTPUT_DIR, f"{filename}.png")
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    return filepath, len(img_data) / 1024
            # Check for text-only response
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "text" in part:
                    print(f"    Text only: {part['text'][:150]}")
            return None, 0
    except HTTPError as e:
        err = e.read().decode() if hasattr(e, 'read') else str(e)
        print(f"    API Error {e.code}: {err[:200]}")
        return None, 0
    except Exception as e:
        print(f"    Error: {str(e)[:200]}")
        return None, 0


def extract_prompts_from_doc():
    """Parse all Prompt B entries from the raw Google Doc."""
    with open(RAW_PROMPTS_PATH) as f:
        content = f.read()

    prompts = []
    lines = content.split("\n")
    i = 0
    current_id = 0
    current_category = "studio"

    while i < len(lines):
        line = lines[i].strip()

        # Track categories
        if "House Backgrounds" in line:
            current_category = "house"
        elif "Plain Backgrounds" in line:
            current_category = "plain"
        elif "OUTDOOR BACKGROUND" in line:
            current_category = "outdoor"
        elif "Busy Backgrounds" in line:
            current_category = "busy"
        elif "CHRISTMAS BACKGROUND" in line:
            current_category = "christmas"
        elif "Set Backgrounds" in line:
            current_category = "set"

        # Find Prompt B lines
        is_prompt_b = False
        prompt_num = None

        # Match patterns like "1. PROMPT B", "2. Prompt B", "PROMPT B", "PROMPT 2"
        m = re.match(r'(\d+)\.\s*(?:PROMPT\s*B|Prompt\s*B)', line, re.IGNORECASE)
        if m:
            is_prompt_b = True
            prompt_num = int(m.group(1))

        if not m:
            m = re.match(r'(\d+)\.\s*PROMPT\s*2', line, re.IGNORECASE)
            if m:
                is_prompt_b = True
                prompt_num = int(m.group(1))

        # Standalone numbered prompts (plain/outdoor/busy sections)
        if not m:
            m = re.match(r'^(\d+)\.\s*Prompt:', line, re.IGNORECASE)
            if m and current_category in ("plain", "outdoor", "busy"):
                is_prompt_b = True
                prompt_num = int(m.group(1))

        # Christmas prompts without A/B distinction
        if not m:
            m = re.match(r'^(\d+)\.\s*Prompt:', line, re.IGNORECASE)
            if m and current_category == "christmas":
                is_prompt_b = True
                prompt_num = int(m.group(1))

        if is_prompt_b and prompt_num:
            # Collect the full prompt text until next section
            prompt_lines = []
            i += 1
            while i < len(lines):
                l = lines[i].strip()
                # Stop at next prompt marker or empty separator
                if re.match(r'\d+\.\s*(?:PROMPT|Prompt)', l, re.IGNORECASE):
                    break
                if l.startswith("House Backgrounds") or l.startswith("Plain Backgrounds") or \
                   l.startswith("OUTDOOR") or l.startswith("Busy Backgrounds") or \
                   l.startswith("CHRISTMAS") or l.startswith("Set Backgrounds"):
                    break
                prompt_lines.append(lines[i])
                i += 1

            prompt_text = "\n".join(prompt_lines).strip()
            # Clean up: remove leading/trailing quotes
            prompt_text = prompt_text.strip('"').strip()

            if len(prompt_text) > 50:  # Valid prompt
                slug = re.sub(r'[^a-z0-9]+', '_', current_category.lower())
                prompts.append({
                    "id": prompt_num,
                    "category": current_category,
                    "prompt": prompt_text,
                    "name": f"{slug}_{prompt_num:02d}"
                })
            continue

        i += 1

    return prompts


def main():
    print("=" * 60)
    print("GENERATING ALL 66 PORTRAITS")
    print("=" * 60)

    # Load reference image
    print("\nLoading reference image...")
    ref_image = load_reference_image()
    print(f"Reference: {REF_IMAGE_PATH}")

    # Refresh Drive token
    print("Refreshing Drive token...")
    refresh_drive_token()

    # Set up Drive folders
    print("Setting up Drive folders...")
    root_id = get_or_create_drive_folder("Cumquat Vibes - Video Pipeline")
    portraits_folder = get_or_create_drive_folder("Portraits", root_id)

    category_folders = {}
    for cat in ["studio", "house", "plain", "outdoor", "busy", "christmas", "set"]:
        category_folders[cat] = get_or_create_drive_folder(cat.capitalize(), portraits_folder)

    # Extract prompts
    print("\nParsing prompts from document...")
    prompts = extract_prompts_from_doc()
    print(f"Found {len(prompts)} portrait prompts\n")

    if not prompts:
        print("ERROR: No prompts extracted. Check parsing.")
        return

    # Generate images
    generated = 0
    failed = 0
    uploaded = 0

    for i, p in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] #{p['id']} ({p['category']}): portrait_{p['name']}")

        filename = f"portrait_{p['name']}_{TIMESTAMP}"

        # Check if already exists
        existing = os.path.join(OUTPUT_DIR, f"{filename}.png")
        if os.path.exists(existing):
            print(f"  SKIP (exists)")
            generated += 1
            continue

        filepath, size_kb = generate_image(p["prompt"], ref_image, filename)

        if filepath:
            print(f"  Generated: {size_kb:.0f} KB")
            generated += 1

            # Upload to Drive
            drive_folder = category_folders.get(p["category"], portraits_folder)
            link = upload_to_drive(filepath, drive_folder)
            if link:
                print(f"  Uploaded to Drive")
                uploaded += 1
        else:
            print(f"  FAILED")
            failed += 1

        # Rate limit
        if i < len(prompts):
            time.sleep(3)

    print(f"\n{'=' * 60}")
    print(f"COMPLETE: {generated} generated, {uploaded} uploaded, {failed} failed")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Drive: Cumquat Vibes - Video Pipeline/Portraits/")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
