# Directive: Competitive Analysis

## Goal

Benchmark each channel's niche against top-performing competitor videos on YouTube. Extract transcripts, analyze what makes them successful, and produce structured briefs that are injected into script generation prompts to improve title strength, hook quality, and content structure.

## Inputs

- **channel_key**: The channel identifier from `channels_config.json` (e.g., `rich_tech`)
- **channel_config**: The channel's config dict including `niche`, `sub_topics`, and `formats`
- **YOUTUBE_API_KEY**: For searching public video data
- **GEMINI_API_KEY**: For analyzing competitor transcripts

## Execution Scripts

| Script | Purpose |
|--------|---------|
| `utils/competitive.py` | Core competitive benchmarking module -- search, transcript, analysis, caching |
| `batch_generate_scripts.py` | Calls `get_competitive_brief()` before script generation |
| `daily_channel_analyzer.py` | Uses YouTube API for broader channel health analysis |

## Steps

### 1. Build Search Query

`_build_search_query(channel_config)` constructs a YouTube search query:
- Uses the channel's `niche` field as the base query
- Adds the first `sub_topic` only if the niche is very generic (2 words or fewer)
- Caps query at 50 characters to avoid overly narrow searches
- Example: niche="technology" + sub_topics=["AI tools"] -> "technology AI tools"

### 2. Fetch Top Competitor Video

`fetch_top_video(niche_query)` searches YouTube for recent high-performing content:
- Uses YouTube Data API v3 search endpoint
- Filters: `type=video`, `order=viewCount`, `videoDuration=medium`, `publishedAfter=90 days ago`
- Returns top result with: `video_id`, `title`, `channel_title`, `view_count`, `like_count`, `description`
- Fetches full statistics via the videos endpoint

### 3. Extract Transcript

`get_video_transcript(video_id, max_seconds=180)` downloads auto-captions:
- Uses `yt-dlp` to fetch English auto-generated subtitles in VTT format
- Parses VTT file, deduplicates overlapping subtitle lines
- Stops at the `max_seconds` timestamp (default 3 minutes -- just the hook + intro)
- Falls back to empty string if yt-dlp is not installed or times out (30s limit)

### 4. Analyze with Gemini

The transcript + video metadata are sent to Gemini Flash for analysis:
- Temperature 0.7, max 2048 tokens
- Prompt asks for: hook technique, title formula, content structure, engagement drivers
- Returns a structured brief that can be injected into script generation prompts

### 5. Cache Results

All competitive briefs are cached in SQLite (`output/pipeline.db`):
- Cache TTL: 7 days per channel
- Cache key: channel_key
- Repeated calls for the same channel return cached results (zero API cost)
- The batch script generator calls `get_competitive_brief()` twice per channel (once for topics, once for scripts) -- the second call is always a cache hit

### 6. Inject into Script Generation

The competitive brief is injected into both:
- **Topic generation prompt**: "Use these insights to adapt successful title formulas and trending angles. Your titles should be AS STRONG or STRONGER than the competitor's."
- **Script generation prompt**: "Apply the hook technique and actionable takeaways from above. Your hook MUST be as strong or stronger than the competitor's."

## Daily Channel Analysis

`daily_channel_analyzer.py` performs a broader analysis across all 38+ channels:

1. **Channel Health**: subscribers, total views, upload frequency
2. **SEO Audit**: title length (target 40-70 chars), description length (min 200), tag count (min 8)
3. **Thumbnail Assessment**: consistency and text overlay patterns
4. **Content Strategy**: upload cadence, topic gaps, trending alignment
5. **Engagement Metrics**: likes/views ratio (target >3%), comments, shares
6. **Playlist Organization**: coverage, naming, structure
7. **Branding Check**: description, banner, links, country
8. **Monetization Readiness**: watch hours, subscribers, metadata compliance

The analyzer runs across 3 Google accounts and outputs a detailed report to `output/daily_analysis/`. It can also push reports to Google Docs via OAuth.

### Benchmarks

| Metric | Target |
|--------|--------|
| Upload frequency | 3+ per week |
| Title length | 40-70 characters |
| Description length | 200+ characters |
| Tag count | 8+ tags |
| Engagement rate (likes/views) | 3%+ |
| CTR | 4%+ |
| Average view duration | 40%+ |
| Subscriber conversion | 5%+ |
| Shorts swipe-away rate | <90% |

## Edge Cases / Known Issues

1. **yt-dlp not installed**: Transcript extraction requires `yt-dlp` as a Python module (`python -m yt_dlp`). If not installed, the competitive brief will lack transcript analysis and rely only on title/description metadata. Install with `pip install yt-dlp`.

2. **YouTube API quota for search**: Each search request costs 100 quota units. With 38 channels refreshing weekly, that's ~544 units/week just for competitive analysis. This is well within the 10,000/day limit but be aware if combined with heavy upload days.

3. **VTT subtitle deduplication**: Auto-generated YouTube subtitles have overlapping timestamp segments. The parser deduplicates by tracking seen text lines, but occasionally a line appears in slightly different forms across segments. Minor duplication in transcripts is acceptable -- Gemini handles it gracefully.

4. **Empty search results**: For very niche or new topics, YouTube search may return zero results. `fetch_top_video()` returns `None`, and the competitive brief is omitted from the script generation prompt. This is fine -- scripts are still generated, just without competitive intelligence.

5. **Gemini rate limiting on analysis**: The analysis call uses temperature 0.7 with 2 retries. On 429 errors, it waits 15s * (attempt + 1). If both retries fail, the brief is empty. Since briefs are cached for 7 days, a single failure doesn't compound.

6. **Cache staleness**: 7-day cache TTL means competitive intelligence may be slightly outdated. For fast-moving niches (crypto, tech news), consider reducing TTL or manually clearing the cache: `DELETE FROM competitive_cache WHERE channel_key = 'rich_crypto'` in `output/pipeline.db`.

## Learnings

- Short, broad search queries (just the niche) produce better results than long, specific queries. YouTube's search algorithm handles relevance ranking well.
- The first 3 minutes of a competitor's transcript (the hook) is the most valuable data for script generation. Full transcripts add noise without proportional value.
- Competitor analysis has the highest ROI when injected into topic generation (better titles) rather than script body (which is already well-structured by the format template).
- Priority channels (`rich_finance`, `rich_science`) benefit most from competitive intelligence because their niches are highly competitive on YouTube.
- The `publishedAfter=90 days` filter ensures we benchmark against recent content, not outdated viral videos.
