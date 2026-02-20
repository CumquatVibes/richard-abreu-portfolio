#!/usr/bin/env python3
"""Set up separate OAuth tokens for each YouTube brand channel.

For each channel, opens a browser where you select the correct brand account.
Saves per-channel refresh tokens to channel_tokens.json.

Auto-proceeds through all channels — just complete each OAuth flow in the browser.

Usage:
    python3 setup_channel_auth.py                   # authorize all channels
    python3 setup_channel_auth.py RichTech           # authorize just one channel
    python3 setup_channel_auth.py --reauth           # re-authorize all channels
"""

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")

# All 38 faceless channels: display_name -> expected channel_id
CHANNELS = {
    "Cumquat Motivation": "UCtrCefKinhom7LFBV8rnfpQ",
    "RichTech": "UCH7Om9fi1IA3SrRXmx2vApQ",
    "RichAnimation": "UCtsmXjQaCdMTEyDTDWRpVVA",
    "RichFashion": "UCf0Y1kCz_2nTmKpJtPQKoyg",
    "RichFamily": "UC3rXZPP828z8w9UdEdQEWtw",
    "RichBeauty": "UCfBoNA8eUrqmSTPLtMhrpdQ",
    "RichCooking": "UC8OrR3UMdyzy4DRgmCWOXcA",
    "RichEducation": "UCp3WkXsFFzdRLZX_UYp43cw",
    "RichHistory": "UC1pCR2B_mQwCacIlvRhUacA",
    "RichNature": "UCqzGBwIvr3sY1nUc9M2EVsg",
    "RichCrypto": "UCc5XhfHIkEp5WwG9CRZm_6w",
    "RichScience": "UC0ODvK8Hvrd9Bd3QWIWPecA",
    "RichTravel": "UCEA1FMT0W2lS93Ig1W1ddUA",
    "RichVlogging": "UCfcF72fTPY1khgl5bEHzZEQ",
    "RichGaming": "UCxa7nahEFd_39_jUl-VB57A",
    "RichReviews": "UCQZAmWq2Y_1W09mIOSRSrFw",
    "RichKids": "UCTR_qaU4bdip3DSvgBkRMGA",
    "RichPets": "UCqPWKbwAGtKfiay4fB8bF1g",
    "RichHorror": "UCoWN7G6XuFBPgM-m3d1ZMvQ",
    "RichMovie": "UCuQwKYGe1hNdbQqJH51qqAw",
    "Rich Business": "UCPQ8N53EgcqEKR4SfQ1DcXQ",
    "RichFitness": "UCYelLGcByI-Qh94two6CaMA",
    "RichMusic": "UCCI_ynXNuutXGrzWDYzUZiA",
    "RichFinance": "UCJwfAudM4c4rWSk3P8iib8g",
    "RichCars": "UCr0q31TN0vW0c65JUD0eaBw",
    "RichLifestyle": "UC1Qnne6cR4N4RJgpySYUevw",
    "RichPhotography": "UCZLGO4ioG50Y3FBK3oLKmpA",
    "RichSports": "UCE33LOzIvklXaPbH1920vqQ",
    "RichFood": "UCSRXBfCZTafYTtfH9KF-SZw",
    "RichMemes": "UC5Sa2tKSk-5Nek01b-v1LpQ",
    "RichDesign": "UCSc0w6tez-UI3fyXQbUcF5g",
    "RichComedy": "UC7OZtJLgHJ1ooWWlPLRYIXg",
    "RichDIY": "UC7dfL3CGJCbG7QcGnjrmqbQ",
    "RichDance": "UCsNqeu5ZPnBOE3liu9-ofYg",
    "Eva Reyes": "UCsp5NIA6aeQmqdn7omBqkYg",
    "RichMind": "UCvrGunMx9dVfAeGYLQYoaLw",
    "How to Meditate": "UCbd6kzX3giNYyAeLaMPdgAA",
    "How to Use AI": "UCkrCbfr9qQkfCYw1WkCILKQ",
}

SCOPES = "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.upload"
REDIRECT_PORT = 8099
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

