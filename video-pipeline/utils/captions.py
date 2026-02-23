"""Caption engine for YouTube Shorts.

Handles audio transcription with word-level timestamps, caption segment
generation, and Pillow-based caption rendering burned directly into video
frames via ffmpeg pipe I/O.

Key constraint: ffmpeg on this system does NOT have drawtext or subtitles
filters compiled in.  All text rendering is done through Pillow, reading
raw frames from ffmpeg stdout and writing composited frames back to ffmpeg
stdin.
"""

import json
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# 1. Audio transcription (Whisper)
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path, model_size="base"):
    """Transcribe audio and return word-level timestamps using OpenAI Whisper.

    Args:
        audio_path: Path to audio file (mp3, wav, aac, etc.)
        model_size: Whisper model size — "tiny", "base", "small", "medium",
                    or "large".  Larger models are more accurate but slower.

    Returns:
        list[dict] | None: List of word dicts, each containing:
            - "word" (str): The transcribed word (stripped of whitespace).
            - "start" (float): Start time in seconds.
            - "end" (float): End time in seconds.
        Returns None if Whisper is not installed.
    """
    try:
        import whisper
    except ImportError:
        print("[captions] WARNING: openai-whisper not installed. "
              "Install with: pip install openai-whisper")
        print("[captions] Falling back to estimated timestamps.")
        return None

    model = whisper.load_model(model_size)
    result = model.transcribe(
        audio_path,
        word_timestamps=True,
        language="en",
        fp16=False,
    )

    words = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": float(w["start"]),
                "end": float(w["end"]),
            })

    return words


# ---------------------------------------------------------------------------
# 2. Fallback timestamp estimation
# ---------------------------------------------------------------------------

def estimate_word_timestamps(script_text, audio_duration):
    """Estimate word-level timestamps by distributing words proportionally.

    Distributes words across the audio duration based on character count,
    leaving a 5 % margin at the end so captions don't run to the very last
    frame.

    Args:
        script_text: Full script text (will be split on whitespace).
        audio_duration: Total audio length in seconds.

    Returns:
        list[dict]: Same format as transcribe_audio — each dict has
        "word", "start", and "end" keys.
    """
    raw_words = script_text.split()
    if not raw_words:
        return []

    usable_duration = audio_duration * 0.95  # 5 % margin at end
    total_chars = sum(len(w) for w in raw_words)
    if total_chars == 0:
        return []

    words = []
    cursor = 0.0

    for w in raw_words:
        word_duration = (len(w) / total_chars) * usable_duration
        words.append({
            "word": w,
            "start": round(cursor, 3),
            "end": round(cursor + word_duration, 3),
        })
        cursor += word_duration

    return words


# ---------------------------------------------------------------------------
# 3. Caption segment generation
# ---------------------------------------------------------------------------

def generate_caption_segments(words, style="capcut", words_per_group=3):
    """Group word-level timestamps into displayable caption segments.

    Args:
        words: List of word dicts from transcribe_audio or
               estimate_word_timestamps.
        style: Caption style — determines grouping behaviour.
            - "capcut": Groups of ``words_per_group`` (default 3).  Each
              word becomes the highlight in turn (highlight_word_idx
              cycles 0, 1, 2, ...).
            - "minimal": Groups of 5-7 words (subtitle lines), no
              highlight.
            - "karaoke": Single-word segments, each highlighted in turn.
        words_per_group: Number of words per group for "capcut" style.

    Returns:
        list[dict]: Caption segments, each with:
            - "text" (str): Joined display text.
            - "words" (list[str]): Individual words in the segment.
            - "highlight_word_idx" (int): Index of the highlighted word
              within the group (0-based).  -1 for styles without a
              highlight.
            - "start_sec" (float): Segment start time.
            - "end_sec" (float): Segment end time.
    """
    if not words:
        return []

    if style == "karaoke":
        return _segments_karaoke(words)
    elif style == "minimal":
        return _segments_minimal(words)
    else:
        return _segments_capcut(words, words_per_group)


