#!/usr/bin/env python3
"""Upload all completed videos to Google Drive."""

import json
import os
import urllib.parse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "output", "videos")
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")
ROOT_FOLDER_ID = "1VYyT9SslxDWV9lxALaFqz30Lq1lil4Xh"  # Cumquat Vibes - Video Pipeline

ACCESS_TOKEN = None


def refresh_token():
    global ACCESS_TOKEN
    with open(TOKEN_PATH) as f:
        creds = json.load(f)
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    resp = json.loads(urlopen(req).read())
    ACCESS_TOKEN = resp["access_token"]
    return ACCESS_TOKEN


def get_or_create_folder(name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    search_url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name)"
    req = Request(search_url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
    result = json.loads(urlopen(req).read())
    if result.get("files"):
        return result["files"][0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    req = Request("https://www.googleapis.com/drive/v3/files",
                  data=json.dumps(body).encode(),
                  headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"},
                  method="POST")
    result = json.loads(urlopen(req).read())
    return result["id"]


def upload_file(filepath, parent_id):
    filename = os.path.basename(filepath)

    # Check if already uploaded
    query = f"name='{filename}' and '{parent_id}' in parents and trashed=false"
    search_url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name)"
    req = Request(search_url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
    result = json.loads(urlopen(req).read())
    if result.get("files"):
        return result["files"][0]["id"], True  # Already exists

    with open(filepath, "rb") as f:
        file_data = f.read()
    boundary = "---BOUNDARY---"
    metadata = json.dumps({"name": filename, "parents": [parent_id]}).encode()
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + metadata
        + f"\r\n--{boundary}\r\nContent-Type: video/mp4\r\n\r\n".encode()
        + file_data
        + f"\r\n--{boundary}--".encode()
    )
    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink"
    req = Request(url, data=body, headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }, method="POST")
    try:
        resp = urlopen(req)
        result = json.loads(resp.read())
        return result.get("webViewLink", result["id"]), False
    except HTTPError as e:
        print(f"  Upload error: {e.code}")
        return None, False


def main():
    print("Uploading videos to Google Drive...\n")
    refresh_token()

    # Create Videos folder
    videos_folder = get_or_create_folder("Videos", ROOT_FOLDER_ID)
    print(f"Videos folder: {videos_folder}\n")

    # Create per-channel subfolders (auto-detect from video filenames)
    channel_folders = {}
    all_videos = sorted([f for f in os.listdir(VIDEOS_DIR) if f.endswith(".mp4")])
    channels_found = sorted(set(v.split("_")[0] for v in all_videos))
    for channel in channels_found:
        channel_folders[channel] = get_or_create_folder(channel, videos_folder)
    print(f"Channel folders: {', '.join(channels_found)}\n")

    # Upload each video
    videos = all_videos
    uploaded = 0

    for v in videos:
        channel = v.split("_")[0]
        folder_id = channel_folders.get(channel, videos_folder)
        filepath = os.path.join(VIDEOS_DIR, v)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)

        print(f"[{channel}] {v} ({size_mb:.1f} MB)")
        link, existed = upload_file(filepath, folder_id)
        if existed:
            print(f"  SKIP (already uploaded)")
        elif link:
            print(f"  Uploaded!")
            uploaded += 1
        else:
            print(f"  FAILED")

    # Also upload voiceovers
    audio_dir = os.path.join(BASE_DIR, "output", "audio")
    voiceovers_folder = get_or_create_folder("Voiceovers", ROOT_FOLDER_ID)

    audios = sorted([f for f in os.listdir(audio_dir) if f.endswith(".mp3")])
    for a in audios:
        channel = a.split("_")[0]
        folder_id = get_or_create_folder(channel, voiceovers_folder)
        filepath = os.path.join(audio_dir, a)
        link, existed = upload_file(filepath, folder_id)
        if not existed and link:
            print(f"  Uploaded voiceover: {a}")

    # Also upload thumbnails
    thumbs_dir = os.path.join(BASE_DIR, "output", "thumbnails")
    if os.path.exists(thumbs_dir):
        thumbs = sorted([f for f in os.listdir(thumbs_dir) if f.endswith(".png")])
        if thumbs:
            thumbs_folder = get_or_create_folder("Thumbnails", ROOT_FOLDER_ID)
            for t in thumbs:
                channel = t.split("_")[0]
                folder_id = get_or_create_folder(channel, thumbs_folder)
                filepath = os.path.join(thumbs_dir, t)
                link, existed = upload_file(filepath, folder_id)
                if not existed and link:
                    print(f"  Uploaded thumbnail: {t}")

    print(f"\nDone! {uploaded} new videos uploaded.")
    print(f"Drive folder: https://drive.google.com/drive/folders/{ROOT_FOLDER_ID}")


if __name__ == "__main__":
    main()
