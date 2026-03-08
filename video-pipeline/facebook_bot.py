#!/usr/bin/env python3
"""Facebook Page automation bot for Cumquat Vibes.

Subcommands:
    --comments      Auto-reply to comments via Gemini
    --engage        Auto-like comments
    --spam          Delete spam comments
    --monitor       Log engagement metrics
    --crosspost     Post YouTube videos to page
    --all           Run everything
    --dry-run       Preview without writing
    --limit N       How many posts to scan (default 25)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

from utils.telemetry import (
    log_comment_action,
    log_decision,
    log_fb_engagement,
    log_incident,
    was_comment_acted_on,
    was_posted_to_facebook,
    get_fb_crosspost_count,
    record_fb_crosspost,
)
from utils.facebook import post_to_facebook_page

# ── Run stats (accumulated across subcommands for learning) ──
_run_stats = {
    "comments_replied": 0,
    "comments_liked": 0,
    "spam_deleted": 0,
    "spam_scanned": 0,
    "posts_monitored": 0,
    "videos_crossposted": 0,
    "api_errors": 0,
    "gemini_failures": 0,
}

# ── Config ──

PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GRAPH_API = "https://graph.facebook.com/v24.0"
MAX_CROSSPOSTS_PER_DAY = 5
UPLOAD_REPORT = os.path.join(BASE_DIR, "output", "reports", "youtube_upload_report.json")

# Spam detection
SPAM_PHRASES = [
    "check my profile", "check my page", "visit my channel",
    "earn $", "make $", "per day", "per week",
    "sub4sub", "sub 4 sub", "follow me",
    "free bitcoin", "free crypto", "crypto giveaway",
    "whatsapp me", "telegram me", "dm me for",
    "click here", "click the link",
    "i]nvest", "tr@ding", "bin@nce",
]
URL_WHITELIST = ["youtube.com", "youtu.be", "cumquatvibes.com", "facebook.com",
                 "richardabreu.studio", "instagram.com"]


# ── Gemini ──

def gemini_call(prompt, model="gemini-2.0-flash", retries=3, temperature=0.7,
                max_tokens=256):
    """Call Gemini API with retries and exponential backoff."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
           f":generateContent?key={GEMINI_API_KEY}")
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }).encode()

    for attempt in range(retries):
        try:
            req = Request(url, data=payload,
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except HTTPError as e:
            if e.code == 429:
                wait = 15 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                err = e.read().decode() if hasattr(e, "read") else str(e)
                print(f"    Gemini API error {e.code}: {err[:200]}")
                if attempt == retries - 1:
                    _run_stats["gemini_failures"] += 1
                    log_incident(None, "fb_bot_gemini_error", "medium",
                                 f"Gemini {e.code} after {retries} retries: {err[:150]}")
                    return None
                time.sleep(5)
        except Exception as e:
            print(f"    Gemini error: {str(e)[:200]}")
            if attempt == retries - 1:
                _run_stats["gemini_failures"] += 1
                log_incident(None, "fb_bot_gemini_error", "medium",
                             f"Gemini exception after {retries} retries: {str(e)[:150]}")
                return None
            time.sleep(5)
    return None


# ── Graph API helpers ──

def _safe_api_call(method, endpoint, data=None, label="api_call"):
    """Never-raise Graph API wrapper. Returns (ok, json_or_error)."""
    url = f"{GRAPH_API}/{endpoint}"
    if method == "GET":
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}access_token={PAGE_TOKEN}"
    try:
        if method == "GET":
            req = Request(url)
        elif method == "POST":
            post_data = data or {}
            post_data["access_token"] = PAGE_TOKEN
            encoded = json.dumps(post_data).encode()
            req = Request(url, data=encoded,
                          headers={"Content-Type": "application/json"},
                          method="POST")
        elif method == "DELETE":
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}access_token={PAGE_TOKEN}"
            req = Request(url, method="DELETE")
        else:
            return False, f"unsupported method: {method}"

        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return True, result
    except HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        try:
            err_json = json.loads(body)
            msg = err_json.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200]
        print(f"  [{label}] HTTP {e.code}: {msg}")
        _run_stats["api_errors"] += 1
        log_incident(None, "fb_bot_api_error", "low",
                     f"Graph API {label} HTTP {e.code}: {msg[:150]}")
        return False, msg
    except Exception as e:
        print(f"  [{label}] Error: {str(e)[:200]}")
        _run_stats["api_errors"] += 1
        log_incident(None, "fb_bot_api_error", "low",
                     f"Graph API {label} exception: {str(e)[:150]}")
        return False, str(e)


