# Directive: Produce Video

## Goal

Take a channel key and topic through the full production pipeline: generate a script, produce TTS audio, generate B-roll images, assemble video with Ken Burns effects, and upload to YouTube. The end result is a published video on the correct brand channel.

## Inputs

- **channel_key**: The channel identifier from `channels_config.json` (e.g., `rich_tech`, `rich_horror`, `eva_reyes`)
- **topic**: A video title/topic string (e.g., "10 AI Tools That Changed 2026")
- **format**: `landscape` (1920x1080) or `shorts` (1080x1920). Defaults to landscape.
- **tier** (optional): For batch runs -- `priority`, `secondary`, or `growth`. Controls channel ordering.
- **count** (optional): Number of topics/scripts to generate per channel.

## Execution Scripts

| Step | Script | Purpose |
|------|--------|---------|
| 1. Script generation | `batch_generate_scripts.py` or `faceless_pipeline.py script <channel> <topic>` | Generates Gemini-powered scripts with [VISUAL:] tags, chapter markers, and emotion cues |
| 2. TTS audio | `batch_generate_audio.py` or `faceless_pipeline.py audio <channel> <topic>` | Cleans script for TTS, generates voiceover via ElevenLabs API |
| 3. B-roll images | `batch_generate_broll.py` | Generates images from [VISUAL:] tags using Gemini image generation |
| 4. Video assembly | `utils/assembly.py` (called by batch producers) | Ken Burns pan/zoom on B-roll images, crossfade transitions, audio merge via ffmpeg |
| 5. Trim (if needed) | `trim_long_videos.py` | Stream-copy trim to 14m00s for unverified channels (15min YouTube limit) |
| 6. Upload | `upload_to_youtube.py` (long-form) or `upload_shorts_to_youtube.py` (shorts) | Resumable upload, SEO metadata, thumbnails, Facebook cross-post |

For CumquatVibes (avatar channel), use `produce_video.py` instead -- it uses HeyGen digital avatar + MoviePy composition rather than the faceless B-roll pipeline.

## Steps

### 1. Generate Script

Run `faceless_pipeline.py script <channel_key> "<topic>"` or use `batch_generate_scripts.py` for bulk generation.

- Scripts are saved to `output/scripts/` as `.txt` files
- Filename format: `{ChannelPrefix}_{SafeTitle}_{timestamp}.txt`
- Scripts include YAML frontmatter, chapter markers (`## Chapter N: Title`), and `[VISUAL: description]` tags
- Competitive intelligence is injected automatically via `utils/competitive.py` (cached 7 days in SQLite)
- Gemini API is called with `gemini-2.0-flash`, temperature 0.9, max 4096 tokens
- Rate limiting: 2s sleep between scripts, 1s between channels

### 2. Generate TTS Audio

Run `batch_generate_audio.py` (processes all scripts missing audio) or target specific channels with args.

- See `directives/tts_generation.md` for full TTS details
- Audio saved to `output/audio/` as `.mp3` files
- Script text is cleaned before TTS (see TTS directive for cleaning rules)

### 3. Generate B-Roll

Run `batch_generate_broll.py` to generate images for all scripts with `[VISUAL:]` tags.

- Images saved to `output/broll/{script_name}/broll_01.png`, `broll_02.png`, etc.
- Daily quota cap: 1800 images (under Gemini free tier ~2000/day)
- Scripts with fewer visuals are processed first for maximum channel coverage
- Stops after 5 consecutive full failures (likely rate limited)
- Estimated rate: ~6 seconds per image

### 4. Assemble Video

`utils/assembly.py` is called by batch producers (not run standalone).

- Splits audio duration into 8-second segments
- Each segment gets a Ken Burns effect (6 presets cycled: zoom in, zoom out, pan left, pan right, corner zooms)
- B-roll images are cycled if there are more segments than images
- Crossfade transitions (0.5s default) between segments
- For >20 segments, crossfades are processed in batches of 10 to manage ffmpeg filter complexity
- Falls back to simple concatenation if crossfade fails
- Final merge: video (libx264) + audio (AAC 192k) with `-shortest` and `+faststart`
- Output: 1920x1080 MP4

### 5. Trim Long Videos

Run `trim_long_videos.py` for any videos exceeding 15 minutes.

- Uses ffmpeg stream copy (no re-encoding) -- very fast
- Trims to 14m00s (840s) with safety buffer for keyframe drift
- Originals backed up to `output/videos/originals_60min/`
- Supports `--dry-run` and `--channel` filters

### 6. Upload to YouTube

Run `upload_to_youtube.py` (long-form) or `upload_shorts_to_youtube.py` (shorts).

- See `directives/upload_video.md` for full upload details

## Edge Cases / Known Issues

1. **ElevenLabs quota exhaustion**: The ElevenLabs API has a monthly character limit. When exhausted, `batch_generate_audio.py` returns 0-byte files. Monitor the character count per script (~4000-8000 chars per video). Consider edge-tts or F5-TTS as fallbacks for non-priority channels.

2. **`[^:]` regex eating body text**: Earlier versions of `clean_script_for_tts()` used `[^:]` in header-stripping regexes that accidentally consumed lines of body text after colons. The fix was to use `[^:\n]*` to prevent matching across newlines. If scripts sound like they're missing sections, check the TTS cleaning regex.

3. **VIDEO_METADATA block not stripped**: Gemini sometimes generates a `VIDEO_METADATA:` block at the top of scripts with key-value lines. If not stripped before TTS, the voice reads metadata aloud ("title: Best AI Tools..."). The fix is in `clean_script_for_tts()` with a specific regex: `r'^VIDEO_METADATA:\s*\n(?:\s+\w.*\n)*'`.

4. **Unverified channel 15-minute limit**: YouTube channels without phone verification cannot upload videos longer than 15 minutes. `trim_long_videos.py` handles this, but stream-copy trimming can overshoot by a few seconds at keyframe boundaries. Target is 14m00s to leave buffer.

5. **Gemini B-roll rate limits**: Gemini image generation has ~2000 requests/day on free tier. The batch script caps at 1800 and stops after 5 consecutive failures. If you need more images, wait until quota resets (midnight PT) and re-run.

6. **Ken Burns crossfade complexity**: For videos with >20 segments, ffmpeg's xfade filter graph becomes too large. The assembly module processes in batches of 10 with crossfade within batches, then simple concat between batches.

7. **Channel prefix mapping**: Script filenames use CamelCase prefixes (e.g., `RichTech`, `HowToUseAI`) while channel keys use snake_case (e.g., `rich_tech`, `how_to_use_ai`). Both `batch_generate_scripts.py` and `batch_generate_audio.py` maintain prefix maps for this conversion. If a new channel is added, both maps must be updated.

## Learnings

- Competitive briefs from `utils/competitive.py` are cached 7 days in SQLite (`output/pipeline.db`), so repeated calls for the same channel are free.
- Gemini `gemini-2.0-flash` is used for scripts (temperature 0.9) and `gemini-2.0-flash-exp-image-generation` for B-roll/thumbnails.
- The "Result First" hook pattern (show end result in first 5 seconds, then explain how) consistently outperforms generic intros.
- Priority channel ordering for batch runs: `rich_finance`, `rich_science` first, then secondary tier, then growth tier.
- Assembly requires ffmpeg and ffprobe installed system-wide.
