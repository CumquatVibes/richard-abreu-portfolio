"""Shorts engine for the video pipeline.

Handles script segment parsing, clip extraction, vertical cropping,
vertical Ken Burns assembly, hook text overlays, and platform metadata.

Key constraint: ffmpeg on this system does NOT have drawtext or subtitles
filters. Hook overlay uses Pillow frame compositing via ffmpeg pipe I/O.
"""

import math
import os
import re
import shutil
import struct
import subprocess
import tempfile

from utils.assembly import get_audio_duration
from utils.common import strip_timestamp, get_channel_from_filename

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERTICAL_WIDTH = 1080
VERTICAL_HEIGHT = 1920
VERTICAL_FPS = 30

SHORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "shorts",
)

# Vertical Ken Burns effect presets — 6 effects cycled through segments.
# Compared to the horizontal presets in assembly.py these use:
#   - 9:16 output (1080x1920) instead of 16:9 (1920x1080)
#   - Vertical pan directions (up/down) instead of left/right
#   - 1.5x faster zoom/pan speeds
_VERTICAL_KEN_BURNS = {
    # 0: zoom in center (1.0 -> 1.35) — 2.5x faster than before
    0: "zoompan=z='min(zoom+0.003,1.35)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # 1: zoom out center (1.35 -> 1.0)
    1: "zoompan=z='if(eq(on,1),1.35,max(zoom-0.003,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # 2: pan down with 1.25x zoom
    2: "zoompan=z='1.25':x='(iw/zoom-ow)/2':y='(ih/zoom-oh)/(FRAMES)*on'",
    # 3: pan up with 1.25x zoom
    3: "zoompan=z='1.25':x='(iw/zoom-ow)/2':y='(ih/zoom-oh)-((ih/zoom-oh)/(FRAMES))*on'",
    # 4: corner zoom top-left (1.0 -> 1.4)
    4: "zoompan=z='min(zoom+0.0035,1.4)':x='0':y='0'",
    # 5: corner zoom bottom-right (1.0 -> 1.4)
    5: "zoompan=z='min(zoom+0.0035,1.4)':x='iw/zoom-ow':y='ih/zoom-oh'",
    # 6: corner zoom top-right
    6: "zoompan=z='min(zoom+0.0035,1.35)':x='iw/zoom-ow':y='0'",
    # 7: corner zoom bottom-left
    7: "zoompan=z='min(zoom+0.0035,1.35)':x='0':y='ih/zoom-oh'",
    # 8: diagonal pan (top-left to bottom-right) with zoom
    8: "zoompan=z='min(zoom+0.002,1.3)':x='(iw/zoom-ow)/(FRAMES)*on':y='(ih/zoom-oh)/(FRAMES)*on'",
    # 9: diagonal pan (bottom-right to top-left) with zoom
    9: "zoompan=z='min(zoom+0.002,1.3)':x='(iw/zoom-ow)-((iw/zoom-ow)/(FRAMES))*on':y='(ih/zoom-oh)-((ih/zoom-oh)/(FRAMES))*on'",
    # 10: fast zoom in tight (1.0 -> 1.5) — dramatic punch
    10: "zoompan=z='min(zoom+0.005,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # 11: slow drift right with zoom
    11: "zoompan=z='min(zoom+0.002,1.25)':x='(iw/zoom-ow)/(FRAMES)*on':y='(ih/zoom-oh)/2'",
}


# ---------------------------------------------------------------------------
# 1. Script segment parsing
# ---------------------------------------------------------------------------

