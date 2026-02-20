#!/usr/bin/env python3
"""Set up Google Drive folder structure for video pipeline backup."""

import json
import os
import urllib.request
import urllib.parse
import urllib.error

# Load credentials
with open("google_token.json") as f:
    creds = json.load(f)


def refresh_token():
    """Refresh the access token."""
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp["access_token"]


TOKEN = refresh_token()
print("Token refreshed.")


def drive_request(method, url, body=None):
    """Make an authenticated Drive API request."""
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if body:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    else:
        data = None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error = e.read().decode()
        print(f"  Error {e.code}: {error[:300]}")
        return None


def create_folder(name, parent_id=None):
    """Create a folder on Google Drive. Returns folder ID."""
    # Check if folder already exists
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    search_url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name)"
    result = drive_request("GET", search_url)

    if result and result.get("files"):
        folder_id = result["files"][0]["id"]
        print(f"  EXISTS: {name} ({folder_id})")
        return folder_id

    # Create folder
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        body["parents"] = [parent_id]

    result = drive_request("POST", "https://www.googleapis.com/drive/v3/files", body)
    if result:
        folder_id = result["id"]
        print(f"  CREATED: {name} ({folder_id})")
        return folder_id
    return None


def upload_file(local_path, parent_id, filename=None):
    """Upload a file to Google Drive."""
    if not filename:
        filename = os.path.basename(local_path)

    # Check if file already exists
    query = f"name='{filename}' and '{parent_id}' in parents and trashed=false"
    search_url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name)"
    result = drive_request("GET", search_url)

    if result and result.get("files"):
        print(f"    SKIP (exists): {filename}")
        return result["files"][0]["id"]

    # Read file
    with open(local_path, "rb") as f:
        file_data = f.read()

    # Simple upload for files under 5MB, resumable for larger
    size_mb = len(file_data) / (1024 * 1024)

    metadata = json.dumps({
        "name": filename,
        "parents": [parent_id],
    }).encode()

    # Use multipart upload
    boundary = "---BOUNDARY---"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
    ).encode() + metadata + (
        f"\r\n--{boundary}\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--".encode()

    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        print(f"    UPLOADED: {filename} ({size_mb:.1f} MB) → {result.get('webViewLink', result['id'])}")
        return result["id"]
    except urllib.error.HTTPError as e:
        error = e.read().decode()
        print(f"    Upload error {e.code}: {error[:200]}")
        return None


def main():
    print("Setting up Google Drive backup structure...\n")

    # Root folder
    root = create_folder("Cumquat Vibes - Video Pipeline")
    if not root:
        print("Failed to create root folder")
        return

    # Sub-folders
    print("\nCreating channel folders...")
    scripts_folder = create_folder("Scripts", root)
    audio_folder = create_folder("Voiceovers", root)
    broll_folder = create_folder("B-Roll", root)
    config_folder = create_folder("Config", root)
    thumbnails_folder = create_folder("Thumbnails", root)

    # Per-channel script folders
    channels = ["RichPets", "RichTech", "RichHorror", "RichMind", "HowToUseAI",
                "RichFinance", "RichLifestyle", "RichMovie", "RichMusic",
                "RichReviews", "RichNature", "RichScience", "RichTravel",
                "HowToMeditate", "EvaReyes"]

    channel_script_folders = {}
    channel_audio_folders = {}

    for ch in channels:
        channel_script_folders[ch] = create_folder(ch, scripts_folder)
        channel_audio_folders[ch] = create_folder(ch, audio_folder)

    # Upload existing scripts
    print("\nUploading scripts...")
    scripts_dir = os.path.join(os.path.dirname(__file__), "output", "scripts")
    if os.path.exists(scripts_dir):
        for fname in sorted(os.listdir(scripts_dir)):
            if not fname.endswith(".txt"):
                continue
            # Determine channel from filename
            channel = None
            for ch in channels:
                if fname.startswith(ch):
                    channel = ch
                    break
            if channel and channel in channel_script_folders:
                upload_file(os.path.join(scripts_dir, fname), channel_script_folders[channel])

    # Upload existing voiceovers
    print("\nUploading voiceovers...")
    audio_dir = os.path.join(os.path.dirname(__file__), "output", "audio")
    if os.path.exists(audio_dir):
        for fname in sorted(os.listdir(audio_dir)):
            if not fname.endswith(".mp3"):
                continue
            channel = None
            for ch in channels:
                if fname.startswith(ch):
                    channel = ch
                    break
            if channel and channel in channel_audio_folders:
                upload_file(os.path.join(audio_dir, fname), channel_audio_folders[channel])

    # Upload config files
    print("\nUploading config files...")
    config_files = ["channels_config.json", "brand_config.json"]
    for cfg in config_files:
        cfg_path = os.path.join(os.path.dirname(__file__), cfg)
        if os.path.exists(cfg_path):
            upload_file(cfg_path, config_folder)

    # Upload B-roll images if they exist
    print("\nUploading B-roll...")
    broll_dir = os.path.join(os.path.dirname(__file__), "output", "images")
    if os.path.exists(broll_dir):
        for fname in sorted(os.listdir(broll_dir)):
            if fname.endswith((".png", ".jpg", ".jpeg", ".webp")):
                channel = None
                for ch in channels:
                    if fname.lower().startswith(ch.lower()):
                        channel = ch
                        break
                parent = create_folder(channel, broll_folder) if channel else broll_folder
                upload_file(os.path.join(broll_dir, fname), parent)

    print("\n✅ Google Drive backup complete!")
    print(f"Root folder: https://drive.google.com/drive/folders/{root}")


if __name__ == "__main__":
    main()
