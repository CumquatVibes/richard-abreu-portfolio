#!/usr/bin/env python3
"""Exchange a short-lived Facebook token for long-lived tokens.

Usage:
    1. Go to https://developers.facebook.com/tools/explorer/
    2. Select your app (1982719755918948)
    3. Add permissions: pages_manage_posts, pages_read_engagement, publish_to_groups
    4. Generate User Access Token and copy it
    5. Run: python3 setup_facebook_tokens.py YOUR_SHORT_LIVED_TOKEN

This will:
    - Exchange for a long-lived user token (60 days)
    - List your Pages and Groups with their IDs
    - Generate a permanent Page Access Token
    - Print the env vars to add to .env
"""

import json
import os
import sys

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, "..", "shopify-theme", ".env")

# Load from .env or environment
from dotenv import load_dotenv
load_dotenv(ENV_PATH)

APP_ID = os.getenv("FACEBOOK_APP_ID", "")
APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")


def exchange_for_long_lived(short_token):
    """Exchange short-lived token for long-lived user token (60 days)."""
    print("\n[1/4] Exchanging for long-lived user token...")
    resp = requests.get(
        "https://graph.facebook.com/v24.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "fb_exchange_token": short_token,
        },
        timeout=15,
    )
    data = resp.json()
    if "access_token" in data:
        token = data["access_token"]
        expires = data.get("expires_in", "unknown")
        print(f"  Long-lived token obtained (expires in {expires}s / ~60 days)")
        return token
    else:
        error = data.get("error", {}).get("message", str(data))
        print(f"  ERROR: {error}")
        sys.exit(1)


def get_pages(user_token):
    """List Pages the user manages and get permanent Page tokens."""
    print("\n[2/4] Fetching your Pages...")
    resp = requests.get(
        "https://graph.facebook.com/v24.0/me/accounts",
        params={"access_token": user_token},
        timeout=15,
    )
    data = resp.json()
    pages = data.get("data", [])
    if not pages:
        print("  No Pages found. Make sure you have admin access to a Page.")
        return []

    for i, page in enumerate(pages, 1):
        print(f"  [{i}] {page['name']} (ID: {page['id']})")
        print(f"      Page Token: {page['access_token'][:20]}...")
    return pages


def get_groups(user_token):
    """List Groups the user is admin of."""
    print("\n[3/4] Fetching your Groups...")
    resp = requests.get(
        "https://graph.facebook.com/v24.0/me/groups",
        params={"access_token": user_token, "admin_only": "true"},
        timeout=15,
    )
    data = resp.json()
    groups = data.get("data", [])
    if not groups:
        print("  No admin Groups found.")
        return []

    for i, group in enumerate(groups, 1):
        print(f"  [{i}] {group['name']} (ID: {group['id']})")
    return groups


def select_item(items, label):
    """Prompt user to select from a list."""
    if len(items) == 1:
        print(f"  Auto-selected: {items[0].get('name', items[0].get('id'))}")
        return items[0]
    while True:
        try:
            choice = int(input(f"\nSelect {label} (1-{len(items)}): "))
            if 1 <= choice <= len(items):
                return items[choice - 1]
        except (ValueError, EOFError):
            pass
        print(f"  Enter a number 1-{len(items)}")


def main():
    if not APP_ID or not APP_SECRET:
        print("[ERROR] FACEBOOK_APP_ID and FACEBOOK_APP_SECRET must be set in .env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python3 setup_facebook_tokens.py YOUR_SHORT_LIVED_TOKEN")
        print("\nGet your token from: https://developers.facebook.com/tools/explorer/")
        print(f"App ID: {APP_ID}")
        print("Required permissions: pages_manage_posts, pages_read_engagement, publish_to_groups")
        sys.exit(1)

    short_token = sys.argv[1]

    # Step 1: Exchange for long-lived token
    long_token = exchange_for_long_lived(short_token)

    # Step 2: Get Pages
    pages = get_pages(long_token)

    # Step 3: Get Groups
    groups = get_groups(long_token)

    # Step 4: Print env vars
    print("\n[4/4] Environment variables to add to .env:")
    print("=" * 60)

    print(f"\nFACEBOOK_ACCESS_TOKEN={long_token}")

    if pages:
        page = select_item(pages, "Page")
        print(f"FACEBOOK_PAGE_ID={page['id']}")
        print(f"FACEBOOK_PAGE_ACCESS_TOKEN={page['access_token']}")

    if groups:
        group = select_item(groups, "Group")
        print(f"FACEBOOK_GROUP_ID={group['id']}")

    print("\n" + "=" * 60)

    # Offer to write to .env
    try:
        answer = input("\nWrite these to .env now? (y/n): ").strip().lower()
    except EOFError:
        answer = "n"

    if answer == "y":
        with open(ENV_PATH, "a") as f:
            f.write(f"\n# Facebook Access Tokens (generated {__import__('datetime').datetime.now().strftime('%Y-%m-%d')})\n")
            f.write(f"FACEBOOK_ACCESS_TOKEN={long_token}\n")
            if pages:
                f.write(f"FACEBOOK_PAGE_ID={page['id']}\n")
                f.write(f"FACEBOOK_PAGE_ACCESS_TOKEN={page['access_token']}\n")
            if groups:
                f.write(f"FACEBOOK_GROUP_ID={group['id']}\n")
        print(f"\nWritten to {ENV_PATH}")
    else:
        print("\nCopy the values above and add them to .env manually.")


if __name__ == "__main__":
    main()