def _segments_capcut(words, group_size):
    """CapCut-style: groups of N words with rotating highlight."""
    segments = []

    for group_start in range(0, len(words), group_size):
        group = words[group_start:group_start + group_size]

        # Each word in the group gets its own segment so the highlight
        # advances word-by-word while the surrounding text stays visible.
        for highlight_idx, active_word in enumerate(group):
            segment_words = [w["word"] for w in group]
            segments.append({
                "text": " ".join(segment_words),
                "words": segment_words,
                "highlight_word_idx": highlight_idx,
                "start_sec": active_word["start"],
                "end_sec": active_word["end"],
            })

    return segments


def _segments_minimal(words):
    """Subtitle-style: groups of 5-7 words, no highlight."""
    segments = []
    group_size = 6  # target middle of 5-7 range

    for group_start in range(0, len(words), group_size):
        group = words[group_start:group_start + group_size]
        segment_words = [w["word"] for w in group]
        segments.append({
            "text": " ".join(segment_words),
            "words": segment_words,
            "highlight_word_idx": -1,
            "start_sec": group[0]["start"],
            "end_sec": group[-1]["end"],
        })

    return segments


def _segments_karaoke(words):
    """Karaoke-style: single word per segment."""
    segments = []
    for w in words:
        segments.append({
            "text": w["word"],
            "words": [w["word"]],
            "highlight_word_idx": 0,
            "start_sec": w["start"],
            "end_sec": w["end"],
        })
    return segments


# ---------------------------------------------------------------------------
# 4. Render captions to video (pipe-based compositing)
# ---------------------------------------------------------------------------