def _fetch_page_posts(limit=25):
    """Fetch recent posts from the page."""
    ok, data = _safe_api_call(
        "GET",
        f"{PAGE_ID}/posts?fields=id,message,created_time&limit={limit}",
        label="fetch_posts",
    )
    if ok and "data" in data:
        return data["data"]
    return []


def _fetch_comments(post_id):
    """Fetch comments for a post."""
    ok, data = _safe_api_call(
        "GET",
        f"{post_id}/comments?fields=id,from,message,created_time&limit=100",
        label="fetch_comments",
    )
    if ok and "data" in data:
        return data["data"]
    return []


# ── Spam scoring ──

def _spam_score(text):
    """Score a comment for spam. Returns (score, reasons)."""
    if not text:
        return 0, []
    score = 0
    reasons = []
    lower = text.lower()

    # Check for unknown URLs
    urls = re.findall(r'https?://[^\s]+', text)
    for url in urls:
        if not any(domain in url.lower() for domain in URL_WHITELIST):
            score += 4
            reasons.append(f"unknown URL: {url[:60]}")

    # Excessive caps (>70% of alpha chars)
    alpha = [c for c in text if c.isalpha()]
    if len(alpha) > 5 and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.7:
        score += 2
        reasons.append("excessive caps")

    # Spam phrases
    for phrase in SPAM_PHRASES:
        if phrase in lower:
            score += 3
            reasons.append(f"spam phrase: '{phrase}'")

    # Gibberish: 30+ chars but ≤2 words
    if len(text) > 30 and len(text.split()) <= 2:
        score += 3
        reasons.append("gibberish (long, few words)")

    # Repetitive chars (10+)
    if re.search(r'(.)\1{9,}', text):
        score += 2
        reasons.append("repetitive chars")

    # Phone numbers
    if re.search(r'[\+]?\d[\d\s\-]{8,}\d', text):
        score += 2
        reasons.append("phone number")

    return score, reasons


# ── Subcommands ──

def cmd_comments(posts, dry_run=False):
    """Auto-reply to comments via Gemini."""
    if not GEMINI_API_KEY:
        print("SKIP --comments: GEMINI_API_KEY not set")
        return
    replied = 0
    for post in posts:
        post_id = post["id"]
        comments = _fetch_comments(post_id)
        for c in comments:
            cid = c["id"]
            from_info = c.get("from", {})
            from_id = from_info.get("id", "")
            from_name = from_info.get("name", "Unknown")
            text = c.get("message", "")

            # Skip own comments
            if from_id == PAGE_ID:
                continue
            # Skip already replied
            if was_comment_acted_on(cid, action="replied"):
                continue

            post_text = post.get("message", "")[:200]
            prompt = (
                f"You are the social media manager for Cumquat Vibes, a creative "
                f"brand. Someone commented on your Facebook post.\n\n"
                f"Post: {post_text}\n"
                f"Comment by {from_name}: {text}\n\n"
                f"Write a short, friendly reply (1-2 sentences). Be warm and "
                f"conversational. Don't use hashtags. Don't be overly formal."
            )

            if dry_run:
                print(f"  [DRY-RUN] Would reply to {from_name}: '{text[:60]}...'")
                replied += 1
                continue

            reply = gemini_call(prompt)
            if not reply:
                print(f"  Gemini failed for comment {cid}, skipping")
                continue

            reply = reply.strip().strip('"')
            ok, _ = _safe_api_call(
                "POST", f"{cid}/comments",
                data={"message": reply},
                label="reply_comment",
            )
            if ok:
                log_comment_action(cid, post_id, "replied",
                                   commenter_name=from_name,
                                   comment_text=text, reply_text=reply)
                log_decision(
                    video_name=None,
                    decision_type="fb_bot_auto_reply",
                    objective="community_engagement",
                    chosen_action=f"Replied to {from_name}: {reply[:80]}",
                    expected_impact="increase_comment_engagement",
                    risk_rating="low",
                )
                print(f"  Replied to {from_name}: {reply[:80]}")
                replied += 1
                _run_stats["comments_replied"] += 1
            time.sleep(2)
    print(f"  Comments: {replied} replies {'(dry-run)' if dry_run else 'sent'}")


