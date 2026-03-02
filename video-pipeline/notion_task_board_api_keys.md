# Notion Task Board: API Key Tutorial Series (RichTech)

**Post to: Shared Claude Team workspace in Notion**
**Priority: HIGH — API key tutorials are proven high-view content**
**Date Created: 2026-03-02**

---

## Announcement: yt-dlp Installed

yt-dlp is installed on the Mac at `/Users/richardabreu/Library/Python/3.9/bin/yt-dlp` (also accessible via `python3 -m yt_dlp`). Used by the new competitive benchmarking system (`utils/competitive.py`) to extract competitor video transcripts for script quality improvement. Available for any future pipeline features that need YouTube video/audio/subtitle extraction.

---

## Project Overview

Create a comprehensive API key tutorial series for the RichTech channel. Research shows API key tutorials are among the highest-performing tech content on YouTube (top videos: 500K-2M+ views). We have 200+ APIs cataloged across 23 categories.

**Research file:** `video-pipeline/api-key-tutorials-research.md`
**Target channel:** `rich_tech`
**Pipeline:** `faceless_pipeline.py` or `batch_generate_scripts.py`

---

## Task Breakdown

### PHASE 1: Tier 1 Scripts (Highest View Potential) — Assign to Claude A

Generate scripts for the top 15 highest-demand API key tutorials. These are the money makers.

| # | Video Topic | Est. Views | Format |
|---|------------|-----------|--------|
| 1 | How to Get Your OpenAI API Key (ChatGPT/GPT-4) in 2026 | 500K-2M | tutorial |
| 2 | How to Get a Google Maps API Key (Step-by-Step) | 500K-1M | tutorial |
| 3 | How to Get a YouTube Data API Key in 2026 | 300K-800K | tutorial |
| 4 | How to Get Stripe API Keys (Test + Live) | 200K-500K | tutorial |
| 5 | How to Create a Discord Bot Token (2026 Guide) | 200K-500K | tutorial |
| 6 | How to Get a Google Gemini API Key for Free | 200K-500K | tutorial |
| 7 | How to Get PayPal API Credentials (Client ID + Secret) | 150K-400K | tutorial |
| 8 | How to Get a Twitter/X API Key in 2026 | 150K-400K | tutorial |
| 9 | How to Get Firebase API Keys (Complete Setup) | 100K-300K | tutorial |
| 10 | How to Get a Claude API Key (Anthropic) | 100K-300K | tutorial |
| 11 | How to Get AWS Access Keys (IAM Setup) | 100K-300K | tutorial |
| 12 | How to Get Instagram Graph API Access | 100K-300K | tutorial |
| 13 | How to Create a Telegram Bot Token (BotFather) | 100K-300K | tutorial |
| 14 | How to Get an ElevenLabs API Key | 100K-300K | tutorial |
| 15 | How to Get a Google Sheets API Key | 100K-200K | tutorial |

**Commands:**
```bash
cd /Users/richardabreu/Projects/RichardAbreuPortfolio/video-pipeline
# Generate one at a time:
python3 faceless_pipeline.py produce rich_tech "How to Get Your OpenAI API Key in 2026" --format tutorial --skip-audio
# Or batch from file:
python3 faceless_pipeline.py batch rich_tech phase1_topics.txt --skip-audio
```

**Per-video requirements:**
- Script must include step-by-step instructions with [VISUAL: screenshot of exact screen] directions
- Include pricing info (free tier limits, costs)
- Include common mistakes / troubleshooting section
- Hook should mention how many people search for this

---

### PHASE 2: Compilation Videos — Assign to Claude B

High-view-potential compilation/listicle videos that cover multiple APIs per video.

| # | Video Topic | Est. Views | Format |
|---|------------|-----------|--------|
| 1 | Top 10 Free API Keys Every Developer Needs in 2026 | 500K+ | listicle |
| 2 | How to Get API Keys for Every AI Service (OpenAI, Gemini, Claude, DeepSeek) | 300K+ | listicle |
| 3 | Every Google API Key Explained (Maps, YouTube, Sheets, Drive, Gmail) | 200K+ | listicle |
| 4 | 7 Free API Keys for Your First Coding Project | 200K+ | listicle |
| 5 | API Keys for Building a Full-Stack App (Complete Guide) | 150K+ | explainer |
| 6 | Payment API Keys: Stripe vs PayPal vs Square (Setup Guide) | 100K+ | listicle |
| 7 | 5 Free AI API Keys You Can Get Right Now (2026) | 200K+ | listicle |
| 8 | Social Media API Keys: Twitter, Instagram, TikTok, Discord | 100K+ | listicle |

**Commands:**
```bash
python3 faceless_pipeline.py batch rich_tech phase2_compilation_topics.txt --format listicle --skip-audio
```