auth_code = None
server_done = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback on localhost."""

    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                b"<h1>Authorized!</h1><p>You can close this tab.</p>"
                b"</body></html>"
            )
        else:
            auth_code = None
            error = params.get("error", ["unknown"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                f"<h1>Error: {error}</h1></body></html>".encode()
            )

        server_done.set()

    def log_message(self, format, *args):
        pass


def get_auth_code(client_id):
    """Open browser for OAuth and capture the authorization code."""
    global auth_code
    auth_code = None
    server_done.clear()

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        "&response_type=code"
        "&access_type=offline"
        "&prompt=consent"
    )

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print("  Opening browser...")
    webbrowser.open(auth_url)

    print("  Waiting for authorization (180s timeout)...")
    server_done.wait(timeout=180)
    server.server_close()
    server_thread.join(timeout=5)

    return auth_code


def exchange_code(code, client_id, client_secret):
    """Exchange authorization code for access + refresh tokens."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    return json.loads(urlopen(req).read())


def verify_channel(access_token):
    """Check which YouTube channel this token authenticates as."""
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        result = json.loads(urlopen(req).read())
    except HTTPError as e:
        print(f"  Verify error: {e.code}")
        return None, None
    items = result.get("items", [])
    if items:
        return items[0]["id"], items[0]["snippet"]["title"]
    return None, None


def main():
    print("YouTube Brand Channel OAuth Setup")
    print("=" * 60)
    print()
    print(f"Channels to authorize: {len(CHANNELS)}")
    print()
    print("A browser window will open for EACH channel.")
    print("When Google shows 'Choose your YouTube channel',")
    print("select the matching brand account, then the next")
    print("channel will start automatically.")
    print()

    with open(TOKEN_PATH) as f:
        creds = json.load(f)
    client_id = creds["client_id"]
    client_secret = creds["client_secret"]

    # Load existing tokens
    channel_tokens = {}
    if os.path.exists(CHANNEL_TOKENS_PATH):
        with open(CHANNEL_TOKENS_PATH) as f:
            channel_tokens = json.load(f)

    # Parse args
    reauth = "--reauth" in sys.argv
    only_channel = None
    for arg in sys.argv[1:]:
        if arg != "--reauth" and arg in CHANNELS:
            only_channel = arg

    channels_to_auth = {only_channel: CHANNELS[only_channel]} if only_channel else CHANNELS

    authorized = 0
    skipped = 0
    failed = 0

    for i, (channel_name, expected_id) in enumerate(channels_to_auth.items(), 1):
        if channel_name in channel_tokens and not reauth:
            existing = channel_tokens[channel_name]
            print(f"[{i}/{len(channels_to_auth)}] {channel_name}: SKIP (already authorized as '{existing.get('channel_title', '?')}')")
            authorized += 1
            continue

        print(f"\n[{i}/{len(channels_to_auth)}] Authorizing: {channel_name}")
        print(f"  Expected channel ID: {expected_id}")

        # Brief pause so user can see what's happening
        time.sleep(2)

        code = get_auth_code(client_id)
        if not code:
            print(f"  FAILED: No authorization code received.")
            failed += 1
            continue

        print("  Exchanging code for tokens...")
        try:
            tokens = exchange_code(code, client_id, client_secret)
        except HTTPError as e:
            print(f"  FAILED: Token exchange error {e.code}")
            failed += 1
            continue

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")

        if not access_token or not refresh_token:
            print(f"  FAILED: Missing tokens in response")
            failed += 1
            continue

        ch_id, ch_title = verify_channel(access_token)
        print(f"  Authenticated as: {ch_title} ({ch_id})")

        if ch_id != expected_id:
            print(f"  NOTE: Expected {expected_id} but got {ch_id}")
            print(f"  Saving anyway — you can re-auth later with --reauth")

        channel_tokens[channel_name] = {
            "channel_id": ch_id,
            "channel_title": ch_title,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        with open(CHANNEL_TOKENS_PATH, "w") as f:
            json.dump(channel_tokens, f, indent=2)

        print(f"  Saved!")
        authorized += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {authorized} authorized, {failed} failed, {skipped} skipped")
    print(f"Tokens file: {CHANNEL_TOKENS_PATH}")

    if authorized == len(CHANNELS):
        print("\nAll channels authorized! Run:")
        print("  python3 upload_to_youtube.py")


if __name__ == "__main__":
    main()