def cmd_engage(posts, dry_run=False):
    """Auto-like comments."""
    liked = 0
    for post in posts:
        post_id = post["id"]
        comments = _fetch_comments(post_id)
        for c in comments:
            cid = c["id"]
            from_id = c.get("from", {}).get("id", "")
            from_name = c.get("from", {}).get("name", "Unknown")

            if from_id == PAGE_ID:
                continue
            if was_comment_acted_on(cid, action="liked"):
                continue

            if dry_run:
                print(f"  [DRY-RUN] Would like comment by {from_name}")
                liked += 1
                continue

            ok, _ = _safe_api_call("POST", f"{cid}/likes", label="like_comment")
            if ok:
                log_comment_action(cid, post_id, "liked",
                                   commenter_name=from_name,
                                   comment_text=c.get("message", ""))
                liked += 1
                _run_stats["comments_liked"] += 1
            time.sleep(1)
    print(f"  Engage: {liked} likes {'(dry-run)' if dry_run else 'sent'}")


def cmd_spam(posts, dry_run=False):
    """Detect and delete spam comments."""
    deleted = 0
    for post in posts:
        post_id = post["id"]
        comments = _fetch_comments(post_id)
        for c in comments:
            cid = c["id"]
            from_id = c.get("from", {}).get("id", "")
            from_name = c.get("from", {}).get("name", "Unknown")
            text = c.get("message", "")

            if from_id == PAGE_ID:
                continue
            if was_comment_acted_on(cid, action="deleted_spam"):
                continue

            _run_stats["spam_scanned"] += 1
            score, reasons = _spam_score(text)
            if score < 5:
                continue

            if dry_run:
                print(f"  [DRY-RUN] SPAM ({score}pts) {from_name}: "
                      f"'{text[:50]}' — {', '.join(reasons)}")
                deleted += 1
                continue

            ok, _ = _safe_api_call("DELETE", cid, label="delete_spam")
            if ok:
                log_comment_action(cid, post_id, "deleted_spam",
                                   commenter_name=from_name,
                                   comment_text=text)
                log_incident(
                    video_name=None,
                    incident_type="facebook_spam_deleted",
                    severity="low",
                    description=(f"Deleted spam from {from_name} (score={score}): "
                                 f"{text[:100]}. Reasons: {', '.join(reasons)}"),
                )
                log_decision(
                    video_name=None,
                    decision_type="fb_bot_spam_delete",
                    objective="page_quality",
                    chosen_action=f"Deleted comment from {from_name} (score={score})",
                    alternatives=json.dumps(reasons),
                    expected_impact="reduce_spam_visibility",
                    risk_rating="low",
                )
                print(f"  Deleted spam from {from_name} ({score}pts): "
                      f"{', '.join(reasons)}")
                deleted += 1
                _run_stats["spam_deleted"] += 1
            time.sleep(1)
    print(f"  Spam: {deleted} deleted {'(dry-run)' if dry_run else ''}")


def cmd_monitor(posts, dry_run=False):
    """Fetch engagement metrics and log snapshots."""
    total_likes = 0
    total_comments = 0
    total_shares = 0
    rows = []

    for post in posts:
        post_id = post["id"]
        ok, data = _safe_api_call(
            "GET",
            f"{post_id}?fields=likes.summary(true),comments.summary(true),shares",
            label="fetch_engagement",
        )
        if not ok:
            continue

        likes = data.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0)

        total_likes += likes
        total_comments += comments
        total_shares += shares

        msg = post.get("message", "")[:40]
        rows.append((post_id, msg, likes, comments, shares))

        if not dry_run:
            log_fb_engagement(post_id, likes, comments, shares)

    # Print summary table
    print(f"\n  {'Post ID':<30} {'Preview':<42} {'Likes':>6} {'Cmts':>6} {'Shares':>6}")
    print(f"  {'-'*30} {'-'*42} {'-'*6} {'-'*6} {'-'*6}")
    for pid, msg, l, c, s in rows:
        print(f"  {pid:<30} {msg:<42} {l:>6} {c:>6} {s:>6}")
    print(f"  {'-'*30} {'-'*42} {'-'*6} {'-'*6} {'-'*6}")
    print(f"  {'TOTAL':<30} {'':<42} {total_likes:>6} {total_comments:>6} "
          f"{total_shares:>6}")
    avg_posts = len(rows) or 1
    print(f"  {'AVERAGE':<30} {'':<42} {total_likes/avg_posts:>6.1f} "
          f"{total_comments/avg_posts:>6.1f} {total_shares/avg_posts:>6.1f}")
    _run_stats["posts_monitored"] = len(rows)
    print(f"\n  Monitor: {len(rows)} posts scanned"
          f"{' (dry-run, not logged)' if dry_run else ', snapshots logged'}")