def parse_script_segments(script_path):
    """Parse a pipeline script into structured segments.

    Supports two heading formats:
        ## Section Name (M:SS-M:SS)          — shorts / simple scripts
        ## Chapter N: Title (M:SS-M:SS)      — long-form scripts

    Returns:
        list[dict]: Each dict has keys:
            - name (str):      Section/chapter name, e.g. "Hook" or "Chapter 1: ..."
            - start_sec (float): Start time in seconds
            - end_sec (float):   End time in seconds
            - text (str):        Narration text (no [VISUAL:] or [SOUND:] lines)
            - visuals (list[str]): Visual descriptions extracted from [VISUAL: ...] lines
    """
    with open(script_path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    # Strip YAML front-matter (--- ... ---)
    raw = re.sub(r"^---\s*\n.*?\n---\s*\n", "", raw, count=1, flags=re.DOTALL)
    # Strip leading ```markdown fence if present
    raw = re.sub(r"^```\s*markdown\s*\n", "", raw, count=1)
    raw = re.sub(r"\n```\s*$", "", raw, count=1)
    # Strip # header lines (channel/topic metadata)
    raw = re.sub(r"^#\s+(?:Channel|Topic|Format|Words|Est Duration|Generated):.*\n", "", raw, flags=re.MULTILINE)

    # Try multiple heading formats found across different script generators:
    # Format 1: ## Section Name (M:SS-M:SS)      — shorts / newer scripts
    # Format 2: **(Section Name - M:SS - M:SS)**  — long-form scripts
    heading_re = re.compile(
        r"^##\s+(.+?)\s+\((\d+):(\d{2})\s*-\s*(\d+):(\d{2})\)\s*$",
        re.MULTILINE,
    )
    headings = list(heading_re.finditer(raw))

    if not headings:
        # Format 2: **(Section Name - M:SS - M:SS)**
        heading_re = re.compile(
            r"^\*\*\((.+?)\s*-\s*(\d+):(\d{2})\s*-\s*(\d+):(\d{2})\)\*\*\s*$",
            re.MULTILINE,
        )
        headings = list(heading_re.finditer(raw))

    if not headings:
        # Format 3: [HH:MM:SS] [CHAPTER: Name] — used by EvaReyes, etc.
        chapter_re = re.compile(
            r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*\[CHAPTER:\s*(.+?)\]\s*$",
            re.MULTILINE,
        )
        chapters = list(chapter_re.finditer(raw))
        if chapters:
            segments = []
            for idx, match in enumerate(chapters):
                h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
                start_sec = h * 3600 + m * 60 + s
                # End = next chapter start, or start + 120s for last segment
                if idx + 1 < len(chapters):
                    nm = chapters[idx + 1]
                    end_sec = int(nm.group(1)) * 3600 + int(nm.group(2)) * 60 + int(nm.group(3))
                else:
                    end_sec = start_sec + 120

                body_start = match.end()
                body_end = chapters[idx + 1].start() if idx + 1 < len(chapters) else len(raw)
                body = raw[body_start:body_end].strip()

                narration_lines = []
                visuals = []
                for line in body.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # Strip timestamp prefixes [HH:MM:SS]
                    line = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*", "", line)
                    vis_matches = re.findall(r"\[VISUAL:\s*(.+?)\]", line)
                    if vis_matches:
                        visuals.extend(vis_matches)
                    cleaned = re.sub(r"\[VISUAL:\s*[^\]]*\]", "", line)
                    cleaned = re.sub(r"\[SOUND:\s*[^\]]*\]", "", cleaned)
                    # Strip emotion tags like [Firmly], [Excited], etc.
                    cleaned = re.sub(r"\[[A-Z][a-z]+(?:ly)?\]", "", cleaned)
                    cleaned = cleaned.strip()
                    if cleaned:
                        narration_lines.append(cleaned)

                segments.append({
                    "name": match.group(4).strip(),
                    "start_sec": float(start_sec),
                    "end_sec": float(end_sec),
                    "text": " ".join(narration_lines),
                    "visuals": visuals,
                })
            return segments

    if not headings:
        # Format 4: Auto-detect numbered sections (**N. Title**) or
        # (Transition to Story N: ...) and estimate timestamps from word count.
        # Also handles **NARRATOR:** prefixed scripts without explicit sections
        # by splitting on **N.** bold numbered patterns.

        # Try **N. Title** pattern (listicle scripts)
        section_re = re.compile(
            r"^\*\*\s*(\d+)\.\s+(.+?)\s*\*\*\s*$",
            re.MULTILINE,
        )
        sections = list(section_re.finditer(raw))

        # Try (Transition to Story N: Title card - "Name") pattern
        if not sections:
            section_re = re.compile(
                r"^\(Transition to (?:Story|Part|Section)\s+(\d+).*?(?:[:\-–]\s*(.+?))?\)\s*$",
                re.MULTILINE | re.IGNORECASE,
            )
            sections = list(section_re.finditer(raw))

        if sections:
            # Extract estimated duration from header if available
            dur_match = re.search(r"#\s*Est Duration:\s*(?:~?\s*)?(\d+)", raw)
            est_duration = int(dur_match.group(1)) * 60 if dur_match else 480  # default 8 min

            # Count total narration words to compute per-word duration
            total_words = 0
            section_data = []
            for idx, match in enumerate(sections):
                body_start = match.end()
                body_end = sections[idx + 1].start() if idx + 1 < len(sections) else len(raw)
                body = raw[body_start:body_end].strip()

                narration_lines = []
                visuals = []
                for line in body.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    vis_matches = re.findall(r"\[VISUAL:\s*(.+?)\]", line)
                    if vis_matches:
                        visuals.extend(vis_matches)
                    cleaned = re.sub(r"\[VISUAL:\s*[^\]]*\]", "", line)
                    cleaned = re.sub(r"\[SOUND:\s*[^\]]*\]", "", cleaned)
                    cleaned = re.sub(r"\*\*(?:NARRATOR|Narrator)\s*:\*\*\s*", "", cleaned)
                    cleaned = re.sub(r"\*\*", "", cleaned)
                    cleaned = re.sub(r"\(.*?\)", "", cleaned)  # strip directions
                    cleaned = cleaned.strip()
                    if cleaned and not cleaned.startswith("[") and not cleaned.startswith("("):
                        narration_lines.append(cleaned)

                text = " ".join(narration_lines)
                wc = len(text.split())
                total_words += wc

                name = match.group(2).strip() if match.group(2) else f"Section {match.group(1)}"
                # Clean up name
                name = re.sub(r'["\']', '', name)
                name = re.sub(r'\s*Title card\s*-?\s*', '', name, flags=re.IGNORECASE)
                name = name.strip(" -–:").strip()

                section_data.append({
                    "name": name,
                    "text": text,
                    "visuals": visuals,
                    "word_count": wc,
                })

            # Estimate timestamps proportionally from word count
            if total_words > 0:
                sec_per_word = est_duration / total_words
            else:
                sec_per_word = 0.5

            t = 0
            segments = []
            for sd in section_data:
                duration = sd["word_count"] * sec_per_word
                segments.append({
                    "name": sd["name"],
                    "start_sec": round(t, 1),
                    "end_sec": round(t + duration, 1),
                    "text": sd["text"],
                    "visuals": sd["visuals"],
                })
                t += duration
            return segments

        # Format 5: No sections at all — split into intro + chunks by paragraph
        # for scripts that are just continuous narration
        paragraphs = [p.strip() for p in re.split(r'\n\n+', raw) if p.strip()]
        narr_paras = []
        for p in paragraphs:
            if p.startswith("#") or p.startswith("```"):
                continue
            cleaned = re.sub(r"\[VISUAL:\s*[^\]]*\]", "", p)
            cleaned = re.sub(r"\[SOUND:\s*[^\]]*\]", "", cleaned)
            cleaned = re.sub(r"\*\*(?:NARRATOR|Narrator)\s*:\*\*\s*", "", cleaned)
            cleaned = re.sub(r"\*\*", "", cleaned)
            cleaned = re.sub(r"\(.*?\)", "", cleaned)
            cleaned = re.sub(r"\[.*?\]", "", cleaned)
            cleaned = cleaned.strip()
            if cleaned and len(cleaned.split()) > 10:
                narr_paras.append(cleaned)

        if len(narr_paras) >= 3:
            dur_match = re.search(r"#\s*Est Duration:\s*(?:~?\s*)?(\d+)", raw)
            est_duration = int(dur_match.group(1)) * 60 if dur_match else 480

            total_words = sum(len(p.split()) for p in narr_paras)
            if total_words > 0:
                sec_per_word = est_duration / total_words
            else:
                return []

            # Group paragraphs into ~60-90s segments
            segments = []
            chunk_text = ""
            chunk_start = 0.0
            chunk_words = 0
            chunk_idx = 0

            for p in narr_paras:
                wc = len(p.split())
                chunk_text += " " + p
                chunk_words += wc
                chunk_dur = chunk_words * sec_per_word

                if chunk_dur >= 60 or p == narr_paras[-1]:
                    end = chunk_start + chunk_dur
                    name = f"Segment {chunk_idx + 1}" if chunk_idx > 0 else "Intro"
                    # Use first sentence as name if possible
                    first_sent = chunk_text.strip().split(".")[0][:50]
                    if first_sent:
                        name = first_sent

                    segments.append({
                        "name": name,
                        "start_sec": round(chunk_start, 1),
                        "end_sec": round(end, 1),
                        "text": chunk_text.strip(),
                        "visuals": [],
                    })
                    chunk_start = end
                    chunk_text = ""
                    chunk_words = 0
                    chunk_idx += 1

            return segments

        return []

    segments = []
    for idx, match in enumerate(headings):
        name = match.group(1).strip()
        start_sec = int(match.group(2)) * 60 + int(match.group(3))
        end_sec = int(match.group(4)) * 60 + int(match.group(5))

        # Body = text between this heading and the next (or end of file)
        body_start = match.end()
        body_end = headings[idx + 1].start() if idx + 1 < len(headings) else len(raw)
        body = raw[body_start:body_end].strip()

        # Separate narration from visual/sound directions
        narration_lines = []
        visuals = []
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Extract [VISUAL: ...] descriptions
            vis_matches = re.findall(r"\[VISUAL:\s*(.+?)\]", line)
            if vis_matches:
                visuals.extend(vis_matches)
            # Extract [SOUND: ...] — skip these from narration
            sound_matches = re.findall(r"\[SOUND:\s*(.+?)\]", line)
            # Build narration: strip out [VISUAL:...], [SOUND:...], and narrator tags
            cleaned = re.sub(r"\[VISUAL:\s*[^\]]*\]", "", line)
            cleaned = re.sub(r"\[SOUND:\s*[^\]]*\]", "", cleaned)
            cleaned = re.sub(r"\*\*\(Narrator\):\*\*\s*", "", cleaned)
            cleaned = re.sub(r"\*\*", "", cleaned)  # strip bold markers
            cleaned = cleaned.strip()
            if cleaned:
                narration_lines.append(cleaned)

        segments.append({
            "name": name,
            "start_sec": float(start_sec),
            "end_sec": float(end_sec),
            "text": " ".join(narration_lines),
            "visuals": visuals,
        })

    return segments


# ---------------------------------------------------------------------------
# 2. Best clip selection
# ---------------------------------------------------------------------------

def find_best_clips(segments, max_duration=59, min_duration=15, retention_data=None):
    """Score segments for clip-worthiness and return ranked candidates.

    Scoring rubric:
        +5  Hook / intro segments
        +4  Self-contained segments (have opening text + conclusion cues)
        +3  Segments with strong visual markers
        +4  Optimal duration (20-50 s)
        +2  Acceptable duration (15-59 s)

    Adjacent segments that together fit under *max_duration* are also
    considered as a combined clip.

    Args:
        segments: List of segment dicts from ``parse_script_segments``.
        max_duration: Maximum clip length in seconds (default 59).
        min_duration: Minimum clip length in seconds (default 15).
        retention_data: Optional list of retention data dicts from YouTube Analytics,
            each with keys ``elapsed_pct`` (0-1) and ``watch_ratio``.

    Returns:
        list[dict]: Sorted by score (descending). Each dict has keys:
            - name (str)
            - start_sec (float)
            - end_sec (float)
            - score (int)
            - hook_text (str): First line of the segment's narration text
    """
    if not segments:
        return []

    def _score_single(seg):
        """Score an individual segment."""
        score = 0
        dur = seg["end_sec"] - seg["start_sec"]
        name_lower = seg["name"].lower()

        # Hook / intro boost
        if any(kw in name_lower for kw in ("hook", "intro", "opening")):
            score += 5

        # Self-contained: has text that starts and has some concluding language
        text_lower = seg["text"].lower()
        conclusion_cues = (
            "subscribe", "like", "comment", "follow", "remember",
            "so next time", "mind blown", "the answer", "that's why",
        )
        has_conclusion = any(cue in text_lower for cue in conclusion_cues)
        has_opening = len(seg["text"]) > 30
        if has_opening and has_conclusion:
            score += 4

        # Strong visual markers
        if len(seg["visuals"]) >= 2:
            score += 3

        # Duration scoring
        if 20 <= dur <= 50:
            score += 4
        elif min_duration <= dur <= max_duration:
            score += 2

        return score

    candidates = []

    # Score individual segments
    for seg in segments:
        dur = seg["end_sec"] - seg["start_sec"]
        if dur < min_duration or dur > max_duration:
            continue
        score = _score_single(seg)
        first_line = seg["text"].split(".")[0].strip() if seg["text"] else ""
        candidates.append({
            "name": seg["name"],
            "start_sec": seg["start_sec"],
            "end_sec": seg["end_sec"],
            "score": score,
            "hook_text": first_line,
        })

    # Consider combining adjacent segments
    for i in range(len(segments) - 1):
        combined_start = segments[i]["start_sec"]
        combined_end = segments[i + 1]["end_sec"]
        combined_dur = combined_end - combined_start
        if combined_dur < min_duration or combined_dur > max_duration:
            continue

        # Combined score: average of both + adjacency bonus
        score_a = _score_single(segments[i])
        score_b = _score_single(segments[i + 1])
        combined_score = max(score_a, score_b) + 1  # adjacency bonus

        # Duration scoring for the combined clip
        if 20 <= combined_dur <= 50:
            combined_score += 4
        elif min_duration <= combined_dur <= max_duration:
            combined_score += 2

        first_line = segments[i]["text"].split(".")[0].strip() if segments[i]["text"] else ""
        candidates.append({
            "name": f"{segments[i]['name']} + {segments[i + 1]['name']}",
            "start_sec": combined_start,
            "end_sec": combined_end,
            "score": combined_score,
            "hook_text": first_line,
        })

    # Boost/penalize based on retention data from YouTube Analytics
    if retention_data:
        # Find high-retention and low-retention regions
        sorted_retention = sorted(retention_data, key=lambda x: x.get("watch_ratio", 0))
        if len(sorted_retention) >= 5:
            top_20_threshold = sorted_retention[int(len(sorted_retention) * 0.8)].get("watch_ratio", 1)
            bottom_20_threshold = sorted_retention[int(len(sorted_retention) * 0.2)].get("watch_ratio", 0)
        else:
            top_20_threshold = 1.2
            bottom_20_threshold = 0.5

        for clip in candidates:
            # Map clip time range to retention data range (0-1)
            # retention data elapsed_pct is 0-1, clip times are in seconds
            # We need the source video duration — estimate from max segment end
            max_end = max(s.get("end_sec", 0) for s in segments) if segments else 1
            clip_start_pct = clip["start_sec"] / max_end if max_end > 0 else 0
            clip_end_pct = clip["end_sec"] / max_end if max_end > 0 else 0

            # Find retention data points within this clip's range
            clip_retention = [
                r for r in retention_data
                if clip_start_pct <= r.get("elapsed_pct", 0) <= clip_end_pct
            ]

            if clip_retention:
                avg_ratio = sum(r.get("watch_ratio", 0) for r in clip_retention) / len(clip_retention)
                if avg_ratio >= top_20_threshold:
                    clip["score"] += 6  # High retention bonus
                elif avg_ratio <= bottom_20_threshold:
                    clip["score"] -= 3  # Low retention penalty

    # Sort by score descending, then by start time ascending
    candidates.sort(key=lambda c: (-c["score"], c["start_sec"]))
    return candidates


# ---------------------------------------------------------------------------
# 3. Clip extraction
# ---------------------------------------------------------------------------

def extract_clip(source_video, start_sec, end_sec, output_path):
    """Extract a clip from a source video using ffmpeg.

    Tries stream-copy first for speed; falls back to re-encode on failure.

    Args:
        source_video: Path to the source video file.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.
        output_path: Destination path for the extracted clip.

    Returns:
        tuple: (success: bool, size_mb: float, duration_sec: float)
    """
    # Clamp end_sec to actual video duration to avoid extracting beyond EOF
    src_duration = _get_video_duration(source_video)
    if src_duration > 0 and end_sec > src_duration:
        end_sec = src_duration
    if src_duration > 0 and start_sec >= src_duration - 1:
        print(f"  [extract_clip] Start ({start_sec:.0f}s) is at or beyond video end ({src_duration:.0f}s)")
        return False, 0.0, 0.0

    duration = end_sec - start_sec
    if duration <= 0:
        print(f"  [extract_clip] Invalid duration: {start_sec}s - {end_sec}s")
        return False, 0.0, 0.0

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Attempt 1: stream copy (fast)
    cmd_copy = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", source_video,
        "-t", str(duration),
        "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    print(f"  [extract_clip] Extracting {duration:.1f}s clip (stream copy)...")
    result = subprocess.run(cmd_copy, capture_output=True, text=True)

    needs_reencode = False
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
        needs_reencode = True
    elif os.path.exists(output_path):
        # Check if stream copy extracted significantly less than expected
        actual_dur = _get_video_duration(output_path)
        if actual_dur < duration * 0.5:
            print(f"  [extract_clip] Stream copy too short ({actual_dur:.1f}s vs {duration:.1f}s target), re-encoding...")
            needs_reencode = True

    if needs_reencode:
        # Attempt 2: re-encode
        print(f"  [extract_clip] Stream copy failed, re-encoding...")
        if os.path.exists(output_path):
            os.remove(output_path)

        cmd_reencode = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", source_video,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-b:v", "2000k", "-maxrate", "2500k", "-bufsize", "5000k",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd_reencode, capture_output=True, text=True)

    if result.returncode == 0 and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        actual_dur = _get_video_duration(output_path)
        print(f"  [extract_clip] OK: {size_mb:.1f} MB, {actual_dur:.1f}s")
        return True, size_mb, actual_dur

    print(f"  [extract_clip] FAILED: {result.stderr[-300:] if result.stderr else 'unknown error'}")
    return False, 0.0, 0.0


