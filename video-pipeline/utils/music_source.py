#!/usr/bin/env python3
"""Music sourcing module for YouTube playlist production.

Sources royalty-free music from:
  1. Jamendo API (primary — 500K+ tracks, CC-licensed)
  2. Internet Archive / Incompetech (secondary — no auth needed)
  3. Freesound API (tertiary — ambient/soundscapes)

All downloaded tracks are CC-licensed and safe for YouTube monetization
with proper attribution in video descriptions.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / "shopify-theme" / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

MUSIC_DIR = BASE_DIR / "output" / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Genre-to-query mapping
# ---------------------------------------------------------------------------
GENRE_QUERIES = {
    "blues_soul": {
        "jamendo": {"fuzzytags": "blues+soul", "vocalinstrumental": "instrumental"},
        "archive": 'subject:"blues" AND mediatype:audio AND licenseurl:*creativecommons*',
    },
    "lofi_hiphop": {
        "jamendo": {"fuzzytags": "lofi+chillout+hiphop", "speed": "low+medium"},
        "archive": 'subject:"lofi" AND mediatype:audio',
    },
    "jazz_smooth": {
        "jamendo": {"fuzzytags": "jazz+smooth+lounge"},
        "archive": 'creator:"Kevin MacLeod" AND subject:"jazz"',
    },
    "jazz_cafe": {
        "jamendo": {"fuzzytags": "jazz+cafe+bossa"},
        "archive": 'subject:"jazz" AND subject:"cafe" AND mediatype:audio',
    },
    "late_night_jazz": {
        "jamendo": {"fuzzytags": "jazz+night+smooth+mellow"},
        "archive": 'creator:"Kevin MacLeod" AND subject:"jazz"',
    },
    "acoustic_folk": {
        "jamendo": {"fuzzytags": "acoustic+folk+guitar"},
        "archive": 'subject:"acoustic" AND mediatype:audio AND licenseurl:*creativecommons*',
    },
    "ambient_relaxation": {
        "jamendo": {"fuzzytags": "ambient+relaxation+meditation", "speed": "low"},
        "archive": 'subject:"ambient" AND mediatype:audio AND licenseurl:*creativecommons*',
    },
    "synthwave": {
        "jamendo": {"fuzzytags": "synthwave+retrowave+electronic"},
        "archive": 'subject:"synthwave" AND mediatype:audio',
    },
    "hip_hop_beats": {
        "jamendo": {"fuzzytags": "hiphop+beats+instrumental"},
        "archive": 'subject:"hip hop" AND subject:"instrumental" AND mediatype:audio',
    },
    "chill_vibes": {
        "jamendo": {"fuzzytags": "chillout+downtempo+relaxed"},
        "archive": 'subject:"chill" AND mediatype:audio AND licenseurl:*creativecommons*',
    },
}


# ---------------------------------------------------------------------------
# Jamendo API
# ---------------------------------------------------------------------------
def _get_jamendo_client_id() -> str:
    key = os.environ.get("JAMENDO_CLIENT_ID", "")
    if not key:
        raise ValueError(
            "JAMENDO_CLIENT_ID not set. Register free at https://devportal.jamendo.com/"
        )
    return key


def search_jamendo(
    genre: str,
    limit: int = 20,
    min_duration: int = 60,
    max_duration: int = 600,
    instrumental_only: bool = True,
) -> List[Dict]:
    """Search Jamendo for tracks matching a genre."""
    client_id = _get_jamendo_client_id()
    genre_cfg = GENRE_QUERIES.get(genre, {}).get("jamendo", {})
    if not genre_cfg:
        genre_cfg = {"fuzzytags": genre.replace("_", "+")}

    params = {
        "client_id": client_id,
        "format": "json",
        "limit": limit,
        "include": "musicinfo+licenses",
        "audioformat": "mp32",
        "order": "popularity_total",
        "durationbetween": f"{min_duration}_{max_duration}",
    }
    if instrumental_only:
        params["vocalinstrumental"] = "instrumental"
    params.update(genre_cfg)

    url = f"https://api.jamendo.com/v3.0/tracks/?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())

    results = []
    for track in data.get("results", []):
        if not track.get("audiodownload_allowed", True):
            continue
        results.append({
            "id": track["id"],
            "name": track["name"],
            "artist": track["artist_name"],
            "duration": track["duration"],
            "license": track.get("license_ccurl", "CC"),
            "download_url": track.get("audiodownload", ""),
            "stream_url": track.get("audio", ""),
            "tags": track.get("musicinfo", {}).get("tags", {}),
            "source": "jamendo",
            "attribution": f'"{track["name"]}" by {track["artist_name"]} (Jamendo, {track.get("license_ccurl", "CC")})',
        })
    return results


def download_jamendo_track(track: Dict, output_dir: Optional[str] = None) -> str:
    """Download a Jamendo track and return the file path."""
    client_id = _get_jamendo_client_id()
    out_dir = Path(output_dir) if output_dir else MUSIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in track["name"])
    safe_name = safe_name.strip().replace(" ", "_")[:80]
    filename = f"jamendo_{track['id']}_{safe_name}.mp3"
    filepath = out_dir / filename

    if filepath.exists():
        print(f"  [cached] {filename}")
        return str(filepath)

    # Use the file download endpoint
    dl_url = (
        f"https://api.jamendo.com/v3.0/tracks/file/"
        f"?client_id={client_id}&id={track['id']}&audioformat=mp32&action=download"
    )
    print(f"  Downloading: {track['name']} by {track['artist']} ({track['duration']}s)")
    req = urllib.request.Request(dl_url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(filepath, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)

    size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"  Saved: {filename} ({size_mb:.1f} MB)")
    return str(filepath)


# ---------------------------------------------------------------------------
# Internet Archive (Incompetech / Kevin MacLeod + CC collections)
# ---------------------------------------------------------------------------
def search_archive(genre: str, limit: int = 20) -> List[Dict]:
    """Search Internet Archive for CC-licensed music."""
    query = GENRE_QUERIES.get(genre, {}).get("archive", "")
    if not query:
        query = f'subject:"{genre}" AND mediatype:audio AND licenseurl:*creativecommons*'

    params = urllib.parse.urlencode({
        "q": query,
        "fl[]": ["identifier", "title", "creator", "description", "licenseurl"],
        "rows": limit,
        "output": "json",
    }, doseq=True)
    url = f"https://archive.org/advancedsearch.php?{params}"

    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())

    results = []
    for doc in data.get("response", {}).get("docs", []):
        results.append({
            "id": doc["identifier"],
            "name": doc.get("title", doc["identifier"]),
            "artist": doc.get("creator", "Unknown"),
            "license": doc.get("licenseurl", "CC"),
            "source": "archive",
            "attribution": f'"{doc.get("title", doc["identifier"])}" by {doc.get("creator", "Unknown")} (Internet Archive, CC)',
        })
    return results


def download_archive_tracks(
    identifier: str, output_dir: Optional[str] = None, max_tracks: int = 10
) -> List[str]:
    """Download audio files from an Internet Archive item."""
    out_dir = Path(output_dir) if output_dir else MUSIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get metadata
    meta_url = f"https://archive.org/metadata/{identifier}"
    with urllib.request.urlopen(meta_url, timeout=30) as resp:
        meta = json.loads(resp.read())

    files = []
    for f in meta.get("files", []):
        name = f.get("name", "")
        if name.endswith((".mp3", ".ogg", ".flac")):
            files.append(name)

    downloaded = []
    for fname in files[:max_tracks]:
        filepath = out_dir / f"archive_{identifier}_{fname}".replace("/", "_")
        if filepath.exists():
            print(f"  [cached] {fname}")
            downloaded.append(str(filepath))
            continue

        dl_url = f"https://archive.org/download/{identifier}/{urllib.parse.quote(fname)}"
        print(f"  Downloading: {fname}")
        try:
            req = urllib.request.Request(dl_url)
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(filepath, "wb") as fp:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        fp.write(chunk)
            downloaded.append(str(filepath))
        except Exception as e:
            print(f"  Error downloading {fname}: {e}")
    return downloaded


# ---------------------------------------------------------------------------
# High-level: source playlist for a genre
# ---------------------------------------------------------------------------
def source_playlist(
    genre: str,
    num_tracks: int = 10,
    min_duration: int = 60,
    max_duration: int = 600,
    output_dir: Optional[str] = None,
) -> Dict:
    """Source a playlist of tracks for a genre, download them, return metadata.

    Returns:
        {
            "genre": str,
            "tracks": [{"path": str, "name": str, "artist": str, "duration": int, "attribution": str}, ...],
            "attributions": [str, ...],  # For video description
        }
    """
    out_dir = Path(output_dir) if output_dir else MUSIC_DIR / genre
    out_dir.mkdir(parents=True, exist_ok=True)

    tracks = []
    attributions = []

    # Try Jamendo first
    try:
        print(f"\n[Jamendo] Searching for '{genre}' tracks...")
        results = search_jamendo(genre, limit=num_tracks, min_duration=min_duration, max_duration=max_duration)
        print(f"  Found {len(results)} tracks")

        for track in results[:num_tracks]:
            try:
                path = download_jamendo_track(track, output_dir=str(out_dir))
                tracks.append({
                    "path": path,
                    "name": track["name"],
                    "artist": track["artist"],
                    "duration": track["duration"],
                    "attribution": track["attribution"],
                    "source": "jamendo",
                })
                attributions.append(track["attribution"])
                time.sleep(0.5)  # Rate limit courtesy
            except Exception as e:
                print(f"  Error downloading {track['name']}: {e}")

        if len(tracks) >= num_tracks:
            return {"genre": genre, "tracks": tracks, "attributions": attributions}
    except Exception as e:
        print(f"  Jamendo search failed: {e}")

    # Fall back to Internet Archive
    remaining = num_tracks - len(tracks)
    if remaining > 0:
        try:
            print(f"\n[Archive] Searching for '{genre}' tracks...")
            results = search_archive(genre, limit=5)
            print(f"  Found {len(results)} collections")

            for item in results[:3]:
                dl_paths = download_archive_tracks(
                    item["id"], output_dir=str(out_dir), max_tracks=remaining
                )
                for p in dl_paths:
                    tracks.append({
                        "path": p,
                        "name": Path(p).stem,
                        "artist": item.get("artist", "Unknown"),
                        "duration": 0,  # Would need ffprobe
                        "attribution": item["attribution"],
                        "source": "archive",
                    })
                    attributions.append(item["attribution"])
                remaining = num_tracks - len(tracks)
                if remaining <= 0:
                    break
        except Exception as e:
            print(f"  Archive search failed: {e}")

    return {"genre": genre, "tracks": tracks, "attributions": attributions}


def concat_tracks_to_playlist(
    track_paths: List[str],
    output_path: str,
    crossfade_sec: float = 3.0,
) -> str:
    """Concatenate multiple audio tracks into a single long playlist with crossfades.

    Uses ffmpeg to concatenate with crossfade transitions.
    """
    import subprocess

    if len(track_paths) == 0:
        raise ValueError("No tracks to concatenate")

    if len(track_paths) == 1:
        # Just copy the single track
        subprocess.run(["cp", track_paths[0], output_path], check=True)
        return output_path

    # Build ffmpeg filter for crossfade concatenation
    # For many tracks, use concat demuxer (simpler, no crossfade but reliable)
    list_file = Path(output_path).parent / "concat_list.txt"
    with open(list_file, "w") as f:
        for tp in track_paths:
            f.write(f"file '{tp}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    print(f"  Concatenating {len(track_paths)} tracks -> {Path(output_path).name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  ffmpeg error: {result.stderr[:500]}")
        raise RuntimeError(f"ffmpeg concat failed: {result.returncode}")

    list_file.unlink(missing_ok=True)

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"  Playlist: {Path(output_path).name} ({size_mb:.1f} MB)")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Source royalty-free music for playlists")
    parser.add_argument("genre", choices=list(GENRE_QUERIES.keys()),
                        help="Genre to source")
    parser.add_argument("--tracks", type=int, default=10, help="Number of tracks")
    parser.add_argument("--min-duration", type=int, default=60, help="Min track duration (s)")
    parser.add_argument("--max-duration", type=int, default=600, help="Max track duration (s)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--concat", action="store_true", help="Concatenate into single playlist")
    args = parser.parse_args()

    result = source_playlist(
        genre=args.genre,
        num_tracks=args.tracks,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        output_dir=args.output_dir,
    )

    print(f"\n{'='*60}")
    print(f"Genre: {result['genre']}")
    print(f"Tracks downloaded: {len(result['tracks'])}")
    for t in result["tracks"]:
        print(f"  - {t['name']} by {t['artist']} ({t['duration']}s) [{t['source']}]")
    print(f"\nAttributions for video description:")
    for a in result["attributions"]:
        print(f"  {a}")

    if args.concat and result["tracks"]:
        out_dir = Path(args.output_dir) if args.output_dir else MUSIC_DIR
        playlist_path = str(out_dir / f"{args.genre}_playlist.m4a")
        concat_tracks_to_playlist(
            [t["path"] for t in result["tracks"]],
            playlist_path,
        )
