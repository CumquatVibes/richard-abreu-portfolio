"""Video assembly with Ken Burns effects and crossfade transitions.

Shared module used by batch_produce.py, overnight_produce.py, and assemble_video.py.
"""

import math
import os
import shutil
import subprocess

# Ken Burns effect presets — 6 effects cycled through segments
KEN_BURNS_EFFECTS = {
    0: "zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    1: "zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    2: "zoompan=z='1.08':x='(iw/zoom-ow)/(FRAMES)*on':y='(ih-oh)/2'",
    3: "zoompan=z='1.08':x='(iw/zoom-ow)-((iw/zoom-ow)/(FRAMES))*on':y='(ih-oh)/2'",
    4: "zoompan=z='min(zoom+0.001,1.2)':x='0':y='0'",
    5: "zoompan=z='min(zoom+0.001,1.2)':x='iw/zoom-ow':y='ih/zoom-oh'",
}


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def _build_segment(img_path, seg_duration, effect_idx, output_path, fps=30):
    """Build a single Ken Burns segment MP4 from an image."""
    total_frames = int(seg_duration * fps)
    effect_str = KEN_BURNS_EFFECTS[effect_idx].replace("FRAMES", str(total_frames))
    filter_str = f"scale=2560:-1,{effect_str}:d={total_frames}:s=1920x1080:fps={fps},format=yuv420p"

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
        "-vf", filter_str, "-t", str(seg_duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def assemble_video(audio_path, broll_dir, output_path, segment_duration=8,
                   crossfade=0.5, verbose=True):
    """Assemble video from B-roll images + voiceover audio.

    Args:
        audio_path: Path to voiceover MP3/WAV
        broll_dir: Directory containing broll_01.png, broll_02.png, etc.
        output_path: Output MP4 path
        segment_duration: Seconds per B-roll image (default 8)
        crossfade: Crossfade duration between segments in seconds (0 to disable)
        verbose: Print progress

    Returns:
        tuple: (success: bool, size_mb: float, duration: float)
    """
    duration = get_audio_duration(audio_path)
    if verbose:
        print(f"  Audio duration: {duration:.1f}s ({duration/60:.1f} min)")

    images = sorted([
        os.path.join(broll_dir, f) for f in os.listdir(broll_dir)
        if f.endswith(".png") and f.startswith("broll_")
    ])

    if not images:
        if verbose:
            print("  No B-roll images found")
        return False, 0, 0

    if verbose:
        print(f"  B-roll images: {len(images)}")

    # Build segments
    num_segments = int(math.ceil(duration / segment_duration))
    temp_dir = os.path.join(os.path.dirname(output_path), "temp_segments")
    os.makedirs(temp_dir, exist_ok=True)

    segment_files = []
    fps = 30

    for i in range(num_segments):
        start = i * segment_duration
        seg_dur = min(segment_duration, duration - start)
        if seg_dur < 1:
            break

        seg_file = os.path.join(temp_dir, f"seg_{i:04d}.mp4")
        segment_files.append(seg_file)

        if os.path.exists(seg_file):
            if verbose:
                print(f"    [{i+1}/{num_segments}] SKIP (exists)")
            continue

        img_idx = i % len(images)
        effect_idx = i % 6

        if verbose:
            print(f"    [{i+1}/{num_segments}] {os.path.basename(images[img_idx])} "
                  f"(effect {effect_idx}, {seg_dur:.1f}s)")

        if not _build_segment(images[img_idx], seg_dur, effect_idx, seg_file, fps):
            if verbose:
                print(f"    Segment {i} failed")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, 0, 0

    if not segment_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    # Concatenate with optional crossfade
    if crossfade > 0 and len(segment_files) > 1:
        concat_output = _concat_with_crossfade(segment_files, temp_dir, crossfade, verbose)
    else:
        concat_output = _concat_simple(segment_files, temp_dir)

    if not concat_output or not os.path.exists(concat_output):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    if verbose:
        print("  Adding audio track...")

    # Merge audio + video
    cmd = [
        "ffmpeg", "-y",
        "-i", concat_output, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    shutil.rmtree(temp_dir, ignore_errors=True)

    if result.returncode == 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if verbose:
            print(f"  Video: {size_mb:.1f} MB, {duration/60:.1f} min")
        return True, size_mb, duration

    if verbose:
        print(f"  Audio merge failed (returncode {result.returncode})")
        if result.stderr:
            # Print last few lines of stderr for debugging
            lines = result.stderr.strip().split('\n')
            for line in lines[-5:]:
                print(f"    {line}")
    return False, 0, 0


def _concat_simple(segment_files, temp_dir):
    """Concatenate segments without transitions."""
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in segment_files:
            f.write(f"file '{os.path.abspath(sf)}'\n")

    concat_output = os.path.join(temp_dir, "video_only.mp4")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p", concat_output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        lines = result.stderr.strip().split('\n') if result.stderr else []
        for line in lines[-3:]:
            print(f"    concat error: {line}")
    return concat_output if result.returncode == 0 else None


def _concat_with_crossfade(segment_files, temp_dir, crossfade_dur, verbose=True):
    """Concatenate segments with crossfade transitions between them.

    Uses pairwise xfade filter to blend adjacent segments.
    Falls back to simple concat if crossfade fails (e.g. too many segments).
    """
    if verbose:
        print(f"  Applying {crossfade_dur}s crossfade transitions...")

    # For large numbers of segments, xfade filter graphs get huge.
    # Process in batches of 10 to keep filter complexity manageable.
    if len(segment_files) > 20:
        return _concat_batched_crossfade(segment_files, temp_dir, crossfade_dur, verbose)

    # Build xfade filter chain
    # xfade works pairwise: [0] xfade [1] -> [tmp1], [tmp1] xfade [2] -> [tmp2], ...
    inputs = []
    for sf in segment_files:
        inputs.extend(["-i", sf])

    filter_parts = []
    current_label = "[0:v]"

    for i in range(1, len(segment_files)):
        # Get duration of current accumulated stream
        # Offset = sum of all previous segment durations minus accumulated crossfades
        # For simplicity, calculate based on segment positions
        offset = _get_video_duration(segment_files[i - 1]) - crossfade_dur if i == 1 else None

        if i == 1:
            # First crossfade: between input 0 and input 1
            out_label = f"[v{i}]" if i < len(segment_files) - 1 else "[outv]"
            seg_dur = _get_video_duration(segment_files[0])
            offset = seg_dur - crossfade_dur
            filter_parts.append(
                f"{current_label}[{i}:v]xfade=transition=fade:duration={crossfade_dur}:offset={max(0, offset)}{out_label}"
            )
            current_label = out_label
        else:
            out_label = f"[v{i}]" if i < len(segment_files) - 1 else "[outv]"
            # Accumulated duration so far minus crossfades
            accumulated = sum(_get_video_duration(segment_files[j]) for j in range(i)) - (i - 1) * crossfade_dur
            offset = accumulated - crossfade_dur
            filter_parts.append(
                f"{current_label}[{i}:v]xfade=transition=fade:duration={crossfade_dur}:offset={max(0, offset)}{out_label}"
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
        concat_output
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        if verbose:
            print(f"  Crossfade failed, falling back to simple concat")
        return _concat_simple(segment_files, temp_dir)

    return concat_output


def _concat_batched_crossfade(segment_files, temp_dir, crossfade_dur, verbose=True):
    """Process crossfades in batches for large segment counts."""
    batch_size = 10
    batch_outputs = []

    for batch_start in range(0, len(segment_files), batch_size):
        batch = segment_files[batch_start:batch_start + batch_size]
        batch_output = os.path.join(temp_dir, f"batch_{batch_start:04d}.mp4")

        if len(batch) == 1:
            batch_outputs.append(batch[0])
            continue

        result = _concat_with_crossfade(batch, temp_dir, crossfade_dur, verbose=False)
        if result:
            # Move to batch-specific name
            if os.path.exists(result) and result != batch_output:
                os.rename(result, batch_output)
                batch_outputs.append(batch_output)
            else:
                batch_outputs.append(result)
        else:
            batch_outputs.extend(batch)

    # Final concat of batches (simple concat between batches)
    if len(batch_outputs) > 1:
        return _concat_simple(batch_outputs, temp_dir)
    return batch_outputs[0] if batch_outputs else None


def _get_video_duration(video_path):
    """Get video file duration using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 8.0  # Default segment duration