# ---------------------------------------------------------------------------
# 4. Vertical crop
# ---------------------------------------------------------------------------

def crop_to_vertical(input_path, output_path, strategy="center"):
    """Crop a 16:9 video to 9:16 vertical format.

    Crop formula for center: crop=ih*9/16:ih:(iw-ih*9/16)/2:0, scale=1080:1920

    Args:
        input_path: Source video (expected 16:9).
        output_path: Destination for the cropped vertical video.
        strategy: One of "center", "left_third", "right_third".

    Returns:
        bool: True on success.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Compute horizontal offset based on strategy
    if strategy == "left_third":
        x_expr = "0"
    elif strategy == "right_third":
        x_expr = "(iw-ih*9/16)"
    else:
        # center (default)
        x_expr = "(iw-ih*9/16)/2"

    crop_filter = f"crop=ih*9/16:ih:{x_expr}:0,scale={VERTICAL_WIDTH}:{VERTICAL_HEIGHT}"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", crop_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-b:v", "2000k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]

    print(f"  [crop_to_vertical] Cropping with strategy='{strategy}'...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0 and os.path.exists(output_path):
        size_bytes = os.path.getsize(output_path)
        size_mb = size_bytes / (1024 * 1024)
        if size_bytes < 10240:  # < 10KB is essentially empty
            print(f"  [crop_to_vertical] FAILED: output too small ({size_bytes} bytes)")
            return False
        print(f"  [crop_to_vertical] OK: {size_mb:.1f} MB")
        return True

    print(f"  [crop_to_vertical] FAILED: {result.stderr[-300:] if result.stderr else 'unknown error'}")
    return False


# ---------------------------------------------------------------------------
# 5. Hook text overlay (Pillow pipe compositing — no drawtext filter)
# ---------------------------------------------------------------------------

def add_hook_overlay(video_path, output_path, hook_text, duration=2.5):
    """Overlay hook text on the first *duration* seconds of a video.

    Because this system's ffmpeg lacks the drawtext and subtitles filters,
    we use a pipe-based approach:
        1. Probe video dimensions and fps with ffprobe.
        2. Decode frames as raw RGBA via ffmpeg pipe.
        3. For frames within the overlay window, composite text with Pillow.
        4. Pipe modified frames back to an ffmpeg encoder.
        5. Mux audio from the original video.

    The hook text is rendered as:
        - Large bold font (~64px), white with 3px black outline
        - Centered horizontally, ~15% from the top
        - Semi-transparent dark background bar behind text
        - Word-wrapped if too wide

    Args:
        video_path: Input video path.
        output_path: Output video path.
        hook_text: The hook text to overlay.
        duration: How many seconds to show the overlay (default 2.5).

    Returns:
        bool: True on success.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  [add_hook_overlay] Pillow not installed — skipping overlay")
        return False

    if not hook_text or not hook_text.strip():
        print("  [add_hook_overlay] Empty hook text — skipping")
        shutil.copy2(video_path, output_path)
        return True

    # --- Step 1: Probe video info ---
    width, height, fps, total_duration = _probe_video(video_path)
    if width == 0 or height == 0:
        print("  [add_hook_overlay] Could not probe video dimensions")
        return False

    overlay_frames = int(fps * duration)
    total_frames = int(fps * total_duration)
    frame_size = width * height * 4  # RGBA

    print(f"  [add_hook_overlay] {width}x{height} @ {fps}fps, "
          f"overlay on first {overlay_frames} frames ({duration}s)")

    # --- Step 2: Prepare the text overlay image ---
    overlay_img = _render_hook_text_image(hook_text, width, height)

    # --- Step 3: Set up ffmpeg decode pipe (video -> raw RGBA) ---
    decode_cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-v", "quiet",
        "pipe:1",
    ]

    # --- Step 4: Set up ffmpeg encode pipe (raw RGBA -> video, no audio) ---
    temp_dir = tempfile.mkdtemp(prefix="shorts_overlay_")
    temp_video = os.path.join(temp_dir, "video_only.mp4")

    encode_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-v", "quiet",
        temp_video,
    ]

    try:
        decoder = subprocess.Popen(
            decode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        encoder = subprocess.Popen(
            encode_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        frame_idx = 0
        while True:
            raw_frame = decoder.stdout.read(frame_size)
            if not raw_frame or len(raw_frame) < frame_size:
                break

            if frame_idx < overlay_frames:
                # Composite overlay onto frame
                frame_img = Image.frombytes("RGBA", (width, height), raw_frame)
                frame_img = Image.alpha_composite(frame_img, overlay_img)
                encoder.stdin.write(frame_img.tobytes())
            else:
                encoder.stdin.write(raw_frame)

            frame_idx += 1

        decoder.stdout.close()
        encoder.stdin.close()
        decoder.wait()
        encoder.wait()

        if encoder.returncode != 0:
            print(f"  [add_hook_overlay] Encoder failed (rc={encoder.returncode})")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

        # --- Step 5: Mux audio from original ---
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        mux_cmd = [
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", video_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0?",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]
        mux_result = subprocess.run(mux_cmd, capture_output=True, text=True)

        if mux_result.returncode == 0 and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  [add_hook_overlay] OK: {size_mb:.1f} MB")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return True

        print(f"  [add_hook_overlay] Mux failed: "
              f"{mux_result.stderr[-300:] if mux_result.stderr else 'unknown'}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    except Exception as exc:
        print(f"  [add_hook_overlay] Exception: {exc}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False


def _probe_video(video_path):
    """Return (width, height, fps, duration) for a video file via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0, 0, 0, 0

    import json
    info = json.loads(result.stdout)
    stream = info.get("streams", [{}])[0]
    fmt = info.get("format", {})

    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    duration = float(fmt.get("duration", 0))

    # Parse frame rate (may be "30/1" or "30000/1001")
    fps_str = stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 30.0

    return width, height, fps, duration


def _render_hook_text_image(hook_text, width, height):
    """Render the hook text as an RGBA overlay image.

    Text properties:
        - White, ~64px bold, 3px black outline
        - Centered horizontally, ~15% from top
        - Semi-transparent dark bar behind the text
        - Word-wrapped to ~80% of frame width
    """
    from PIL import Image, ImageDraw, ImageFont

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Try to load a bold system font; fall back to default
    font_size = max(48, int(height * 0.042))  # ~80px at 1920h (was 64px)
    font = _load_font(font_size)

    # Word-wrap to ~80% of frame width
    max_text_width = int(width * 0.80)
    lines = _word_wrap(draw, hook_text, font, max_text_width)

    # Measure total text block height
    line_spacing = int(font_size * 0.3)
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        line_widths.append(lw)
        line_heights.append(lh)

    total_text_h = sum(line_heights) + line_spacing * (len(lines) - 1)

    # Position: centered horizontally, ~15% from top
    y_start = int(height * 0.15)
    padding_x = int(width * 0.05)
    padding_y = int(font_size * 0.5)

    # Draw semi-transparent background bar
    bar_top = y_start - padding_y
    bar_bottom = y_start + total_text_h + padding_y
    bar_left = 0
    bar_right = width
    draw.rectangle(
        [(bar_left, bar_top), (bar_right, bar_bottom)],
        fill=(0, 0, 0, 140),  # ~55% opacity black
    )

    # Draw each line of text with outline
    outline_width = 3
    y_cursor = y_start
    for i, line in enumerate(lines):
        lw = line_widths[i]
        x = (width - lw) // 2

        # Black outline (draw text shifted in 8 directions)
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y_cursor + dy), line, font=font, fill=(0, 0, 0, 255))

        # White text on top
        draw.text((x, y_cursor), line, font=font, fill=(255, 255, 255, 255))

        y_cursor += line_heights[i] + line_spacing

    return overlay


def _load_font(size):
    """Try to load a bold TrueType font; fall back to Pillow default."""
    from PIL import ImageFont

    # Common bold font paths on macOS and Linux
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFCompact.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    # Pillow's built-in bitmap font (limited but always available)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow versions don't accept size kwarg
        return ImageFont.load_default()


def _word_wrap(draw, text, font, max_width):
    """Break *text* into lines that fit within *max_width* pixels."""
    words = text.split()
    if not words:
        return [text]

    lines = []
    current = words[0]

    for word in words[1:]:
        test = f"{current} {word}"
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# 6. Vertical Ken Burns assembly
# ---------------------------------------------------------------------------

def assemble_vertical_video(audio_path, broll_dir, output_path,
                            segment_duration=4, crossfade=0.3, verbose=True):
    """Assemble a vertical (9:16) video from B-roll images and voiceover.

    Like ``assembly.assemble_video`` but optimised for shorts:
        - Output is 1080x1920 (vertical) instead of 1920x1080
        - Uses vertical Ken Burns presets (pan up/down, faster zoom)
        - Shorter default segment duration (4 s) and crossfade (0.3 s)
        - Images scaled to fill vertical frame: scale=-1:2560 then zoompan

    Args:
        audio_path: Path to voiceover audio file.
        broll_dir: Directory containing broll_01.png, broll_02.png, etc.
        output_path: Output MP4 path.
        segment_duration: Seconds per B-roll image (default 4).
        crossfade: Crossfade between segments in seconds (default 0.3, 0 to disable).
        verbose: Print progress messages.

    Returns:
        tuple: (success: bool, size_mb: float, duration: float)
    """
    duration = get_audio_duration(audio_path)
    if verbose:
        print(f"  [vertical] Audio duration: {duration:.1f}s ({duration / 60:.1f} min)")

    images = sorted([
        os.path.join(broll_dir, f) for f in os.listdir(broll_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg")) and f.startswith("broll_")
    ])

    if not images:
        if verbose:
            print("  [vertical] No B-roll images found")
        return False, 0, 0

    if verbose:
        print(f"  [vertical] B-roll images: {len(images)}")

    # Build segments
    num_segments = int(math.ceil(duration / segment_duration))
    temp_dir = os.path.join(os.path.dirname(output_path), "temp_vertical_segments")
    os.makedirs(temp_dir, exist_ok=True)

    segment_files = []
    fps = VERTICAL_FPS

    for i in range(num_segments):
        start = i * segment_duration
        seg_dur = min(segment_duration, duration - start)
        if seg_dur < 0.5:
            break

        seg_file = os.path.join(temp_dir, f"vseg_{i:04d}.mp4")
        segment_files.append(seg_file)

        if os.path.exists(seg_file):
            if verbose:
                print(f"    [{i + 1}/{num_segments}] SKIP (exists)")
            continue

        img_idx = i % len(images)
        effect_idx = i % len(_VERTICAL_KEN_BURNS)

        if verbose:
            print(f"    [{i + 1}/{num_segments}] {os.path.basename(images[img_idx])} "
                  f"(effect {effect_idx}, {seg_dur:.1f}s)")

        if not _build_vertical_segment(images[img_idx], seg_dur, effect_idx, seg_file, fps):
            if verbose:
                print(f"    Segment {i} failed")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, 0, 0

    if not segment_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    # Concatenate with optional crossfade (reuses assembly.py patterns)
    if crossfade > 0 and len(segment_files) > 1:
        concat_output = _vconcat_with_crossfade(segment_files, temp_dir, crossfade, verbose)
    else:
        concat_output = _vconcat_simple(segment_files, temp_dir)

    if not concat_output or not os.path.exists(concat_output):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    if verbose:
        print("  [vertical] Adding audio track...")

    # Merge audio + video (same pattern as assembly.py)
    cmd = [
        "ffmpeg", "-y",
        "-i", concat_output, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    shutil.rmtree(temp_dir, ignore_errors=True)

    if result.returncode == 0 and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if verbose:
            print(f"  [vertical] Video: {size_mb:.1f} MB, {duration:.1f}s")
        return True, size_mb, duration

    if verbose:
        print(f"  [vertical] Final merge failed: "
              f"{result.stderr[-300:] if result.stderr else 'unknown'}")
    return False, 0, 0


def _build_vertical_segment(img_path, seg_duration, effect_idx, output_path, fps=30):
    """Build a single vertical Ken Burns segment MP4 from an image.

    Images are first scaled to fill the vertical frame (scale=-1:2560 gives
    enough headroom for zoom/pan), then the zoompan filter outputs 1080x1920.
    """
    total_frames = int(seg_duration * fps)
    effect_str = _VERTICAL_KEN_BURNS[effect_idx].replace("FRAMES", str(total_frames))
    filter_str = (
        f"scale=-1:2560,"
        f"{effect_str}:d={total_frames}:s={VERTICAL_WIDTH}x{VERTICAL_HEIGHT}:fps={fps},"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
        "-vf", filter_str,
        "-t", str(seg_duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-b:v", "2000k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _vconcat_simple(segment_files, temp_dir):
    """Concatenate vertical segments without transitions.

    Mirrors ``assembly._concat_simple``.
    """
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in segment_files:
            f.write(f"file '{os.path.abspath(sf)}'\n")

    concat_output = os.path.join(temp_dir, "video_only.mp4")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-b:v", "2000k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-pix_fmt", "yuv420p", concat_output,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return concat_output if result.returncode == 0 else None


def _vconcat_with_crossfade(segment_files, temp_dir, crossfade_dur, verbose=True):
    """Concatenate vertical segments with crossfade transitions.

    Mirrors ``assembly._concat_with_crossfade``, with batching for large
    segment counts.  Falls back to simple concat on failure.
    """
    if verbose:
        print(f"  [vertical] Applying {crossfade_dur}s crossfade transitions...")

    # Batch for large segment counts (same threshold as assembly.py)
    if len(segment_files) > 20:
        return _vconcat_batched_crossfade(segment_files, temp_dir, crossfade_dur, verbose)

    # Build xfade filter chain
    inputs = []
    for sf in segment_files:
        inputs.extend(["-i", sf])

    filter_parts = []
    current_label = "[0:v]"

    for i in range(1, len(segment_files)):
        out_label = f"[v{i}]" if i < len(segment_files) - 1 else "[outv]"

        if i == 1:
            seg_dur = _get_video_duration(segment_files[0])
            offset = seg_dur - crossfade_dur
        else:
            accumulated = sum(
                _get_video_duration(segment_files[j]) for j in range(i)
            ) - (i - 1) * crossfade_dur
            offset = accumulated - crossfade_dur

        filter_parts.append(
            f"{current_label}[{i}:v]xfade=transition=fade:"
            f"duration={crossfade_dur}:offset={max(0, offset)}{out_label}"
        )
        current_label = out_label

    filter_complex = ";".join(filter_parts)
    concat_output = os.path.join(temp_dir, "video_only.mp4")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        concat_output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if verbose:
            print("  [vertical] Crossfade failed, falling back to simple concat")
        return _vconcat_simple(segment_files, temp_dir)

    return concat_output


def _vconcat_batched_crossfade(segment_files, temp_dir, crossfade_dur, verbose=True):
    """Process crossfades in batches for large segment counts.

    Mirrors ``assembly._concat_batched_crossfade``.
    """
    batch_size = 10
    batch_outputs = []

    for batch_start in range(0, len(segment_files), batch_size):
        batch = segment_files[batch_start:batch_start + batch_size]
        batch_output = os.path.join(temp_dir, f"vbatch_{batch_start:04d}.mp4")

        if len(batch) == 1:
            batch_outputs.append(batch[0])
            continue

        result = _vconcat_with_crossfade(batch, temp_dir, crossfade_dur, verbose=False)
        if result:
            if os.path.exists(result) and result != batch_output:
                os.rename(result, batch_output)
                batch_outputs.append(batch_output)
            else:
                batch_outputs.append(result)
        else:
            batch_outputs.extend(batch)

    if len(batch_outputs) > 1:
        return _vconcat_simple(batch_outputs, temp_dir)
    return batch_outputs[0] if batch_outputs else None


# ---------------------------------------------------------------------------
# 7. Shorts title
# ---------------------------------------------------------------------------

def make_shorts_title(video_name, channel=None, platform="youtube"):
    """Generate a clean, title-cased shorts title.

    Args:
        video_name: Raw video name or filename (underscores will be replaced).
        channel: Optional channel name (unused in title, reserved for future).
        platform: Target platform ("youtube", "tiktok", "instagram").

    Returns:
        str: Cleaned title, max 100 characters. " #Shorts" appended for YouTube
             if there is room.
    """
    # Clean the name
    name = os.path.splitext(os.path.basename(video_name))[0]
    name = strip_timestamp(name)

    # Remove channel prefix if present (e.g. "CumquatShortform_Title" -> "Title")
    parts = name.split("_", 1)
    if len(parts) == 2 and not parts[0][0].isdigit():
        # Heuristic: if first segment looks like a channel name (CamelCase, no spaces)
        if parts[0] != parts[0].upper() and parts[0] != parts[0].lower():
            name = parts[1]

    # Replace underscores with spaces, collapse whitespace
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name).strip()

    # Title-case (preserve existing all-caps words like "AI", "NASA")
    words = name.split()
    title_words = []
    for word in words:
        if word.isupper() and len(word) > 1:
            title_words.append(word)  # Keep acronyms
        elif word.startswith("#"):
            title_words.append(word)  # Keep hashtags
        else:
            title_words.append(word.capitalize())
    name = " ".join(title_words)

    # Strip format suffixes like "shorts_facts", "shorts_story"
    name = re.sub(r"\s*shorts[_ ]?(facts|story|clip|highlight)\s*$", "", name, flags=re.IGNORECASE)

    # Platform-specific suffix
    shorts_tag = " #Shorts" if platform == "youtube" else ""

    # Enforce 100-character limit
    max_base = 100 - len(shorts_tag)
    if len(name) > max_base:
        name = name[:max_base - 3].rstrip() + "..."

    return f"{name}{shorts_tag}"


# ---------------------------------------------------------------------------
# 8. Shorts description
# ---------------------------------------------------------------------------

def make_shorts_description(channel, title, platform="youtube"):
    """Generate a short description for a Shorts upload.

    Keeps it to 2-3 lines: hook sentence, CTA, and AI disclosure.

    Args:
        channel: Channel name (used in CTA).
        title: The video title (hook line derived from it).
        platform: "youtube", "tiktok", or "instagram".

    Returns:
        str: Multi-line description string.
    """
    # Clean title for the hook (remove #Shorts tag and ellipsis)
    hook = re.sub(r"\s*#\w+", "", title).rstrip(".!? ").strip()
    if hook and not hook[-1] in ".!?":
        hook += "!"

    if platform == "youtube":
        cta = f"Subscribe to {channel} for more!" if channel else "Subscribe for more!"
        lines = [
            hook,
            "",
            cta,
            "",
            "---",
            "This video was produced with the assistance of AI tools (script, visuals, voiceover).",
        ]
    elif platform == "tiktok":
        cta = f"Follow @{channel.replace(' ', '')} for more!" if channel else "Follow for more!"
        lines = [
            hook,
            "",
            cta,
            "",
            "AI-assisted production.",
        ]
    else:
        # Instagram / generic
        cta = f"Follow {channel} for more!" if channel else "Follow for more!"
        lines = [
            hook,
            "",
            cta,
            "",
            "AI-assisted production.",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 9. Shorts tags
# ---------------------------------------------------------------------------

def make_shorts_tags(channel, title, platform="youtube"):
    """Generate platform-appropriate tags for a Shorts upload.

    Always includes "Shorts" for YouTube. Extracts keywords from the title
    and adds channel-specific tags.

    Args:
        channel: Channel name.
        title: Video title.
        platform: "youtube", "tiktok", or "instagram".

    Returns:
        list[str]: Tag strings (max 13 for YouTube to match Etsy pattern,
                   max 30 for TikTok/Instagram).
    """
    tags = []

    # Platform tag
    if platform == "youtube":
        tags.append("Shorts")
        tags.append("YouTube Shorts")
    elif platform == "tiktok":
        tags.append("fyp")
        tags.append("foryoupage")
    elif platform == "instagram":
        tags.append("Reels")
        tags.append("IGReels")

    # Channel tag
    if channel:
        clean_channel = channel.replace(" ", "")
        tags.append(clean_channel)

    # Extract keywords from title (words > 3 chars, not common stop words)
    stop_words = {
        "the", "and", "for", "you", "that", "this", "with", "from",
        "will", "your", "have", "about", "more", "than", "them",
        "into", "when", "what", "were", "been", "most", "also",
        "shorts", "short",
    }
    title_clean = re.sub(r"#\w+", "", title)  # Remove hashtags
    title_words = re.findall(r"[A-Za-z]{4,}", title_clean)
    for word in title_words:
        tag = word.capitalize()
        if tag.lower() not in stop_words and tag not in tags:
            tags.append(tag)

    # Platform-specific limits
    max_tags = 13 if platform == "youtube" else 30
    return tags[:max_tags]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_video_duration(video_path):
    """Get video file duration using ffprobe.

    Same pattern as ``assembly._get_video_duration``.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 4.0  # Default to segment_duration for shorts


# ---------------------------------------------------------------------------
# 10. Text-card shorts engine
# ---------------------------------------------------------------------------

def _get_system_font(size, bold=False):
    """Load a system font, preferring SF Pro > Helvetica > Arial."""
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/SFPro-Bold.otf" if bold
        else "/System/Library/Fonts/SFPro-Regular.otf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text_lines(text, font, max_width, draw):
    """Word-wrap *text* so each line fits within *max_width* pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _build_gradient_bg(width, height, top_color, bottom_color):
    """Create a vertical linear-gradient PIL Image (fast, row-based)."""
    from PIL import Image

    img = Image.new("RGB", (width, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        row = bytes([r, g, b] * width)
        img.paste(Image.frombytes("RGB", (width, 1), row), (0, y))
    return img


def _render_card_frame(width, height, texts, opacity=255,
                       bg_top=(16, 25, 34), bg_bottom=(10, 16, 24),
                       accent_color=(232, 148, 31), cached_bg=None):
    """Render a single text-card frame with gradient bg and accent bar.

    Args:
        width, height: Frame dimensions.
        texts: list of (text, font_size, color, bold) tuples.
        opacity: 0-255, applied to text for fade-in animation.
        bg_top, bg_bottom: Gradient colours (RGB tuples).
        accent_color: Thin accent bar colour.
        cached_bg: Pre-built gradient Image to avoid re-rendering.

    Returns:
        PIL.Image in RGB mode.
    """
    from PIL import Image, ImageDraw, ImageFilter

    bg = cached_bg.copy() if cached_bg else _build_gradient_bg(width, height, bg_top, bg_bottom)
    draw = ImageDraw.Draw(bg)

    # Accent bar — thin horizontal line at top
    bar_h = 4
    draw.rectangle([(0, 0), (width, bar_h)], fill=accent_color)

    # Calculate total content height for vertical centering
    elements = []
    total_h = 0
    padding = 80  # horizontal padding each side
    gap = 36  # vertical gap between text blocks

    for text, size, color, bold in texts:
        font = _get_system_font(size, bold)
        lines = _wrap_text_lines(text, font, width - padding * 2, draw)
        line_h = size + 12
        block_h = line_h * len(lines)
        elements.append((lines, font, color, line_h, size))
        total_h += block_h + gap

    total_h -= gap  # Remove last gap

    # Render text with opacity (compose via alpha layer)
    if opacity < 255:
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
    else:
        overlay = None
        odraw = draw

    y = (height - total_h) // 2

    for lines, font, color, line_h, fsize in elements:
        # Glow effect for accent-coloured or highlighted text
        is_highlight = color == accent_color or color in (
            (255, 215, 0), (0, 230, 118), (255, 80, 80),
        )

        for line in lines:
            bbox = odraw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (width - text_w) // 2

            fill = (*color, opacity) if overlay else color

            # Glow: draw blurred shadow behind highlighted text
            if is_highlight and overlay:
                glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                gdraw = ImageDraw.Draw(glow_layer)
                glow_alpha = max(30, opacity // 3)
                gdraw.text((x, y), line, fill=(*color, glow_alpha), font=font)
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=12))
                overlay = Image.alpha_composite(overlay, glow_layer)
                odraw = ImageDraw.Draw(overlay)

            if overlay:
                # Black outline for readability
                for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                    odraw.text((x + dx, y + dy), line,
                               fill=(0, 0, 0, opacity), font=font)
                odraw.text((x, y), line, fill=fill, font=font)
            else:
                for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                    odraw.text((x + dx, y + dy), line,
                               fill=(0, 0, 0), font=font)
                odraw.text((x, y), line, fill=fill, font=font)
            y += line_h
        y += gap

    if overlay:
        bg = bg.convert("RGBA")
        bg = Image.alpha_composite(bg, overlay)
        bg = bg.convert("RGB")

    return bg


def _generate_whoosh_sfx(output_path, duration=0.3):
    """Generate a whoosh sweep SFX using ffmpeg's sine audio source."""
    # Descending sine sweep 800Hz -> 200Hz with fast fade-out
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", (f"sine=frequency=800:duration={duration},"
               f"asetrate=44100,atempo=1,"
               f"afade=t=out:st=0:d={duration}"),
        "-c:a", "aac", "-b:a", "128k", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path)


def _generate_impact_sfx(output_path, duration=0.25):
    """Generate a bass impact hit using ffmpeg's sine audio source."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", (f"sine=frequency=60:duration={duration},"
               f"afade=t=out:st=0.05:d={duration - 0.05}"),
        "-c:a", "aac", "-b:a", "128k", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path)


def produce_text_short(audio_path, text_cards, output_path,
                       channel=None, bg_music_path=None, sfx=True,
                       fps=30, crossfade_dur=0.4, fade_in_frames=15,
                       bg_top=(16, 25, 34), bg_bottom=(10, 16, 24),
                       accent_color=(232, 148, 31)):
    """Produce a polished text-card short with animations, SFX, and transitions.

    Args:
        audio_path: Path to voiceover audio clip.
        text_cards: list of dicts, each with:
            - duration (float): seconds this card is shown
            - texts: list of (text, font_size, color_rgb, bold) tuples
            - impact (bool, optional): if True, add bass impact SFX
        output_path: Output MP4 path.
        channel: Channel name (for brand config lookup).
        bg_music_path: Optional background music (mixed at 15% volume).
        sfx: If True, add whoosh on transitions and impact on reveals.
        fps: Frame rate (default 30).
        crossfade_dur: Crossfade between cards in seconds (default 0.4).
        fade_in_frames: Number of frames for text fade-in (default 15 = 0.5s).
        bg_top, bg_bottom: Gradient background colours.
        accent_color: Brand accent colour for bar and glow.

    Returns:
        tuple: (success: bool, size_mb: float, duration_sec: float)
    """
    from PIL import Image

    tmp = tempfile.mkdtemp(prefix="textshort_")
    w, h = VERTICAL_WIDTH, VERTICAL_HEIGHT

    try:
        # ── Step 1: Render each card as a video segment ──
        card_videos = []
        card_has_impact = []

        # Pre-render a single gradient background and reuse it
        gradient_bg = _build_gradient_bg(w, h, bg_top, bg_bottom)

        for ci, card in enumerate(text_cards):
            card_dur = card["duration"]
            texts = card["texts"]
            has_impact = card.get("impact", False)
            card_has_impact.append(has_impact)

            # Strategy: render only fade-in frames as PNGs, then hold
            # the final frame for the remaining duration via ffmpeg.
            fade_dur = fade_in_frames / fps  # seconds of fade-in
            hold_dur = card_dur - fade_dur

            frames_dir = os.path.join(tmp, f"card_{ci:02d}_frames")
            os.makedirs(frames_dir)

            # Render fade-in frames (only ~15 frames, not 150+)
            for fi in range(fade_in_frames):
                opacity = int(255 * (fi / fade_in_frames))
                frame = _render_card_frame(
                    w, h, texts, opacity=opacity,
                    bg_top=bg_top, bg_bottom=bg_bottom,
                    accent_color=accent_color,
                    cached_bg=gradient_bg,
                )
                frame.save(os.path.join(frames_dir, f"frame_{fi:05d}.png"))

            # Render one full-opacity frame
            full_frame_path = os.path.join(frames_dir, "full.png")
            full_frame = _render_card_frame(
                w, h, texts, opacity=255,
                bg_top=bg_top, bg_bottom=bg_bottom,
                accent_color=accent_color,
                cached_bg=gradient_bg,
            )
            full_frame.save(full_frame_path)

            # Build card video: fade-in sequence + held full frame
            fade_vid = os.path.join(tmp, f"card_{ci:02d}_fade.mp4")
            cmd = [
                "ffmpeg", "-y", "-framerate", str(fps),
                "-i", os.path.join(frames_dir, "frame_%05d.png"),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", fade_vid,
            ]
            subprocess.run(cmd, capture_output=True, text=True)

            hold_vid = os.path.join(tmp, f"card_{ci:02d}_hold.mp4")
            cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", full_frame_path,
                "-t", str(max(hold_dur, 0.1)),
                "-vf", f"fps={fps},format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                hold_vid,
            ]
            subprocess.run(cmd, capture_output=True, text=True)

            # Concat fade + hold
            card_vid = os.path.join(tmp, f"card_{ci:02d}.mp4")
            concat_file = os.path.join(tmp, f"card_{ci:02d}_concat.txt")
            with open(concat_file, "w") as cf:
                cf.write(f"file '{fade_vid}'\nfile '{hold_vid}'\n")
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file, "-c", "copy", card_vid,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  [text_short] Card {ci} encoding failed")
                return False, 0, 0
            card_videos.append(card_vid)

            # Clean up frames
            shutil.rmtree(frames_dir)

        print(f"  [text_short] Rendered {len(card_videos)} animated cards")

        # ── Step 2: Join cards with crossfade transitions ──
        if len(card_videos) > 1 and crossfade_dur > 0:
            visual_path = _vconcat_with_crossfade(
                card_videos, tmp, crossfade_dur, verbose=False)
        else:
            visual_path = _vconcat_simple(card_videos, tmp)

        if not visual_path or not os.path.exists(visual_path):
            print("  [text_short] Card concatenation failed")
            return False, 0, 0

        print(f"  [text_short] Cards joined with {crossfade_dur}s crossfade")

        # ── Step 3: Build audio mix (voice + SFX + bg music) ──
        audio_duration = _get_video_duration(audio_path)
        mixed_audio = os.path.join(tmp, "mixed_audio.wav")

        # Start with the voiceover
        filter_inputs = ["-i", audio_path]
        filter_parts = []
        input_idx = 1  # [0] is voiceover

        # Generate and mix SFX
        if sfx:
            whoosh_path = os.path.join(tmp, "whoosh.m4a")
            impact_path = os.path.join(tmp, "impact.m4a")
            _generate_whoosh_sfx(whoosh_path, duration=0.3)
            _generate_impact_sfx(impact_path, duration=0.25)

            # Calculate transition timestamps (where each card ends)
            sfx_events = []
            t = 0
            for ci, card in enumerate(text_cards):
                card_end = t + card["duration"]
                if ci < len(text_cards) - 1:
                    # Whoosh at each transition point
                    sfx_events.append(("whoosh", card_end - crossfade_dur / 2))
                if card_has_impact[ci]:
                    # Impact 0.5s after card starts (after fade-in)
                    sfx_events.append(("impact", t + 0.5))
                t = card_end

            # Add each SFX as a delayed input
            for sfx_type, timestamp in sfx_events:
                sfx_file = whoosh_path if sfx_type == "whoosh" else impact_path
                if os.path.exists(sfx_file):
                    filter_inputs.extend(["-i", sfx_file])
                    vol = "0.4" if sfx_type == "whoosh" else "0.6"
                    filter_parts.append(
                        f"[{input_idx}:a]volume={vol},"
                        f"adelay={int(timestamp * 1000)}|{int(timestamp * 1000)}[sfx{input_idx}]"
                    )
                    input_idx += 1

        # Background music
        if bg_music_path and os.path.exists(bg_music_path):
            filter_inputs.extend(["-i", bg_music_path])
            # Trim to audio duration, set volume to 15%, fade in/out
            filter_parts.append(
                f"[{input_idx}:a]volume=0.15,"
                f"afade=t=in:st=0:d=2,"
                f"afade=t=out:st={max(0, audio_duration - 3)}:d=3,"
                f"atrim=0:{audio_duration}[bgm]"
            )
            input_idx += 1

        # Build the amix filter
        if filter_parts:
            # Label the voiceover
            mix_inputs = ["[0:a]"]
            for part in filter_parts:
                label = part.split("]")[-1] if part.endswith("]") else None
                # Extract the output label
                out_label = part.rsplit("[", 1)[-1].rstrip("]")
                mix_inputs.append(f"[{out_label}]")

            all_filters = ";".join(filter_parts)
            mix_count = len(mix_inputs)
            all_filters += f";{''.join(mix_inputs)}amix=inputs={mix_count}:duration=first:dropout_transition=0[aout]"

            cmd = [
                "ffmpeg", "-y",
                *filter_inputs,
                "-filter_complex", all_filters,
                "-map", "[aout]",
                "-c:a", "pcm_s16le", "-ar", "44100",
                mixed_audio,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  [text_short] Audio mix failed, using raw voiceover")
                mixed_audio = audio_path
            else:
                print(f"  [text_short] Audio mixed ({len(sfx_events) if sfx else 0} SFX"
                      f"{', bg music' if bg_music_path else ''})")
        else:
            mixed_audio = audio_path

        # ── Step 4: Merge visual + audio ──
        cmd = [
            "ffmpeg", "-y",
            "-i", visual_path, "-i", mixed_audio,
            "-t", str(audio_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0 and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  [text_short] OK: {size_mb:.1f} MB, {audio_duration:.1f}s")
            return True, size_mb, audio_duration

        print(f"  [text_short] Final merge failed: "
              f"{result.stderr[-300:] if result.stderr else 'unknown'}")
        return False, 0, 0

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
