"""Post YouTube videos to the CumquatVibes Facebook page and group."""

import json
import os

import requests

from utils.telemetry import log_facebook_post

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "channels_config.json")


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

    url = f"https://graph.facebook.com/v19.0/{group_id}/feed"
    ok, result = _post_to_facebook(url, message, video_url, token, "group")
    if ok:
        log_facebook_post(video_title, result, target="group")
    return ok, result


def post_to_facebook_page(video_title, video_url, channel, is_short=False):
    """Post a YouTube video link to the Facebook page.

    Never raises — logs and returns on failure so the upload pipeline isn't blocked.
    Returns (success, post_id_or_error).
    """
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    page_id = os.getenv("FACEBOOK_PAGE_ID", "")

    if not token or len(token) < 40:
        print("  SKIP facebook page: FACEBOOK_PAGE_ACCESS_TOKEN missing or invalid")
        return False, "missing_token"
    if not page_id:
        print("  SKIP facebook page: FACEBOOK_PAGE_ID not set")
        return False, "missing_page_id"

    template = _load_caption_template("youtube_to_facebook_page")
    video_type = "Short" if is_short else "video"
    message = template.format(
        hook_line=f"New {video_type} from {channel}: {video_title}",
        youtube_link=video_url,
        hashtags=f"#CumquatVibes #{channel.replace(' ', '')}",
    )

    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    ok, result = _post_to_facebook(url, message, video_url, token, "page")
    if ok:
        log_facebook_post(video_title, result, target="page")
    return ok, result


def share_to_facebook(video_title, video_url, channel, is_short=False):
    """Post to both the Facebook page and group. Never raises."""
    page_result = post_to_facebook_page(video_title, video_url, channel, is_short)
    group_result = post_to_facebook_group(video_title, video_url, channel, is_short)
    return page_result, group_result
