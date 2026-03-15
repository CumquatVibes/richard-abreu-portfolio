"""Post YouTube videos to channel-specific Facebook pages and the shared group."""

import json
import os

import requests

from utils.telemetry import log_facebook_post

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "channels_config.json")
FB_TOKENS_PATH = os.path.join(BASE_DIR, "facebook_page_tokens.json")

# Load env vars from both .env files (tokens may be split across them)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv(os.path.join(os.path.dirname(BASE_DIR), "shopify-theme", ".env"))
except ImportError:
    pass


def _load_channel_page_tokens():
    """Load per-channel Facebook page tokens from facebook_page_tokens.json."""
    if os.path.exists(FB_TOKENS_PATH):
        try:
            with open(FB_TOKENS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _get_page_token_for_channel(channel):
    """Get the Facebook page ID and access token for a specific channel.
    Falls back to the default FACEBOOK_PAGE_* env vars if no channel-specific token exists.
    """
    tokens = _load_channel_page_tokens()
    if channel in tokens:
        entry = tokens[channel]
        return entry.get("page_id", ""), entry.get("access_token", "")
    # Fallback to default page from env
    return os.getenv("FACEBOOK_PAGE_ID", ""), os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")


def _load_caption_template(key):
    """Load a caption template from channels_config.json content_repurposing_rules."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    rules = config.get("content_repurposing_rules", {})
    entry = rules.get(key, {})
    return entry.get("caption_template", "{hook_line}\n\nWatch: {youtube_link}")


def _post_to_facebook(endpoint_url, message, video_url, token, label):
    """Low-level Graph API post. Returns (success, post_id_or_error)."""
    try:
        resp = requests.post(
            endpoint_url,
            data={"message": message, "link": video_url, "access_token": token},
            timeout=30,
        )
        data = resp.json()

        if "id" in data:
            post_id = data["id"]
            print(f"  Facebook {label} post: {post_id}")
            return True, post_id
        else:
            error = data.get("error", {}).get("message", str(data))
            print(f"  WARNING: Facebook {label} post failed: {error[:120]}")
            return False, error
    except Exception as e:
        print(f"  WARNING: Facebook {label} error: {str(e)[:120]}")
        return False, str(e)


def post_to_facebook_group(video_title, video_url, channel, is_short=False):
    """Post a YouTube video link to the Facebook group.

    Never raises — logs and returns on failure so the upload pipeline isn't blocked.
    Returns (success, post_id_or_error).
    """
    token = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    group_id = os.getenv("FACEBOOK_GROUP_ID", "")

    if not token or len(token) < 40:
        print("  SKIP facebook group: FACEBOOK_ACCESS_TOKEN missing or invalid")
        return False, "missing_token"
    if not group_id:
        print("  SKIP facebook group: FACEBOOK_GROUP_ID not set")
        return False, "missing_group_id"

    template = _load_caption_template("youtube_to_facebook_group")
    video_type = "Short" if is_short else "video"
    message = template.format(
        hook_line=f"New {video_type} from {channel}: {video_title}",
        discussion_question="What do you think about this one?",
        youtube_link=video_url,
    )

    url = f"https://graph.facebook.com/v24.0/{group_id}/feed"
    ok, result = _post_to_facebook(url, message, video_url, token, "group")
    if ok:
        log_facebook_post(video_title, result, target="group")
    return ok, result


def post_to_facebook_page(video_title, video_url, channel, is_short=False):
    """Post a YouTube video link to the channel's Facebook page.

    Routes to the channel-specific Facebook page if configured in
    facebook_page_tokens.json, otherwise falls back to the default page.

    Never raises — logs and returns on failure so the upload pipeline isn't blocked.
    Returns (success, post_id_or_error).
    """
    page_id, token = _get_page_token_for_channel(channel)

    if not token or len(token) < 40:
        print(f"  SKIP facebook page: no token for {channel}")
        return False, "missing_token"
    if not page_id:
        print(f"  SKIP facebook page: no page_id for {channel}")
        return False, "missing_page_id"

    template = _load_caption_template("youtube_to_facebook_page")
    video_type = "Short" if is_short else "video"
    message = template.format(
        hook_line=f"New {video_type} from {channel}: {video_title}",
        youtube_link=video_url,
        hashtags=f"#{channel.replace(' ', '')}",
    )

    url = f"https://graph.facebook.com/v24.0/{page_id}/feed"
    ok, result = _post_to_facebook(url, message, video_url, token, f"page:{channel}")
    if ok:
        log_facebook_post(video_title, result, target=f"page:{channel}")
    return ok, result


def share_to_facebook(video_title, video_url, channel, is_short=False):
    """Post to both the Facebook page and group. Never raises."""
    page_result = post_to_facebook_page(video_title, video_url, channel, is_short)
    group_result = post_to_facebook_group(video_title, video_url, channel, is_short)
    return page_result, group_result


def check_token_expiry(warn_days=14):
    """Check Facebook token expiry dates. Returns dict with status info.

    Queries the Graph API debug_token endpoint to get expiry timestamps.
    Prints warnings if tokens expire within warn_days.
    """
    import time

    results = {}
    tokens = {
        "page": os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
        "user": os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
    }
    app_token = os.getenv("FACEBOOK_APP_TOKEN", "")

    for label, token in tokens.items():
        if not token or len(token) < 40:
            results[label] = {"status": "missing"}
            continue

        try:
            # Use the token itself to debug (works for long-lived tokens)
            resp = requests.get(
                "https://graph.facebook.com/v24.0/debug_token",
                params={"input_token": token, "access_token": token},
                timeout=10,
            )
            data = resp.json().get("data", {})
            expires_at = data.get("expires_at", 0)
            is_valid = data.get("is_valid", False)

            if expires_at == 0:
                results[label] = {"status": "never_expires" if is_valid else "invalid"}
            else:
                days_left = (expires_at - time.time()) / 86400
                results[label] = {
                    "status": "valid" if is_valid else "invalid",
                    "expires_at": expires_at,
                    "days_left": round(days_left, 1),
                }
                if is_valid and days_left < warn_days:
                    print(
                        "  WARNING: Facebook %s token expires in %.0f days! "
                        "Regenerate at https://developers.facebook.com/tools/explorer/"
                        % (label, days_left)
                    )
                elif is_valid:
                    print("  Facebook %s token: valid, %.0f days remaining" % (label, days_left))
        except Exception as e:
            results[label] = {"status": "error", "error": str(e)[:100]}

    return results
