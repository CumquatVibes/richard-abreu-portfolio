#!/usr/bin/env python3
"""Capture screenshot assets for API key tutorial series.

Uses Playwright (headless Chromium) to screenshot public pages for each
API service: landing page, sign-up, docs, pricing, and developer console/dashboard.

Authenticated pages (actual dashboards, key creation screens) are captured
as their login/gate page — Richard can replace with real screenshots later.

Usage:
    python3 capture_api_screenshots.py              # all services
    python3 capture_api_screenshots.py openai stripe # specific services
"""

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "broll", "api_key_screenshots")

# All services across Phase 1, 2, and 3 with their public URLs
# Each service has: landing, signup, docs, pricing, dashboard/console
SERVICES = {
    # --- Phase 1: Tier 1 ---
    "openai": {
        "name": "OpenAI",
        "pages": {
            "001_landing": "https://openai.com",
            "002_signup": "https://platform.openai.com/signup",
            "003_dashboard": "https://platform.openai.com/api-keys",
            "004_docs": "https://platform.openai.com/docs/quickstart",
            "005_pricing": "https://openai.com/api/pricing",
        },
    },
    "google_maps": {
        "name": "Google Maps",
        "pages": {
            "001_landing": "https://developers.google.com/maps",
            "002_console": "https://console.cloud.google.com/apis/credentials",
            "003_docs": "https://developers.google.com/maps/documentation",
            "004_pricing": "https://cloud.google.com/maps-platform/pricing",
            "005_signup": "https://console.cloud.google.com/freetrial",
        },
    },
    "youtube_data": {
        "name": "YouTube Data API",
        "pages": {
            "001_landing": "https://developers.google.com/youtube/v3",
            "002_console": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
            "003_docs": "https://developers.google.com/youtube/v3/getting-started",
            "004_quotas": "https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas",
            "005_credentials": "https://console.cloud.google.com/apis/credentials",
        },
    },
    "stripe": {
        "name": "Stripe",
        "pages": {
            "001_landing": "https://stripe.com",
            "002_signup": "https://dashboard.stripe.com/register",
            "003_dashboard": "https://dashboard.stripe.com/apikeys",
            "004_docs": "https://docs.stripe.com/keys",
            "005_pricing": "https://stripe.com/pricing",
        },
    },
    "discord": {
        "name": "Discord Bot",
        "pages": {
            "001_landing": "https://discord.com/developers/applications",
            "002_docs": "https://discord.com/developers/docs/getting-started",
            "003_portal": "https://discord.com/developers/applications",
            "004_bot_docs": "https://discord.com/developers/docs/topics/oauth2",
            "005_intents": "https://discord.com/developers/docs/topics/gateway",
        },
    },
    "gemini": {
        "name": "Google Gemini",
        "pages": {
            "001_landing": "https://ai.google.dev",
            "002_studio": "https://aistudio.google.com/apikey",
            "003_docs": "https://ai.google.dev/gemini-api/docs/quickstart",
            "004_pricing": "https://ai.google.dev/pricing",
            "005_models": "https://ai.google.dev/gemini-api/docs/models",
        },
    },
    "paypal": {
        "name": "PayPal",
        "pages": {
            "001_landing": "https://developer.paypal.com",
            "002_signup": "https://developer.paypal.com/dashboard/applications/sandbox",
            "003_docs": "https://developer.paypal.com/api/rest/",
            "004_dashboard": "https://developer.paypal.com/dashboard",
            "005_pricing": "https://www.paypal.com/us/business/accept-payments",
        },
    },
    "twitter": {
        "name": "Twitter/X",
        "pages": {
            "001_landing": "https://developer.x.com",
            "002_portal": "https://developer.x.com/en/portal/dashboard",
            "003_docs": "https://developer.x.com/en/docs/twitter-api",
            "004_pricing": "https://developer.x.com/en/products",
            "005_signup": "https://developer.x.com/en/portal/petition/essential/basic-info",
        },
    },
    "firebase": {
        "name": "Firebase",
        "pages": {
            "001_landing": "https://firebase.google.com",
            "002_console": "https://console.firebase.google.com",
            "003_docs": "https://firebase.google.com/docs/web/setup",
            "004_pricing": "https://firebase.google.com/pricing",
            "005_config": "https://firebase.google.com/docs/web/learn-more#config-object",
        },
    },
    "claude": {
        "name": "Claude (Anthropic)",
        "pages": {
            "001_landing": "https://www.anthropic.com/api",
            "002_console": "https://console.anthropic.com",
            "003_docs": "https://docs.anthropic.com/en/docs/quickstart",
            "004_pricing": "https://www.anthropic.com/pricing",
            "005_keys": "https://console.anthropic.com/settings/keys",
        },
    },
    "aws": {
        "name": "AWS",
        "pages": {
            "001_landing": "https://aws.amazon.com",
            "002_console": "https://console.aws.amazon.com/iam",
            "003_docs": "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html",
            "004_pricing": "https://aws.amazon.com/free/",
            "005_signup": "https://portal.aws.amazon.com/billing/signup",
        },
    },
    "instagram": {
        "name": "Instagram Graph API",
        "pages": {
            "001_landing": "https://developers.facebook.com/docs/instagram-api",
            "002_explorer": "https://developers.facebook.com/tools/explorer/",
            "003_docs": "https://developers.facebook.com/docs/instagram-api/getting-started",
            "004_setup": "https://developers.facebook.com/apps/",
            "005_permissions": "https://developers.facebook.com/docs/instagram-api/reference",
        },
    },
    "telegram": {
        "name": "Telegram Bot",
        "pages": {
            "001_landing": "https://core.telegram.org/bots",
            "002_botfather": "https://core.telegram.org/bots/tutorial",
            "003_docs": "https://core.telegram.org/bots/api",
            "004_features": "https://core.telegram.org/bots/features",
            "005_payments": "https://core.telegram.org/bots/payments",
        },
    },
    "elevenlabs": {
        "name": "ElevenLabs",
        "pages": {
            "001_landing": "https://elevenlabs.io",
            "002_signup": "https://elevenlabs.io/sign-up",
            "003_docs": "https://elevenlabs.io/docs/api-reference/text-to-speech",
            "004_pricing": "https://elevenlabs.io/pricing",
            "005_dashboard": "https://elevenlabs.io/app/settings/api-keys",
        },
    },
    "google_sheets": {
        "name": "Google Sheets API",
        "pages": {
            "001_landing": "https://developers.google.com/sheets/api",
            "002_console": "https://console.cloud.google.com/apis/library/sheets.googleapis.com",
            "003_docs": "https://developers.google.com/sheets/api/quickstart/python",
            "004_credentials": "https://console.cloud.google.com/apis/credentials",
            "005_reference": "https://developers.google.com/sheets/api/reference/rest",
        },
    },
    # --- Phase 3: Tier 2-3 ---
    "spotify": {
        "name": "Spotify",
        "pages": {
            "001_landing": "https://developer.spotify.com",
            "002_dashboard": "https://developer.spotify.com/dashboard",
            "003_docs": "https://developer.spotify.com/documentation/web-api",
            "004_console": "https://developer.spotify.com/console",
            "005_guides": "https://developer.spotify.com/documentation/web-api/tutorials/getting-started",
        },
    },
    "openweathermap": {
        "name": "OpenWeatherMap",
        "pages": {
            "001_landing": "https://openweathermap.org",
            "002_signup": "https://home.openweathermap.org/users/sign_up",
            "003_api_keys": "https://home.openweathermap.org/api_keys",
            "004_docs": "https://openweathermap.org/api",
            "005_pricing": "https://openweathermap.org/price",
        },
    },
    "twilio": {
        "name": "Twilio",
        "pages": {
            "001_landing": "https://www.twilio.com",
            "002_signup": "https://www.twilio.com/try-twilio",
            "003_console": "https://console.twilio.com",
            "004_docs": "https://www.twilio.com/docs/usage/api",
            "005_pricing": "https://www.twilio.com/en-us/pricing",
        },
    },
    "shopify": {
        "name": "Shopify",
        "pages": {
            "001_landing": "https://shopify.dev",
            "002_partners": "https://partners.shopify.com/signup",
            "003_docs": "https://shopify.dev/docs/api/admin-rest",
            "004_apps": "https://shopify.dev/docs/apps/build",
            "005_pricing": "https://www.shopify.com/pricing",
        },
    },
    "github": {
        "name": "GitHub",
        "pages": {
            "001_landing": "https://github.com/settings/tokens",
            "002_docs": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
            "003_fine_grained": "https://github.com/settings/personal-access-tokens/new",
            "004_classic": "https://github.com/settings/tokens/new",
            "005_scopes": "https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps",
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "pages": {
            "001_landing": "https://www.deepseek.com",
            "002_platform": "https://platform.deepseek.com",
            "003_docs": "https://platform.deepseek.com/api-docs",
            "004_pricing": "https://platform.deepseek.com/api-docs/pricing",
            "005_keys": "https://platform.deepseek.com/api_keys",
        },
    },
    "supabase": {
        "name": "Supabase",
        "pages": {
            "001_landing": "https://supabase.com",
            "002_dashboard": "https://supabase.com/dashboard",
            "003_docs": "https://supabase.com/docs/guides/api",
            "004_pricing": "https://supabase.com/pricing",
            "005_settings": "https://supabase.com/docs/guides/api/api-keys",
        },
    },
    "stability_ai": {
        "name": "Stability AI",
        "pages": {
            "001_landing": "https://stability.ai",
            "002_platform": "https://platform.stability.ai",
            "003_docs": "https://platform.stability.ai/docs/api-reference",
            "004_pricing": "https://platform.stability.ai/pricing",
            "005_account": "https://platform.stability.ai/account/keys",
        },
    },
    "notion": {
        "name": "Notion",
        "pages": {
            "001_landing": "https://www.notion.so",
            "002_developers": "https://developers.notion.com",
            "003_integrations": "https://www.notion.so/my-integrations",
            "004_docs": "https://developers.notion.com/docs/getting-started",
            "005_reference": "https://developers.notion.com/reference/intro",
        },
    },
    "groq": {
        "name": "Groq",
        "pages": {
            "001_landing": "https://groq.com",
            "002_console": "https://console.groq.com",
            "003_docs": "https://console.groq.com/docs/quickstart",
            "004_keys": "https://console.groq.com/keys",
            "005_models": "https://console.groq.com/docs/models",
        },
    },
    "clerk": {
        "name": "Clerk",
        "pages": {
            "001_landing": "https://clerk.com",
            "002_signup": "https://dashboard.clerk.com/sign-up",
            "003_dashboard": "https://dashboard.clerk.com",
            "004_docs": "https://clerk.com/docs/quickstarts/nextjs",
            "005_pricing": "https://clerk.com/pricing",
        },
    },
    "mapbox": {
        "name": "Mapbox",
        "pages": {
            "001_landing": "https://www.mapbox.com",
            "002_signup": "https://account.mapbox.com/auth/signup/",
            "003_account": "https://account.mapbox.com",
            "004_docs": "https://docs.mapbox.com/api/overview/",
            "005_pricing": "https://www.mapbox.com/pricing",
        },
    },
    "rapidapi": {
        "name": "RapidAPI",
        "pages": {
            "001_landing": "https://rapidapi.com",
            "002_signup": "https://rapidapi.com/auth/sign-up",
            "003_hub": "https://rapidapi.com/hub",
            "004_docs": "https://docs.rapidapi.com/docs/keys",
            "005_pricing": "https://rapidapi.com/pricing",
        },
    },
    "tmdb": {
        "name": "TMDB",
        "pages": {
            "001_landing": "https://www.themoviedb.org",
            "002_signup": "https://www.themoviedb.org/signup",
            "003_settings": "https://www.themoviedb.org/settings/api",
            "004_docs": "https://developer.themoviedb.org/docs/getting-started",
            "005_reference": "https://developer.themoviedb.org/reference/intro/getting-started",
        },
    },
    "cloudinary": {
        "name": "Cloudinary",
        "pages": {
            "001_landing": "https://cloudinary.com",
            "002_signup": "https://cloudinary.com/users/register_free",
            "003_console": "https://console.cloudinary.com",
            "004_docs": "https://cloudinary.com/documentation/how_to_integrate",
            "005_pricing": "https://cloudinary.com/pricing",
        },
    },
}


def capture_service(browser, service_key, service_config, retries=2):
    """Capture all pages for a single service."""
    name = service_config["name"]
    pages = service_config["pages"]
    svc_dir = os.path.join(OUTPUT_DIR, service_key)
    os.makedirs(svc_dir, exist_ok=True)

    # Check what's already captured
    existing = set(os.listdir(svc_dir))
    to_capture = {k: v for k, v in pages.items() if f"{k}.png" not in existing}

    if not to_capture:
        print(f"  [{service_key}] Already complete ({len(pages)} screenshots)")
        return len(pages), 0

    print(f"  [{service_key}] {name} — {len(to_capture)} pages to capture")

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    page = context.new_page()

    success = len(pages) - len(to_capture)
    failed = 0

    for filename, url in to_capture.items():
        out_path = os.path.join(svc_dir, f"{filename}.png")
        for attempt in range(retries + 1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                # Wait a bit for dynamic content
                page.wait_for_timeout(2000)
                # Dismiss common cookie/privacy banners
                for selector in [
                    "button:has-text('Accept')",
                    "button:has-text('Got it')",
                    "button:has-text('I agree')",
                    "button:has-text('Close')",
                    "[aria-label='Close']",
                ]:
                    try:
                        page.click(selector, timeout=1000)
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                page.screenshot(path=out_path, full_page=False)
                size_kb = os.path.getsize(out_path) // 1024
                print(f"    [{filename}] {url[:60]}... -> {size_kb} KB")
                success += 1
                break
            except Exception as e:
                if attempt < retries:
                    time.sleep(2)
                else:
                    print(f"    [{filename}] FAILED: {str(e)[:80]}")
                    failed += 1

    context.close()
    return success, failed


def main():
    from playwright.sync_api import sync_playwright

    # Filter to specific services if args given
    if len(sys.argv) > 1:
        keys = [k for k in sys.argv[1:] if k in SERVICES]
        if not keys:
            print(f"Unknown services. Available: {', '.join(sorted(SERVICES.keys()))}")
            sys.exit(1)
    else:
        keys = list(SERVICES.keys())

    total_pages = sum(len(SERVICES[k]["pages"]) for k in keys)
    print(f"{'=' * 60}")
    print(f"  API Key Screenshot Capture")
    print(f"  Services: {len(keys)} | Pages: {total_pages}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_success = 0
    total_failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for i, key in enumerate(keys, 1):
            config = SERVICES[key]
            print(f"\n[{i}/{len(keys)}] {config['name']}")
            s, f = capture_service(browser, key, config)
            total_success += s
            total_failed += f

        browser.close()

    print(f"\n{'=' * 60}")
    print(f"  COMPLETE")
    print(f"  Screenshots captured: {total_success}")
    print(f"  Failed: {total_failed}")
    print(f"  Success rate: {total_success / (total_success + total_failed) * 100:.1f}%")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