def cmd_crosspost(dry_run=False):
    """Post YouTube videos to the Facebook page."""
    if not os.path.exists(UPLOAD_REPORT):
        print(f"  SKIP --crosspost: {UPLOAD_REPORT} not found")
        return

    with open(UPLOAD_REPORT) as f:
        report = json.load(f)

    results = report.get("results", [])
    today = datetime.utcnow().strftime("%Y-%m-%d")
    posted = 0

    for r in results:
        if r.get("status") != "success":
            continue

        video_title = r.get("file", "").replace(".mp4", "").replace("_", " ")
        video_url = r.get("url", "")
        channel = r.get("channel", "CumquatVibes")

        if not video_url:
            continue

        # Skip if already posted to Facebook page
        if was_posted_to_facebook(video_title, target="page"):
            continue

        # Enforce daily cap
        current_count = get_fb_crosspost_count(today)
        if current_count >= MAX_CROSSPOSTS_PER_DAY:
            print(f"  Crosspost daily cap reached ({MAX_CROSSPOSTS_PER_DAY})")
            break

        if dry_run:
            print(f"  [DRY-RUN] Would crosspost: {video_title[:60]} → {video_url}")
            posted += 1
            continue

        ok, result = post_to_facebook_page(video_title, video_url, channel)
        if ok:
            record_fb_crosspost(today)
            log_decision(
                video_name=video_title,
                decision_type="fb_bot_crosspost",
                objective="cross_platform_reach",
                chosen_action=f"Crossposted {channel}: {video_url}",
                expected_impact="increase_facebook_page_reach",
                risk_rating="low",
            )
            posted += 1
            _run_stats["videos_crossposted"] += 1
            print(f"  Crossposted: {video_title[:60]}")
        time.sleep(5)

    print(f"  Crosspost: {posted} videos {'(dry-run)' if dry_run else 'posted'}")


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description="Facebook Page automation bot for Cumquat Vibes")
    parser.add_argument("--comments", action="store_true",
                        help="Auto-reply to comments via Gemini")
    parser.add_argument("--engage", action="store_true",
                        help="Auto-like comments")
    parser.add_argument("--spam", action="store_true",
                        help="Delete spam comments")
    parser.add_argument("--monitor", action="store_true",
                        help="Log engagement metrics")
    parser.add_argument("--crosspost", action="store_true",
                        help="Post YouTube videos to Facebook page")
    parser.add_argument("--all", action="store_true",
                        help="Run all subcommands")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    parser.add_argument("--limit", type=int, default=25,
                        help="Number of posts to scan (default 25)")
    args = parser.parse_args()

    # Default to --all if nothing specified
    run_all = args.all or not any([
        args.comments, args.engage, args.spam, args.monitor, args.crosspost
    ])

    if not PAGE_TOKEN or len(PAGE_TOKEN) < 40:
        print("ERROR: FACEBOOK_PAGE_ACCESS_TOKEN missing or invalid")
        sys.exit(1)
    if not PAGE_ID:
        print("ERROR: FACEBOOK_PAGE_ID not set")
        sys.exit(1)

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"Facebook Bot [{mode}] — scanning {args.limit} posts")
    print(f"  Page ID: {PAGE_ID}")
    print()

    # Fetch posts once for commands that need them
    posts = []
    needs_posts = (run_all or args.comments or args.engage or args.spam
                   or args.monitor)
    if needs_posts:
        posts = _fetch_page_posts(args.limit)
        print(f"  Fetched {len(posts)} posts")
        if not posts:
            print("  No posts found — check PAGE_ID and token permissions")

    if run_all or args.spam:
        print("\n── Spam Detection ──")
        cmd_spam(posts, args.dry_run)

    if run_all or args.engage:
        print("\n── Auto-Like ──")
        cmd_engage(posts, args.dry_run)

    if run_all or args.comments:
        print("\n── Auto-Reply ──")
        cmd_comments(posts, args.dry_run)

    if run_all or args.monitor:
        print("\n── Engagement Monitor ──")
        cmd_monitor(posts, args.dry_run)

    if run_all or args.crosspost:
        print("\n── YouTube Crosspost ──")
        cmd_crosspost(args.dry_run)

    # ── Log run summary for learning loop ──
    if not args.dry_run and any(_run_stats.values()):
        summary = (f"replied={_run_stats['comments_replied']} "
                   f"liked={_run_stats['comments_liked']} "
                   f"spam_deleted={_run_stats['spam_deleted']}/{_run_stats['spam_scanned']} "
                   f"monitored={_run_stats['posts_monitored']} "
                   f"crossposted={_run_stats['videos_crossposted']} "
                   f"api_errors={_run_stats['api_errors']} "
                   f"gemini_failures={_run_stats['gemini_failures']}")
        log_decision(
            video_name=None,
            decision_type="fb_bot_run_summary",
            objective="page_automation",
            chosen_action=summary,
            expected_impact="track_bot_effectiveness_over_time",
            risk_rating="info",
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
