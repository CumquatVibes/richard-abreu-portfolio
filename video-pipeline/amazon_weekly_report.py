#!/usr/bin/env python3
"""Amazon Associates Weekly Earnings & Analytics Report.

Generates a weekly report of Amazon affiliate earnings and saves to Google Drive.
Scheduled to run every Sunday.

Note: Amazon Associates doesn't have a public API for earnings data.
This script creates a report template that can be manually filled or
connected to Amazon's Product Advertising API for click/conversion tracking.

For automated earnings, use Amazon Associates reporting:
https://affiliate-program.amazon.com/home/reports

This script:
1. Generates a formatted weekly report template
2. Tracks which videos have affiliate links
3. Estimates performance based on YouTube analytics
4. Saves report to Google Drive
"""

import json
import os
import sys
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "google_token.json")
REPORTS_DIR = os.path.join(BASE_DIR, "output", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

AMAZON_STORE_ID = "7193294712"
AMAZON_AFFILIATE_TAG = "richstudio0f-20"

# Channels with affiliate links
AFFILIATE_CHANNELS = {
    "RichTech", "RichReviews", "HowToUseAI", "RichCars", "RichBeauty",
    "RichCooking", "RichFitness", "RichGaming", "RichFood", "RichDIY",
    "RichFashion", "RichPhotography", "EvaReyes", "RichMind", "RichLifestyle",
}

# Google Drive folder for reports
DRIVE_FOLDER_NAME = "Amazon Affiliate Reports"


def refresh_token():
    """Refresh OAuth token for Google Drive access."""
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


def find_or_create_drive_folder(access_token):
    """Find or create the Amazon Affiliate Reports folder on Google Drive."""
    # Search for existing folder
    query = f"name='{DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name)"
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("files"):
            return data["files"][0]["id"]
    except HTTPError:
        pass

    # Create folder
    folder_metadata = json.dumps({
        "name": DRIVE_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }).encode("utf-8")

    req = Request(
        "https://www.googleapis.com/drive/v3/files",
        data=folder_metadata,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["id"]


def get_uploaded_videos_with_affiliates():
    """Get list of uploaded videos that have affiliate links."""
    report_path = os.path.join(REPORTS_DIR, "youtube_upload_report.json")
    if not os.path.exists(report_path):
        return []

    with open(report_path) as f:
        data = json.load(f)

    affiliate_videos = []
    for result in data.get("results", []):
        if result.get("status") == "success" and result.get("video_id"):
            channel = result.get("channel", "")
            if channel in AFFILIATE_CHANNELS:
                affiliate_videos.append({
                    "channel": channel,
                    "video_id": result["video_id"],
                    "url": result.get("url", f"https://youtube.com/watch?v={result['video_id']}"),
                    "file": result.get("file", ""),
                })

    return affiliate_videos


def generate_report_content():
    """Generate the weekly report content."""
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday() + 1)  # Last Monday
    week_end = today

    affiliate_videos = get_uploaded_videos_with_affiliates()

    report = []
    report.append("=" * 60)
    report.append("AMAZON ASSOCIATES WEEKLY EARNINGS & ANALYTICS REPORT")
    report.append("=" * 60)
    report.append(f"Report Period: {week_start.strftime('%B %d, %Y')} - {week_end.strftime('%B %d, %Y')}")
    report.append(f"Generated: {today.strftime('%B %d, %Y at %I:%M %p')}")
    report.append(f"Affiliate Tag: {AMAZON_AFFILIATE_TAG}")
    report.append(f"Store ID: {AMAZON_STORE_ID}")
    report.append("")

    # Earnings section (manual entry or API integration)
    report.append("-" * 40)
    report.append("EARNINGS SUMMARY")
    report.append("-" * 40)
    report.append("(Log into Amazon Associates for actual figures)")
    report.append(f"  Dashboard: https://affiliate-program.amazon.com/home/reports")
    report.append("")
    report.append("  Total Clicks:        _________")
    report.append("  Total Orders:        _________")
    report.append("  Conversion Rate:     __________%")
    report.append("  Total Earnings:      $_________")
    report.append("  Shipped Revenue:     $_________")
    report.append("  Advertising Fees:    $_________")
    report.append("")

    # Active affiliate videos
    report.append("-" * 40)
    report.append(f"ACTIVE AFFILIATE VIDEOS ({len(affiliate_videos)})")
    report.append("-" * 40)

    if affiliate_videos:
        for v in affiliate_videos:
            report.append(f"  [{v['channel']}] {v['file']}")
            report.append(f"    URL: {v['url']}")
            report.append(f"    Clicks: ___  |  Orders: ___  |  Revenue: $___")
            report.append("")
    else:
        report.append("  No affiliate videos uploaded yet.")
        report.append("")

    # Sites with affiliate links
    report.append("-" * 40)
    report.append("SITES WITH AFFILIATE LINKS")
    report.append("-" * 40)
    report.append(f"  1. richardabreu.studio (portfolio)")
    report.append(f"  2. cumquatvibes.com (Shopify store)")
    report.append(f"  3. YouTube channels ({len(AFFILIATE_CHANNELS)} channels with affiliate descriptions)")
    report.append("")

    # Affiliate channels breakdown
    report.append("-" * 40)
    report.append("AFFILIATE CHANNEL BREAKDOWN")
    report.append("-" * 40)
    for ch in sorted(AFFILIATE_CHANNELS):
        report.append(f"  {ch}: Clicks: ___  |  Orders: ___  |  Revenue: $___")
    report.append("")

    # Top products (manual tracking)
    report.append("-" * 40)
    report.append("TOP PERFORMING PRODUCTS THIS WEEK")
    report.append("-" * 40)
    report.append("  1. ________________________________  |  Orders: ___  |  Revenue: $___")
    report.append("  2. ________________________________  |  Orders: ___  |  Revenue: $___")
    report.append("  3. ________________________________  |  Orders: ___  |  Revenue: $___")
    report.append("  4. ________________________________  |  Orders: ___  |  Revenue: $___")
    report.append("  5. ________________________________  |  Orders: ___  |  Revenue: $___")
    report.append("")

    # Week-over-week comparison
    report.append("-" * 40)
    report.append("WEEK-OVER-WEEK COMPARISON")
    report.append("-" * 40)
    report.append("  Clicks:    This Week: ___  |  Last Week: ___  |  Change: ___%")
    report.append("  Orders:    This Week: ___  |  Last Week: ___  |  Change: ___%")
    report.append("  Revenue:   This Week: $__  |  Last Week: $__  |  Change: ___%")
    report.append("  Conv Rate: This Week: ___%  |  Last Week: ___%  |  Change: ___%")
    report.append("")

    # Action items
    report.append("-" * 40)
    report.append("ACTION ITEMS FOR NEXT WEEK")
    report.append("-" * 40)
    report.append("  [ ] Review top-performing products and create more content around them")
    report.append("  [ ] Check which videos drive the most affiliate clicks")
    report.append("  [ ] Update product links for any discontinued/out-of-stock items")
    report.append("  [ ] Add affiliate links to any new video uploads")
    report.append("  [ ] Review Amazon Associates dashboard for earning trends")
    report.append("")

    report.append("=" * 60)
    report.append("END OF REPORT")
    report.append("=" * 60)
    report.append("")
    report.append("NOTE: For automated earnings data, consider integrating the")
    report.append("Amazon Product Advertising API (PA-API 5.0) for real-time")
    report.append("click and conversion tracking.")

    return "\n".join(report)


def upload_to_drive(content, filename, folder_id, access_token):
    """Upload report to Google Drive."""
    import urllib.parse

    # Create file metadata
    metadata = json.dumps({
        "name": filename,
        "parents": [folder_id],
        "mimeType": "text/plain",
    }).encode("utf-8")

    # Use multipart upload
    boundary = "----ReportBoundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata.decode('utf-8')}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain\r\n\r\n"
        f"{content}\r\n"
        f"--{boundary}--"
    ).encode("utf-8")

    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    req = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("id")
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"Drive upload error: {err[:300]}")
        return None


def main():
    print("Amazon Associates Weekly Report Generator")
    print("=" * 50)

    # Generate report
    report_content = generate_report_content()

    # Save locally
    today = datetime.now()
    filename = f"amazon_weekly_report_{today.strftime('%Y%m%d')}.txt"
    local_path = os.path.join(REPORTS_DIR, filename)
    with open(local_path, "w") as f:
        f.write(report_content)
    print(f"Report saved locally: {local_path}")

    # Upload to Google Drive
    print("\nUploading to Google Drive...")
    access_token = refresh_token()

    folder_id = find_or_create_drive_folder(access_token)
    print(f"Drive folder: {DRIVE_FOLDER_NAME} ({folder_id})")

    file_id = upload_to_drive(report_content, filename, folder_id, access_token)

    if file_id:
        drive_url = f"https://drive.google.com/file/d/{file_id}/view"
        print(f"Uploaded to Drive: {drive_url}")
    else:
        print("Drive upload failed — report saved locally only.")

    # Print the report
    print(f"\n{report_content}")


if __name__ == "__main__":
    main()
