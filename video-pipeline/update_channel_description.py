#!/usr/bin/env python3
"""Update the Cumquat Vibes channel description and branding metadata."""

import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")

MAIN_CHANNEL_ID = "UCThXDUhXqcui2HqBv4MUBBA"

NEW_DESCRIPTION = """Cumquat Vibes — Veteran-owned design studio creating original art, apparel, and lifestyle products with a citrus-coastal aesthetic.

What you'll find here:
- Product showcases and design drops (tees, hoodies, totes, stickers, candles & more)
- Adobe Fresco tutorials and digital illustration walkthroughs
- Behind-the-scenes of running a print-on-demand brand
- Design tips for creators, solopreneurs, and POD sellers

Created with love in Adobe Fresco by Richard Abreu — Navy veteran, graphic designer, and creative entrepreneur.

Shop the collection: https://cumquatvibes.com
Follow for new drops, design tutorials, and creative inspiration.

#CumquatVibes #PrintOnDemand #AdobeFresco #VeteranOwned #GraphicDesign"""


def refresh_token():
    """Refresh the OAuth access token."""
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    payload = json.dumps({
        "client_id": token_data["client_id"],
        "client_secret": token_data["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = Request(
        token_data["token_uri"],
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    token_data["token"] = data["access_token"]
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    return data["access_token"]


def get_channel_info(access_token):
    """Get current channel info."""
    url = (
        f"https://www.googleapis.com/youtube/v3/channels"
        f"?part=snippet,brandingSettings&id={MAIN_CHANNEL_ID}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

    with urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["items"][0]


def update_channel(access_token, channel_data):
    """Update channel description."""
    # Update snippet description
    channel_data["snippet"]["description"] = NEW_DESCRIPTION

    # Also update branding settings
    if "brandingSettings" not in channel_data:
        channel_data["brandingSettings"] = {}
    if "channel" not in channel_data["brandingSettings"]:
        channel_data["brandingSettings"]["channel"] = {}

    channel_data["brandingSettings"]["channel"]["description"] = NEW_DESCRIPTION
    channel_data["brandingSettings"]["channel"]["keywords"] = (
        "cumquat vibes veteran owned print on demand adobe fresco "
        "graphic design POD shopify etsy illustration digital art "
        "citrus coastal aesthetic design tutorials creative entrepreneur"
    )

    # Update brandingSettings first (separate call required)
    branding_url = "https://www.googleapis.com/youtube/v3/channels?part=brandingSettings"
    branding_payload = json.dumps({
        "id": MAIN_CHANNEL_ID,
        "brandingSettings": channel_data["brandingSettings"],
    }).encode("utf-8")

    branding_req = Request(
        branding_url,
        data=branding_payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )

    try:
        with urlopen(branding_req) as resp:
            json.loads(resp.read().decode("utf-8"))
            print("  Branding settings updated.")
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Branding error {e.code}: {err[:300]}")

    # Update snippet (description, language, country)
    snippet_url = "https://www.googleapis.com/youtube/v3/channels?part=snippet"
    snippet_payload = json.dumps({
        "id": MAIN_CHANNEL_ID,
        "snippet": {
            "title": channel_data["snippet"]["title"],
            "description": NEW_DESCRIPTION,
            "defaultLanguage": "en",
            "country": "US",
        },
    }).encode("utf-8")

    snippet_req = Request(
        snippet_url,
        data=snippet_payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )

    try:
        with urlopen(snippet_req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"  Snippet error {e.code}: {err[:500]}")
        return None


def main():
    print("Updating Cumquat Vibes Channel Description")
    print("=" * 50)

    access_token = refresh_token()
    print("Token refreshed.")

    print("\nFetching current channel info...")
    channel = get_channel_info(access_token)
    print(f"Current title: {channel['snippet']['title']}")
    print(f"Current description: {channel['snippet'].get('description', '(empty)')[:100]}...")

    print(f"\nNew description:")
    print(NEW_DESCRIPTION[:200] + "...")

    print("\nUpdating channel...")
    result = update_channel(access_token, channel)

    if result:
        print("\nChannel updated successfully!")
        print(f"Title: {result['snippet']['title']}")
        print(f"Description starts: {result['snippet']['description'][:100]}...")
    else:
        print("\nUpdate failed!")


if __name__ == "__main__":
    main()
