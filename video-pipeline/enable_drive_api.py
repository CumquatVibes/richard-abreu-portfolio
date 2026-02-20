#!/usr/bin/env python3
"""Enable Google Drive API by re-authorizing with cloud-platform scope."""

import json
import http.server
import urllib.request
import urllib.parse
import urllib.error
import webbrowser
import threading

# Use the same OAuth client but request cloud-platform scope
with open("google_token.json") as f:
    creds = json.load(f)

CLIENT_ID = creds["client_id"]
CLIENT_SECRET = creds["client_secret"]
REDIRECT_PORT = 8091
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
SCOPES = " ".join([
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
])

auth_code = None


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authorized! You can close this tab.</h1>")

    def log_message(self, *args):
        pass


# Build auth URL
auth_url = (
    "https://accounts.google.com/o/oauth2/auth?"
    + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
)

print("Opening browser for authorization...")
print(f"If browser doesn't open, visit:\n{auth_url}\n")
webbrowser.open(auth_url)

# Wait for callback
server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
server.handle_request()

if not auth_code:
    print("ERROR: No auth code received")
    exit(1)

print("Auth code received! Exchanging for token...")

# Exchange code for token
token_data = urllib.parse.urlencode({
    "code": auth_code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}).encode()

req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_data)
resp = json.loads(urllib.request.urlopen(req).read())
access_token = resp["access_token"]
print("Token obtained with cloud-platform scope!")

# Update google_token.json with new token + refresh token
creds["token"] = access_token
if "refresh_token" in resp:
    creds["refresh_token"] = resp["refresh_token"]
creds["scopes"] = SCOPES.split()
with open("google_token.json", "w") as f:
    json.dump(creds, f, indent=2)
print("Saved updated token to google_token.json")

# Now enable Drive API
print("\nEnabling Google Drive API...")
enable_url = "https://serviceusage.googleapis.com/v1/projects/24631452174/services/drive.googleapis.com:enable"
req2 = urllib.request.Request(enable_url, data=b"{}", headers={
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}, method="POST")

try:
    resp2 = urllib.request.urlopen(req2)
    result = json.loads(resp2.read())
    print("Drive API enabled successfully!")
    print(json.dumps(result, indent=2))
except urllib.error.HTTPError as e:
    error = e.read().decode()
    print(f"Error {e.code}: {error[:500]}")

# Test Drive API
print("\nTesting Drive API access...")
test_url = "https://www.googleapis.com/drive/v3/about?fields=user"
req3 = urllib.request.Request(test_url, headers={
    "Authorization": f"Bearer {access_token}",
})
try:
    resp3 = urllib.request.urlopen(req3)
    user = json.loads(resp3.read())
    print(f"Drive API working! Logged in as: {user['user']['displayName']} ({user['user']['emailAddress']})")
except urllib.error.HTTPError as e:
    error = e.read().decode()
    print(f"Drive test error {e.code}: {error[:300]}")
