# Directive: Upload Video to YouTube

## Goal

Upload produced videos (long-form and Shorts) to the correct YouTube brand channels with SEO-optimized metadata, custom thumbnails, compliance checks, and automatic Facebook cross-posting.

## Inputs

- **video files**: MP4 files in `output/videos/` (long-form) or `output/shorts/` (Shorts)
- **script files**: Matching `.txt` scripts in `output/scripts/` (used for description, chapters, tags)
- **channel_tokens.json**: Per-channel OAuth refresh tokens (set up via `setup_channel_auth.py`)
- **google_token.json**: Default OAuth token (fallback if no channel-specific token exists)

## Execution Scripts

| Script | Purpose |
|--------|---------|
| `upload_to_youtube.py` | Long-form video upload with thumbnails, chapters, affiliate links |
| `upload_shorts_to_youtube.py` | Shorts upload (no thumbnails, adds #Shorts tag) |
| `setup_channel_auth.py` | OAuth token setup for each brand channel |
| `utils/facebook.py` | Facebook page + group cross-posting after upload |
| `utils/compliance.py` | Pre-upload compliance/preflight check |
| `utils/telemetry.py` | Logs uploads and quota usage to pipeline.db |

## Steps

### 1. Pre-flight

Before uploading, the script automatically:
- Loads per-channel OAuth tokens from `channel_tokens.json` and refreshes them
- Falls back to the default `google_token.json` if a channel-specific token is missing
- Loads `output/reports/youtube_upload_report.json` to skip already-uploaded videos
- Runs compliance preflight checks (script content, title, description, tags, synthetic media flag)

### 2. Channel Routing

Videos are routed to channels based on filename prefix:
- Filename `RichTech_Some_Title.mp4` routes to the `RichTech` channel
- The `CHANNEL_MAP` dict maps prefixes to `(channel_id, category_id)` tuples
- 38+ channels are supported across 3 Google accounts (`rabreu84@gmail.com`, `furywall213@gmail.com`, `evarey69@gmail.com`)
- `TOKEN_KEY_MAP` handles prefix-to-token-name translation for channels with spaces (e.g., `HowToUseAI` -> `"How to Use AI"`)

### 3. Metadata Generation

For each video, the uploader generates:

**Title** (40-70 chars):
- Extracted from filename, converted to title case
- Preserves acronyms (AI, DIY, etc.)
- Truncates at word boundary if >70 chars
- For Shorts: appends `#Shorts` tag if title is under 92 chars

**Description**:
- First 2 lines = searchable hook (visible in search results)
- Script intro extracted (first 3 clean lines, up to 400 chars)
- Chapter timestamps (evenly spaced based on script sections)
- Amazon affiliate links for product channels (using tag `richstudio0f-20`)
- CTA section with subscribe/like/comment prompts
- Social links (cumquatvibes.com, richardabreu.studio, Facebook group)
- AI disclosure statement (`containsSyntheticMedia: true` flag set)
- Channel-specific hashtags

**Tags** (max 500 chars total):
- Channel-specific base tags from `CHANNEL_TAGS` dict
- Title keyword extraction (words >3 chars)
- Long-form adds niche-specific tags; Shorts adds "Shorts", "YouTube Shorts"

**Thumbnail** (long-form only):
- Generated via Gemini `gemini-2.0-flash-exp-image-generation`
- Channel-specific style prompts (e.g., RichHorror = "dark horror atmosphere, eerie fog")
- Bold text overlay with key title words
- Uploaded via YouTube thumbnails.set endpoint
- Skipped for Shorts (YouTube auto-generates)

### 4. Upload

- Uses YouTube Data API v3 resumable upload protocol
- 10MB chunk size for reliable large file uploads
- Handles HTTP 308 (resume) and 503 (retry after 10s) responses
- Videos uploaded as `public` by default
- `selfDeclaredMadeForKids: false` and `containsSyntheticMedia: true` always set

### 5. Post-Upload

After successful upload:
- Thumbnail uploaded (long-form only; requires phone-verified channel)
- Facebook cross-post to page + group via `utils/facebook.py`
- Telemetry logged to `output/pipeline.db` via `utils/telemetry.py`
- Upload report updated in `output/reports/youtube_upload_report.json`
- Report is deduplicated (latest entry per file wins)

## Quota Management

YouTube Data API v3 has a daily quota of 10,000 units:
- Each video upload costs ~1,600 units
- Each thumbnail upload costs ~50 units
- The uploader stops at 80% quota usage (8,000 units) to leave room for other API operations
- At 80% threshold: remaining videos are deferred to the next run
- Quota resets at midnight Pacific Time

Per-channel upload limits:
- YouTube enforces daily upload limits per channel (varies by channel age/standing)
- When `uploadLimitExceeded` is returned, that channel is added to `rate_limited_channels` set
- All remaining videos for that channel are skipped for the rest of the run
- Rate-limited channels retry after 24 hours

## Edge Cases / Known Issues

1. **Unverified channels can't upload custom thumbnails**: The YouTube API returns 403 when setting thumbnails on channels without phone verification. The uploader logs this but does not fail the upload itself. Fix: verify all channels via YouTube Studio.

2. **Upload limit detection**: YouTube returns `uploadLimitExceeded` in the error body, not a specific HTTP status code. The uploader checks the response body string to detect this. If the error format changes, uploads may fail silently.

3. **Token refresh failures**: If a channel's OAuth refresh token expires or is revoked, the uploader falls back to the default token, which uploads to the main channel instead of the target brand channel. Always check the upload report to verify videos landed on the correct channel.

4. **Affiliate link channels**: Only channels in the `AFFILIATE_CHANNELS` set get Amazon links in descriptions. If a new product-review channel is added, it must be added to this set explicitly.

5. **Facebook posting never blocks uploads**: `utils/facebook.py` is wrapped in try/except so Facebook failures don't prevent YouTube uploads. Check logs for Facebook warnings separately.

6. **Shorts title length**: Shorts titles get `#Shorts` appended only if the title is under 92 characters. Longer titles may not surface properly in the Shorts shelf.

7. **Quota tracking is per-run, not per-day**: The uploader tracks quota usage within a single execution. If you run the uploader multiple times in one day, each run starts its quota counter at 0. Use `utils/telemetry.py` `get_daily_quota()` for accurate cross-run tracking.

## Learnings

- Resumable uploads handle network interruptions gracefully -- the 308 response contains the byte offset to resume from.
- Channel-specific thumbnail styles dramatically improve CTR. Each channel has a distinct visual identity in `CHANNEL_THUMBNAIL_STYLE`.
- The `+faststart` moov atom flag should be set during video assembly, not upload. The uploader expects properly formatted MP4 files.
- Amazon affiliate tag `richstudio0f-20` and store ID `7193294712` are used across all affiliate channels.
- Always set `containsSyntheticMedia: true` -- YouTube requires this disclosure for AI-generated content.
