#!/usr/bin/env python3
"""Download high-resolution museum art for RichArt video series.

Downloads CC0 Public Domain paintings from:
- Art Institute of Chicago (IIIF API, 3000px)
- Metropolitan Museum of Art (Open Access API)

Creates: broll_XX.jpg, metadata.json, asset_log.txt for each collection.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

BASE = "/Users/richardabreu/Projects/RichardAbreuPortfolio/video-pipeline/output/broll"


def fetch_json(url, retries=3):
    """Fetch JSON from URL with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VideoBot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"  FAILED: {url[:80]}... - {e}")
                return None


def download_image(url, path, retries=3):
    """Download image file with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VideoBot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                if len(data) < 5000:
                    print(f"  WARNING: tiny file ({len(data)} bytes), skipping")
                    return False
                with open(path, "wb") as f:
                    f.write(data)
                size_kb = len(data) / 1024
                print(f"  Downloaded: {os.path.basename(path)} ({size_kb:.0f} KB)")
                return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
            else:
                print(f"  FAILED download: {e}")
                return False


def write_metadata(out_dir, paintings, source, license_text="CC0 Public Domain"):
    """Write metadata.json and asset_log.txt."""
    meta = {"paintings": paintings, "source": source, "license": license_text}
    with open(os.path.join(out_dir, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    with open(os.path.join(out_dir, "asset_log.txt"), "w") as f:
        f.write(f"ASSET LOG — {os.path.basename(out_dir)}\n")
        f.write(f"All images: {license_text} via {source}\n\n")
        for i, p in enumerate(paintings):
            f.write(f"broll_{i:02d}.jpg: \"{p['title']}\" by {p['artist']} ({p['date']})\n")
            f.write(f"  Source: {p['source_url']}\n")
            f.write(f"  License: {license_text}\n\n")

    print(f"  Wrote metadata.json and asset_log.txt ({len(paintings)} paintings)")


# ── AIC helpers ──

def search_aic(query, artist_filter=None, limit=30):
    """Search Art Institute of Chicago for public domain artworks."""
    url = (
        f"https://api.artic.edu/api/v1/artworks/search?"
        f"q={urllib.parse.quote(query)}"
        f"&query[term][is_public_domain]=true"
        f"&fields=id,title,artist_title,date_display,image_id"
        f"&limit={limit}"
    )
    data = fetch_json(url)
    if not data:
        return []
    results = []
    for p in data.get("data", []):
        if not p.get("image_id"):
            continue
        if artist_filter and artist_filter.lower() not in (p.get("artist_title") or "").lower():
            continue
        results.append(p)
    return results


def download_aic(paintings_data, out_dir, start_idx=0):
    """Download paintings from AIC IIIF at 3000px. Returns list of metadata dicts."""
    downloaded = []
    idx = start_idx
    for p in paintings_data:
        img_url = f"https://www.artic.edu/iiif/2/{p['image_id']}/full/3000,/0/default.jpg"
        out_path = os.path.join(out_dir, f"broll_{idx:02d}.jpg")
        print(f"  [{idx}] {p['title']} ({p.get('date_display', '?')})")
        if download_image(img_url, out_path):
            downloaded.append({
                "id": p["id"],
                "title": p["title"],
                "artist": p.get("artist_title", "Unknown"),
                "date": p.get("date_display", ""),
                "image_id": p["image_id"],
                "image_url": img_url,
                "source_url": f"https://www.artic.edu/artworks/{p['id']}"
            })
            idx += 1
        time.sleep(0.5)
    return downloaded


# ── Met Museum helpers ──

def search_met(query, limit=20):
    """Search Met Museum for public domain artworks."""
    url = (
        f"https://collectionapi.metmuseum.org/public/collection/v1/search?"
        f"artistOrCulture=true&q={urllib.parse.quote(query)}"
        f"&isPublicDomain=true&hasImages=true"
    )
    data = fetch_json(url)
    if not data:
        return []
    return data.get("objectIDs", [])[:limit]


def get_met_object(obj_id):
    """Get Met Museum object details."""
    url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{obj_id}"
    return fetch_json(url)


def download_met(obj_ids, out_dir, start_idx=0, title_filter=None):
    """Download paintings from Met Museum. Returns list of metadata dicts."""
    downloaded = []
    idx = start_idx
    for oid in obj_ids:
        obj = get_met_object(oid)
        if not obj or not obj.get("primaryImage"):
            continue
        title = obj.get("title", "Unknown")
        if title_filter and not title_filter(title):
            continue
        img_url = obj["primaryImage"]
        out_path = os.path.join(out_dir, f"broll_{idx:02d}.jpg")
        artist = obj.get("artistDisplayName", "Unknown")
        date = obj.get("objectDate", "")
        print(f"  [{idx}] {title} — {artist} ({date})")
        if download_image(img_url, out_path):
            downloaded.append({
                "id": oid,
                "title": title,
                "artist": artist,
                "date": date,
                "image_url": img_url,
                "source_url": f"https://www.metmuseum.org/art/collection/search/{oid}"
            })
            idx += 1
        time.sleep(0.5)
        if idx - start_idx >= 15:
            break
    return downloaded


# ── Collection 1: Van Gogh ──

def download_van_gogh():
    print("\n" + "="*60)
    print("VAN GOGH COMPLETE COLLECTION")
    print("="*60)

    out_dir = os.path.join(BASE, "RichArt_Van_Gogh_Complete_Collection_Turn_Your_TV_Into_Art")
    os.makedirs(out_dir, exist_ok=True)

    # Clear existing PNGs
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    all_paintings = []

    # AIC Van Goghs
    print("\n--- Art Institute of Chicago ---")
    aic_results = search_aic("van gogh", artist_filter="Vincent van Gogh", limit=30)
    print(f"  Found {len(aic_results)} Van Gogh paintings at AIC")
    aic_paintings = download_aic(aic_results[:15], out_dir, start_idx=0)
    all_paintings.extend(aic_paintings)

    # Met Museum Van Goghs (supplement)
    if len(all_paintings) < 15:
        print("\n--- Metropolitan Museum ---")
        met_ids = search_met("Vincent van Gogh", limit=25)
        print(f"  Found {len(met_ids)} Van Gogh objects at Met")
        met_paintings = download_met(met_ids, out_dir, start_idx=len(all_paintings))
        all_paintings.extend(met_paintings)

    write_metadata(out_dir, all_paintings, "Art Institute of Chicago + Met Museum")
    print(f"\n  TOTAL: {len(all_paintings)} Van Gogh paintings downloaded")
    return len(all_paintings)


# ── Collection 2: Japanese Woodblock Prints ──

def download_japanese_prints():
    print("\n" + "="*60)
    print("JAPANESE WOODBLOCK PRINTS — HOKUSAI & HIROSHIGE")
    print("="*60)

    out_dir = os.path.join(BASE, "RichArt_Japanese_Woodblock_Prints_Hokusai_Hiroshige_4K")
    os.makedirs(out_dir, exist_ok=True)

    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    all_paintings = []

    # AIC Hokusai
    print("\n--- AIC: Hokusai ---")
    aic_hokusai = search_aic("hokusai", artist_filter="Katsushika Hokusai", limit=15)
    print(f"  Found {len(aic_hokusai)} Hokusai prints at AIC")
    hokusai_dl = download_aic(aic_hokusai[:8], out_dir, start_idx=0)
    all_paintings.extend(hokusai_dl)

    # AIC Hiroshige
    print("\n--- AIC: Hiroshige ---")
    aic_hiroshige = search_aic("hiroshige", artist_filter="Utagawa Hiroshige", limit=15)
    print(f"  Found {len(aic_hiroshige)} Hiroshige prints at AIC")
    hiroshige_dl = download_aic(aic_hiroshige[:8], out_dir, start_idx=len(all_paintings))
    all_paintings.extend(hiroshige_dl)

    # Met Museum supplement
    if len(all_paintings) < 12:
        print("\n--- Met Museum: Hokusai ---")
        met_hok_ids = search_met("Hokusai", limit=10)
        met_hok = download_met(met_hok_ids, out_dir, start_idx=len(all_paintings))
        all_paintings.extend(met_hok)

    if len(all_paintings) < 14:
        print("\n--- Met Museum: Hiroshige ---")
        met_hir_ids = search_met("Hiroshige", limit=10)
        met_hir = download_met(met_hir_ids, out_dir, start_idx=len(all_paintings))
        all_paintings.extend(met_hir)

    write_metadata(out_dir, all_paintings, "Art Institute of Chicago + Met Museum")
    print(f"\n  TOTAL: {len(all_paintings)} Japanese prints downloaded")
    return len(all_paintings)


# ── Collection 3: Impressionist Masters ──

def download_impressionists():
    print("\n" + "="*60)
    print("IMPRESSIONIST MASTERS — RENOIR, DEGAS & MONET")
    print("="*60)

    out_dir = os.path.join(BASE, "RichArt_Impressionist_Masters_Monet_Renoir_Degas_1Hr_4K_Slideshow")
    os.makedirs(out_dir, exist_ok=True)

    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    # Monet IDs already used in the dedicated Monet video (avoid these)
    monet_used_ids = {16568, 16571, 64818, 14620, 87088, 14598, 81537, 14624,
                      16564, 81539, 16549, 16554, 4783, 16584, 20545, 16544,
                      103139, 97933, 4887, 20701}

    all_paintings = []

    # AIC Renoir
    print("\n--- AIC: Renoir ---")
    aic_renoir = search_aic("renoir", artist_filter="Pierre-Auguste Renoir", limit=20)
    print(f"  Found {len(aic_renoir)} Renoir paintings at AIC")
    renoir_dl = download_aic(aic_renoir[:5], out_dir, start_idx=0)
    all_paintings.extend(renoir_dl)

    # AIC Degas
    print("\n--- AIC: Degas ---")
    aic_degas = search_aic("degas", artist_filter="Edgar Degas", limit=20)
    print(f"  Found {len(aic_degas)} Degas paintings at AIC")
    degas_dl = download_aic(aic_degas[:5], out_dir, start_idx=len(all_paintings))
    all_paintings.extend(degas_dl)

    # AIC Monet (ones NOT in the Monet video)
    print("\n--- AIC: Monet (non-duplicate) ---")
    aic_monet = search_aic("monet", artist_filter="Claude Monet", limit=30)
    monet_new = [m for m in aic_monet if m["id"] not in monet_used_ids]
    print(f"  Found {len(monet_new)} new Monet paintings at AIC")
    monet_dl = download_aic(monet_new[:4], out_dir, start_idx=len(all_paintings))
    all_paintings.extend(monet_dl)

    # Met Museum supplement (Renoir + Degas)
    if len(all_paintings) < 12:
        print("\n--- Met Museum: Renoir ---")
        met_renoir_ids = search_met("Pierre-Auguste Renoir", limit=10)
        met_renoir = download_met(met_renoir_ids, out_dir, start_idx=len(all_paintings))
        all_paintings.extend(met_renoir)

    if len(all_paintings) < 14:
        print("\n--- Met Museum: Degas ---")
        met_degas_ids = search_met("Edgar Degas", limit=10)
        # Filter to paintings (not sculptures)
        met_degas = download_met(met_degas_ids, out_dir, start_idx=len(all_paintings))
        all_paintings.extend(met_degas)

    write_metadata(out_dir, all_paintings,
                   "Art Institute of Chicago + Met Museum")
    print(f"\n  TOTAL: {len(all_paintings)} Impressionist paintings downloaded")
    return len(all_paintings)


# ── Main ──

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["vangogh", "japanese", "impressionist"]

    totals = {}
    if "vangogh" in targets:
        totals["Van Gogh"] = download_van_gogh()
    if "japanese" in targets:
        totals["Japanese Prints"] = download_japanese_prints()
    if "impressionist" in targets:
        totals["Impressionists"] = download_impressionists()

    print("\n" + "="*60)
    print("DOWNLOAD SUMMARY")
    print("="*60)
    for name, count in totals.items():
        print(f"  {name}: {count} paintings")
    print(f"  Total: {sum(totals.values())} paintings downloaded")