---

### PHASE 3: Tier 2-3 Individual Tutorials — Assign to Claude C

Solid-demand APIs, each gets its own tutorial.

| # | Video Topic | Format |
|---|------------|--------|
| 1 | How to Get a Spotify API Key (Client ID + Secret) | tutorial |
| 2 | How to Get an OpenWeatherMap API Key | tutorial |
| 3 | How to Get a Twilio API Key (SMS + Voice) | tutorial |
| 4 | How to Get Shopify API Credentials | tutorial |
| 5 | How to Get a GitHub Personal Access Token | tutorial |
| 6 | How to Get a DeepSeek API Key | tutorial |
| 7 | How to Get Supabase API Keys (anon + service) | tutorial |
| 8 | How to Get a Stability AI API Key (Stable Diffusion) | tutorial |
| 9 | How to Get a Notion API Key (Integration Token) | tutorial |
| 10 | How to Get a Groq API Key (Free Fast AI) | tutorial |
| 11 | How to Get Clerk API Keys (Auth for Next.js) | tutorial |
| 12 | How to Get a Mapbox Access Token | tutorial |
| 13 | How to Get a RapidAPI Key (Access 40K+ APIs) | tutorial |
| 14 | How to Get TMDB API Key (Movie Database) | tutorial |
| 15 | How to Get a Cloudinary API Key | tutorial |

**Commands:**
```bash
python3 faceless_pipeline.py batch rich_tech phase3_topics.txt --format tutorial --skip-audio
```

---

### PHASE 4: Screenshots & Visual Assets — Any Claude with Browser Access

For each tutorial, we need actual screenshots of the API key retrieval process. These become the [VISUAL:] assets in the scripts.

**Per API, capture:**
1. Landing page / sign-up page
2. Dashboard after login
3. API key creation screen
4. The actual key display (redacted)
5. Where to find documentation
6. Billing/pricing page (if applicable)

**Storage:** Save to `output/broll/api_key_screenshots/[service_name]/` — numbered 001.png through 005.png

**Priority order:** Follow Phase 1 order (OpenAI first, then Google Maps, etc.)

---

### PHASE 5: Pipeline Optimization — Assign to Claude D

After scripts are generated, run them through the full pipeline:

1. **B-roll generation** — `python3 batch_generate_broll.py` (uses [VISUAL:] tags from scripts)
2. **Audio** — Richard records voiceovers himself (skip ElevenLabs TTS)
3. **Video assembly** — `python3 batch_produce.py` after audio is ready
4. **Thumbnails** — `python3 backfill_thumbnails.py`
5. **Upload** — `python3 upload_to_youtube.py`

**SEO optimization per video:**
- Title: "How to Get [Service] API Key in 2026 (Step-by-Step)"
- Tags: api key, [service name], [service name] api, how to get api key, [service name] tutorial, developer tools, 2026
- Description: Step-by-step with timestamps, links to service, related videos

---

## Progress Tracker

| Phase | Task | Status | Details |
|-------|------|--------|---------|
| 1 | Tier 1 scripts (15 videos) | DONE | 15/15 scripts + SEO metadata generated |
| 1 | Tier 1 B-roll | DONE | 373 images generated (97.9% success) |
| 2 | Compilation scripts (8 videos) | DONE | 8/8 scripts + SEO metadata generated |
| 2 | Compilation B-roll | IN PROGRESS | Running batch_generate_broll.py |
| 3 | Tier 2-3 scripts (15 videos) | PENDING | Assign to next available Claude |
| 4 | Screenshot assets | PENDING | Needs Claude with browser access |
| 5 | Pipeline (broll, assembly, upload) | BLOCKED | Waiting on Richard's voiceovers |

**Last updated: 2026-03-02**

## Assignment Summary

| Phase | Task | Assignee | Dependencies |
|-------|------|----------|-------------|
| 1 | Tier 1 scripts (15 videos) | Claude A | None |
| 2 | Compilation scripts (8 videos) | Claude B | None |
| 3 | Tier 2-3 scripts (15 videos) | Claude C | None |
| 4 | Screenshot assets | Any Claude w/ browser | None (parallel) |
| 5 | Pipeline (broll, assembly, upload) | Claude D | Phases 1-3 scripts + Richard's voiceovers |

**Phases 1-4 can run in parallel. Phase 5 depends on scripts + voiceovers.**

---

## Notes

- All scripts should use `--skip-audio` since Richard records voiceovers himself
- The competitive benchmarking system (`utils/competitive.py`) will automatically inject competitor insights into script generation
- Research data is in `video-pipeline/api-key-tutorials-research.md` (200+ APIs cataloged)
- Prioritize quality over quantity — best scripts first, don't blast-generate