def render_captions_to_video(input_video, output_video, caption_segments,
                             style="capcut", position="center"):
    """Burn captions into a video using Pillow compositing over ffmpeg pipes.

    Pipeline:
        1. Probe video for dimensions, fps, duration.
        2. Extract audio to a temp file.
        3. Decode video to raw RGB24 frames via ffmpeg stdout pipe.
        4. For each frame, composite the active caption using Pillow.
        5. Encode composited frames + original audio via ffmpeg stdin pipe.

    Args:
        input_video: Path to the source video.
        output_video: Path to write the captioned video.
        caption_segments: List of segment dicts from
                          generate_caption_segments.
        style: "capcut", "minimal", or "karaoke".
        position: Caption vertical position — "center" (65 % height),
                  "bottom" (80 % height), or "top" (20 % height).

    Returns:
        bool: True on success, False on failure.
    """
    # ------------------------------------------------------------------
    # Step 1 — probe video metadata
    # ------------------------------------------------------------------
    info = get_video_info(input_video)
    if not info:
        print("[captions] ERROR: Could not probe video info.")
        return False

    width = info["width"]
    height = info["height"]
    fps = info["fps"]
    frame_size = width * height * 3  # RGB24

    # ------------------------------------------------------------------
    # Step 2 — extract audio to temp file
    # ------------------------------------------------------------------
    temp_audio = None
    try:
        temp_fd, temp_audio = tempfile.mkstemp(suffix=".aac")
        os.close(temp_fd)

        # Try copying audio stream directly first
        audio_cmd = [
            "ffmpeg", "-y", "-i", input_video,
            "-vn", "-c:a", "copy", temp_audio,
        ]
        result = subprocess.run(audio_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Fallback: re-encode to AAC
            audio_cmd = [
                "ffmpeg", "-y", "-i", input_video,
                "-vn", "-c:a", "aac", "-b:a", "192k", temp_audio,
            ]
            result = subprocess.run(audio_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print("[captions] ERROR: Could not extract audio.")
                return False

        # ------------------------------------------------------------------
        # Step 3 — set up decode pipe (video -> raw RGB24 frames)
        # ------------------------------------------------------------------
        decode_cmd = [
            "ffmpeg",
            "-i", input_video,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-v", "quiet",
            "-",
        ]
        decode_proc = subprocess.Popen(
            decode_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        # ------------------------------------------------------------------
        # Step 4 — set up encode pipe (raw RGB24 frames + audio -> output)
        # ------------------------------------------------------------------
        encode_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",              # stdin — raw frames
            "-i", temp_audio,       # audio track
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-b:v", "2000k", "-maxrate", "2500k", "-bufsize", "5000k",
            "-c:a", "copy",
            "-shortest",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_video,
        ]
        encode_proc = subprocess.Popen(
            encode_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # ------------------------------------------------------------------
        # Step 5 — frame loop: read, composite, write
        # ------------------------------------------------------------------
        # Pre-load fonts once outside the loop
        font = _get_font(size=80, bold=True)
        font_highlight = _get_font(size=92, bold=True)
        font_minimal = _get_font(size=56, bold=False)

        # Build a sorted index for fast segment lookup
        seg_index = _build_segment_index(caption_segments)

        frame_num = 0
        while True:
            raw_data = decode_proc.stdout.read(frame_size)
            if len(raw_data) < frame_size:
                break  # end of video

            timestamp = frame_num / fps

            # Find active caption segment for this timestamp
            segment = _find_active_segment(seg_index, timestamp)

            if segment is not None:
                # Composite caption onto frame via Pillow
                img = Image.frombytes("RGB", (width, height), raw_data)
                draw = ImageDraw.Draw(img)

                if style == "minimal":
                    _render_minimal_text(
                        draw, width, height, segment, font_minimal,
                        position=position,
                    )
                elif style == "karaoke":
                    _render_capcut_text(
                        draw, width, height, segment,
                        font, font_highlight,
                        position=position,
                    )
                else:
                    _render_capcut_text(
                        draw, width, height, segment,
                        font, font_highlight,
                        position=position,
                    )

                raw_data = img.tobytes()

            try:
                encode_proc.stdin.write(raw_data)
            except BrokenPipeError:
                print("[captions] WARNING: Encode pipe closed early.")
                break

            frame_num += 1

        # ------------------------------------------------------------------
        # Step 6 — clean up pipes
        # ------------------------------------------------------------------
        decode_proc.stdout.close()
        decode_proc.wait()

        if encode_proc.stdin:
            encode_proc.stdin.close()
        encode_proc.wait()

        success = encode_proc.returncode == 0
        if success:
            print(f"[captions] Rendered {frame_num} frames -> {output_video}")
        else:
            print(f"[captions] ERROR: Encode process exited with "
                  f"code {encode_proc.returncode}")

        return success

    except Exception as exc:
        print(f"[captions] ERROR: {exc}")
        return False

    finally:
        if temp_audio and os.path.exists(temp_audio):
            try:
                os.unlink(temp_audio)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 5. CapCut-style text renderer
# ---------------------------------------------------------------------------

def _render_capcut_text(draw, img_width, img_height, segment,
                        font, font_highlight, position="center"):
    """Render CapCut-style caption with word-by-word highlighting.

    Draws each word individually so the active (highlighted) word can
    use a different colour and slightly larger font.  All words get a
    black outline for readability against any background.

    Args:
        draw: PIL ImageDraw instance.
        img_width: Frame width in pixels.
        img_height: Frame height in pixels.
        segment: Caption segment dict.
        font: Normal word font (ImageFont).
        font_highlight: Highlighted word font (ImageFont, slightly larger).
        position: "center" (65 %), "bottom" (80 %), or "top" (20 %).
    """
    words = segment.get("words", [])
    highlight_idx = segment.get("highlight_word_idx", -1)
    if not words:
        return

    # Determine vertical position
    if position == "top":
        y_pct = 0.20
    elif position == "bottom":
        y_pct = 0.80
    else:
        y_pct = 0.65

    # Measure total line width and find max ascent for vertical alignment
    space_width = _text_width(draw, " ", font)
    word_metrics = []
    total_width = 0

    for i, word in enumerate(words):
        f = font_highlight if i == highlight_idx else font
        w = _text_width(draw, word, f)
        word_metrics.append((word, f, w))
        total_width += w
        if i < len(words) - 1:
            total_width += space_width

    # Word-wrap: split into two lines if text exceeds 85 % of frame width
    max_line_width = int(img_width * 0.85)
    if total_width > max_line_width and len(words) > 1:
        _render_capcut_multiline(
            draw, img_width, img_height, words, highlight_idx,
            font, font_highlight, y_pct,
        )
        return

    # Single-line rendering
    x_start = (img_width - total_width) // 2
    y_pos = int(img_height * y_pct)

    # Semi-transparent background bar for readability on any B-roll
    text_h = _text_height(draw, "Ay", font_highlight)
    padding = 14
    bar_rect = [
        x_start - padding,
        y_pos - padding,
        x_start + total_width + padding,
        y_pos + text_h + padding,
    ]
    draw.rectangle(bar_rect, fill=(0, 0, 0, 160))

    x = x_start
    for i, (word, f, w) in enumerate(word_metrics):
        fill = "#FFD700" if i == highlight_idx else "white"
        _draw_outlined_text(draw, (x, y_pos), word, f, fill=fill)
        x += w + space_width


def _render_capcut_multiline(draw, img_width, img_height, words,
                             highlight_idx, font, font_highlight, y_pct):
    """Render CapCut text across two lines when it is too wide."""
    mid = len(words) // 2
    lines = [words[:mid], words[mid:]]

    space_width = _text_width(draw, " ", font)
    line_height = _text_height(draw, "Ay", font_highlight) + 8

    y_base = int(img_height * y_pct) - line_height // 2

    # Semi-transparent background bar behind both lines
    padding = 14
    max_line_w = max(
        sum(_text_width(draw, w, font_highlight) for w in line) + space_width * (len(line) - 1)
        for line in lines
    )
    bar_rect = [
        (img_width - max_line_w) // 2 - padding,
        y_base - padding,
        (img_width + max_line_w) // 2 + padding,
        y_base + line_height * len(lines) + padding,
    ]
    draw.rectangle(bar_rect, fill=(0, 0, 0, 160))

    global_idx = 0
    for line_num, line_words in enumerate(lines):
        # Measure line width
        line_width = 0
        metrics = []
        for word in line_words:
            f = font_highlight if global_idx + len(metrics) == highlight_idx else font
            w = _text_width(draw, word, f)
            metrics.append((word, f, w))
            line_width += w
        line_width += space_width * (len(line_words) - 1)

        x = (img_width - line_width) // 2
        y = y_base + line_num * line_height

        for word, f, w in metrics:
            fill = "#FFD700" if global_idx == highlight_idx else "white"
            _draw_outlined_text(draw, (x, y), word, f, fill=fill)
            x += w + space_width
            global_idx += 1


# ---------------------------------------------------------------------------
# 6. Minimal / subtitle text renderer
# ---------------------------------------------------------------------------

def _render_minimal_text(draw, img_width, img_height, segment, font,
                         position="center"):
    """Render subtitle-style caption with semi-transparent background bar.

    Args:
        draw: PIL ImageDraw instance.
        img_width: Frame width in pixels.
        img_height: Frame height in pixels.
        segment: Caption segment dict.
        font: Font for subtitle text (ImageFont).
        position: "center", "bottom", or "top".
    """
    text = segment.get("text", "")
    if not text:
        return

    if position == "top":
        y_pct = 0.20
    elif position == "bottom":
        y_pct = 0.80
    else:
        y_pct = 0.80  # minimal defaults to bottom-third regardless

    text_w = _text_width(draw, text, font)
    text_h = _text_height(draw, text, font)

    # Word-wrap if needed
    max_w = int(img_width * 0.90)
    if text_w > max_w:
        words = text.split()
        mid = len(words) // 2
        text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
        text_w = max(_text_width(draw, line, font) for line in text.split("\n"))
        text_h = text_h * 2 + 4

    x = (img_width - text_w) // 2
    y = int(img_height * y_pct)

    # Draw semi-transparent background bar
    padding = 12
    bar_rect = [
        x - padding,
        y - padding,
        x + text_w + padding,
        y + text_h + padding,
    ]
    draw.rectangle(bar_rect, fill=(0, 0, 0, 180))

    # Draw text
    draw.text((x, y), text, font=font, fill="white")


# ---------------------------------------------------------------------------
# 7. Font loading
# ---------------------------------------------------------------------------

def _get_font(size=64, bold=True):
    """Load a system font with macOS fallbacks.

    Tries several common macOS font paths in order of preference, falling
    back to Pillow's built-in default font if nothing else works.

    Args:
        size: Font size in pixels.
        bold: Whether to prefer a bold weight (used in path selection).

    Returns:
        PIL ImageFont instance.
    """
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue

    # Last resort: Pillow default
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow versions don't accept size= on load_default
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 8. Outlined text drawing
# ---------------------------------------------------------------------------

def _draw_outlined_text(draw, position, text, font, fill="white",
                        outline="black", outline_width=3):
    """Draw text with a stroke outline for readability on any background.

    Renders the outline by drawing the text offset in all eight cardinal
    and ordinal directions, then draws the main text on top.

    Args:
        draw: PIL ImageDraw instance.
        position: (x, y) tuple for the top-left of the text.
        text: String to draw.
        font: PIL ImageFont.
        fill: Main text colour (default "white").
        outline: Outline colour (default "black").
        outline_width: Outline thickness in pixels (default 3).
    """
    x, y = position

    # Draw outline by offsetting in 8 directions
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=outline)

    # Draw main text
    draw.text((x, y), text, font=font, fill=fill)


# ---------------------------------------------------------------------------
# 9. Video info via ffprobe
# ---------------------------------------------------------------------------

def get_video_info(video_path):
    """Get video metadata (dimensions, fps, duration) via ffprobe.

    Args:
        video_path: Path to a video file.

    Returns:
        dict | None: Dictionary with keys "width" (int), "height" (int),
        "fps" (float), and "duration" (float in seconds).  Returns None
        if ffprobe fails.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)

        # Find the video stream
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            return None

        width = int(video_stream["width"])
        height = int(video_stream["height"])

        # Parse fps from r_frame_rate (e.g. "30/1" or "30000/1001")
        fps_str = video_stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(fps_str)

        # Duration: prefer stream duration, fall back to format duration
        duration = float(
            video_stream.get("duration")
            or data.get("format", {}).get("duration", "0")
        )

        return {
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "duration": round(duration, 3),
        }

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        print(f"[captions] ffprobe error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_segment_index(segments):
    """Pre-sort caption segments by start time for binary-search lookup.

    Returns:
        list[tuple]: Sorted list of (start_sec, end_sec, segment_dict).
    """
    indexed = []
    for seg in segments:
        indexed.append((seg["start_sec"], seg["end_sec"], seg))
    indexed.sort(key=lambda t: t[0])
    return indexed


def _find_active_segment(seg_index, timestamp):
    """Find the caption segment active at a given timestamp.

    Uses linear scan (fast enough for typical segment counts < 500).
    For extremely dense caption tracks, a binary search could be added.

    Args:
        seg_index: Sorted list from _build_segment_index.
        timestamp: Current frame time in seconds.

    Returns:
        dict | None: The active segment, or None if no segment covers
        this timestamp.
    """
    for start, end, seg in seg_index:
        if start <= timestamp < end:
            return seg
        if start > timestamp:
            break  # segments are sorted; no point checking further
    return None


def _text_width(draw, text, font):
    """Measure text width in pixels, compatible across Pillow versions."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except AttributeError:
        w, _ = draw.textsize(text, font=font)
        return w


def _text_height(draw, text, font):
    """Measure text height in pixels, compatible across Pillow versions."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[3] - bbox[1]
    except AttributeError:
        _, h = draw.textsize(text, font=font)
        return h
