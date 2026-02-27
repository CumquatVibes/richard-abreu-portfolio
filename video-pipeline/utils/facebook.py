"""Post YouTube videos to the CumquatVibes Facebook group."""

import json
import os

import requests

from utils.telemetry import log_facebook_post

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "channels_config.json")


def _load_caption_template():
    """Load the youtube_to_facebook_group caption template from channels_config.json."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    rules = config.get("content_repurposing_rules", {})
    entry = rules.get("youtube_to_facebook_group", {})
    return entry.get(
        "caption_template",
        "{hook_line}\n\nWatch: {youtube_link}\n\nDrop your thoughts below!",
    )


def post_to_facebook_group(video_title, video_url, channel, is_short=False):
    """Post a YouTube video link to the Facebook group.

    Never raises — logs and returns on failure so the upload pipeline isn't blocked.
    Returns (success: bool, post_id_or_error: str).
    """
    token = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    group_id = os.getenv("FACEBOOK_GROUP_ID", "")

    if not token or len(token) < 40:
        print("  SKIP facebook: FACEBOOK_ACCESS_TOKEN missing or invalid")
        return False, "missing_token"
    if not group_id:
        print("  SKIP facebook: FACEBOOK_GROUP_ID not set")
        return False, "missing_group_id"

    template = _load_caption_template()
    video_type = "Short" if is_short else "video"
    message = template.format(
        hook_line=f"New {video_type} from {channel}: {video_title}",
        discussion_question=f"What do you think about this one?",
        youtube_link=video_url,
    )

    try:
        resp = requests.post(
            f"https://graph.facebook.com/v19.0/{group_id}/feed",
            data={"message": message, "link": video_url, "access_token": token},
            timeout=30,
        )
        data = resp.json()

        if "id" in data:
            post_id = data["id"]
            print(f"  Facebook group post: {post_id}")
            log_facebook_post(video_title, post_id)
            return True, post_id
        else:
            error = data.get("error", {}).get("message", str(data))
            print(f"  WARNING: Facebook post failed: {error[:120]}")
            return False, error
    except Exception as e:
        print(f"  WARNING: Facebook post error: {str(e)[:120]}")
        return False, str(e)
