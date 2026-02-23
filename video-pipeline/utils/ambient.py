"""Ambient / endless video production pipeline.

Produces long-form (1-12 hour) looping ambient videos from images + audio.
Designed for fireplace, lofi, rain, art slideshow, and study music content.

Key differences from assembly.py:
- Much longer segment durations (60-300s per image vs 8s)
- Slower Ken Burns effects for gentle, non-distracting motion
- Audio looping to fill target duration
- 4K output option (3840x2160)
- Optimized encoding for very long videos (lower bitrate, faster preset)
"""

import math
import os
import shutil
import subprocess

# Slow Ken Burns presets for ambient content — barely perceptible motion
AMBIENT_KEN_BURNS = {
    # Very slow zoom in (center)
    0: "zoompan=z='min(zoom+0.0002,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # Very slow zoom out (center)
    1: "zoompan=z='if(eq(on,1),1.08,max(zoom-0.0002,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    # Slow pan left to right
    2: "zoompan=z='1.05':x='(iw/zoom-ow)/(FRAMES)*on':y='(ih-oh)/2'",
    # Slow pan right to left
    3: "zoompan=z='1.05':x='(iw/zoom-ow)-((iw/zoom-ow)/(FRAMES))*on':y='(ih-oh)/2'",
    # Slow pan top to bottom
    4: "zoompan=z='1.05':x='(iw/zoom-ow)/2':y='(ih/zoom-oh)/(FRAMES)*on'",
    # Slow pan bottom to top
    5: "zoompan=z='1.05':x='(iw/zoom-ow)/2':y='(ih/zoom-oh)-((ih/zoom-oh)/(FRAMES))*on'",
    # Very slow zoom in (top-left)
    6: "zoompan=z='min(zoom+0.00015,1.06)':x='0':y='0'",
    # Very slow zoom in (bottom-right)
    7: "zoompan=z='min(zoom+0.00015,1.06)':x='iw/zoom-ow':y='ih/zoom-oh'",
}


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def _build_ambient_segment(img_path, seg_duration, effect_idx, output_path,
                           resolution="1080p", fps=24):
    """Build a single slow Ken Burns segment for ambient video.

    Args:
        img_path: Source image path
        seg_duration: Duration in seconds (typically 60-300)
        effect_idx: Index into AMBIENT_KEN_BURNS
        output_path: Output MP4 path
        resolution: "1080p" (1920x1080) or "4k" (3840x2160)
        fps: Frame rate (24 for ambient, saves encoding time)
    """
    total_frames = int(seg_duration * fps)
    effect_str = AMBIENT_KEN_BURNS[effect_idx % len(AMBIENT_KEN_BURNS)]
    effect_str = effect_str.replace("FRAMES", str(total_frames))

    if resolution == "4k":
        min_w = 4800
        size = "3840x2160"
        crf = "26"  # Slightly higher CRF for 4K (smaller files)
    else:
        min_w = 2560
        size = "1920x1080"
        crf = "24"

    # Upscale small images to minimum width for Ken Burns, then force even dims
    scale = f"scale='max(iw,{min_w}):-2':flags=lanczos"

    filter_str = f"{scale},{effect_str}:d={total_frames}:s={size}:fps={fps},format=yuv420p"

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
        "-vf", filter_str, "-t", str(seg_duration),
        "-c:v", "libx264", "-preset", "medium", "-crf", crf,
        "-pix_fmt", "yuv420p", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _loop_audio(audio_path, target_duration, output_path):
    """Loop audio to fill target duration with crossfade between loops.

    Uses ffmpeg's aloop or concat + trim to seamlessly loop audio.
    """
    audio_dur = get_audio_duration(audio_path)

    if audio_dur >= target_duration:
        # Audio is already long enough, just trim
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-t", str(target_duration),
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    # Calculate loops needed
    loops_needed = math.ceil(target_duration / audio_dur)

    # Create concat file
    concat_file = output_path + ".concat.txt"
    with open(concat_file, "w") as f:
        for _ in range(loops_needed):
            f.write(f"file '{os.path.abspath(audio_path)}'\n")

    # Concat and trim to exact duration
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-t", str(target_duration),
        "-c:a", "aac", "-b:a", "192k",
        "-af", "afade=t=in:st=0:d=3,afade=t=out:st={:.1f}:d=5".format(
            target_duration - 5
        ),
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Clean up concat file
    if os.path.exists(concat_file):
        os.remove(concat_file)

    return result.returncode == 0


def assemble_ambient_video(images, audio_path, output_path,
                           target_duration_hours=1,
                           segment_duration=120,
                           resolution="1080p",
                           crossfade=2.0,
                           fps=24,
                           verbose=True):
    """Assemble a long-form ambient video from images + audio.

    Args:
        images: List of image file paths
        audio_path: Path to audio file (will be looped if needed)
        output_path: Output MP4 path
        target_duration_hours: Target video length in hours
        segment_duration: Seconds per image (default 120 = 2 minutes)
        resolution: "1080p" or "4k"
        crossfade: Crossfade between segments (seconds, 0 to disable)
        fps: Frame rate (24 recommended for ambient)
        verbose: Print progress

    Returns:
        tuple: (success: bool, size_mb: float, duration_sec: float)
    """
    target_duration = target_duration_hours * 3600

    if verbose:
        print(f"  Target: {target_duration_hours}h ({target_duration}s)")
        print(f"  Images: {len(images)}")
        print(f"  Segment duration: {segment_duration}s ({segment_duration/60:.1f} min)")
        print(f"  Resolution: {resolution}, FPS: {fps}")

    if not images:
        if verbose:
            print("  No images provided")
        return False, 0, 0

    # Calculate segments needed
    num_segments = int(math.ceil(target_duration / segment_duration))
    if verbose:
        print(f"  Segments needed: {num_segments}")

    # Unique temp dir per video to prevent segment collision between concurrent renders
    video_stem = os.path.splitext(os.path.basename(output_path))[0]
    temp_dir = os.path.join(os.path.dirname(output_path), f"temp_{video_stem}")
    os.makedirs(temp_dir, exist_ok=True)

    # Build video segments
    segment_files = []
    for i in range(num_segments):
        seg_dur = min(segment_duration, target_duration - i * segment_duration)
        if seg_dur < 5:
            break

        seg_file = os.path.join(temp_dir, f"amb_{i:04d}.mp4")
        segment_files.append(seg_file)

        if os.path.exists(seg_file):
            if verbose:
                print(f"    [{i+1}/{num_segments}] SKIP (exists)")
            continue

        img_idx = i % len(images)
        effect_idx = i % len(AMBIENT_KEN_BURNS)

        if verbose:
            print(f"    [{i+1}/{num_segments}] {os.path.basename(images[img_idx])} "
                  f"(effect {effect_idx}, {seg_dur:.0f}s)")

        if not _build_ambient_segment(images[img_idx], seg_dur, effect_idx,
                                       seg_file, resolution, fps):
            if verbose:
                print(f"    Segment {i} FAILED")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, 0, 0

    if not segment_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    if verbose:
        print(f"  Concatenating {len(segment_files)} segments...")

    # Simple concat for ambient (crossfade too expensive for many segments)
    concat_output = _ambient_concat(segment_files, temp_dir)
    if not concat_output or not os.path.exists(concat_output):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    # Get actual video duration
    video_duration = _get_duration(concat_output)

    # Loop audio to match video duration
    if verbose:
        print(f"  Looping audio to {video_duration/3600:.1f}h...")

    looped_audio = os.path.join(temp_dir, "audio_looped.m4a")
    if not _loop_audio(audio_path, video_duration, looped_audio):
        if verbose:
            print("  Audio looping failed")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    # Merge video + audio
    if verbose:
        print("  Merging audio + video...")

    cmd = [
        "ffmpeg", "-y",
        "-i", concat_output, "-i", looped_audio,
        "-c:v", "copy", "-c:a", "copy",
        "-shortest", "-movflags", "+faststart",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    shutil.rmtree(temp_dir, ignore_errors=True)

    if result.returncode == 0 and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if verbose:
            print(f"  Done: {size_mb:.0f} MB, {video_duration/3600:.1f}h")
        return True, size_mb, video_duration

    if verbose:
        print(f"  Final merge failed: {result.stderr[-500:]}")
    return False, 0, 0


def assemble_art_slideshow(images, output_path, duration_per_image=600,
                           resolution="4k", music_path=None,
                           music_volume=0.15, verbose=True):
    """Assemble a 4K art slideshow for TV display.

    Optimized for Samsung Frame TV / ambient art channel content.
    Each image displayed for 5-10 minutes with very subtle Ken Burns.

    Args:
        images: List of high-res artwork image paths
        output_path: Output MP4 path
        duration_per_image: Seconds per artwork (default 600 = 10 min)
        resolution: "1080p" or "4k" (default "4k")
        music_path: Optional ambient music track (looped)
        music_volume: Music volume (0.0-1.0, default 0.15)
        verbose: Print progress

    Returns:
        tuple: (success: bool, size_mb: float, duration_sec: float)
    """
    if not images:
        return False, 0, 0

    total_duration = len(images) * duration_per_image
    if verbose:
        print(f"  Art slideshow: {len(images)} works x {duration_per_image/60:.0f} min = "
              f"{total_duration/3600:.1f}h")

    # Unique temp dir per video to prevent segment collision
    video_stem = os.path.splitext(os.path.basename(output_path))[0]
    temp_dir = os.path.join(os.path.dirname(output_path), f"temp_{video_stem}")
    os.makedirs(temp_dir, exist_ok=True)

    # Build one segment per artwork
    segment_files = []
    for i, img in enumerate(images):
        seg_file = os.path.join(temp_dir, f"art_{i:03d}.mp4")
        segment_files.append(seg_file)

        if os.path.exists(seg_file):
            if verbose:
                print(f"    [{i+1}/{len(images)}] SKIP (exists)")
            continue

        effect_idx = i % len(AMBIENT_KEN_BURNS)
        if verbose:
            print(f"    [{i+1}/{len(images)}] {os.path.basename(img)} "
                  f"({duration_per_image/60:.0f} min, effect {effect_idx})")

        if not _build_ambient_segment(img, duration_per_image, effect_idx,
                                       seg_file, resolution, fps=24):
            if verbose:
                print(f"    FAILED")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, 0, 0

    # Concatenate
    if verbose:
        print(f"  Concatenating {len(segment_files)} artworks...")

    concat_output = _ambient_concat(segment_files, temp_dir)
    if not concat_output:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, 0, 0

    # Add music if provided
    if music_path and os.path.exists(music_path):
        if verbose:
            print(f"  Adding ambient music at {int(music_volume*100)}% volume...")

        video_dur = _get_duration(concat_output)
        final_output = output_path

        cmd = [
            "ffmpeg", "-y",
            "-i", concat_output, "-i", music_path,
            "-filter_complex",
            f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{video_dur},"
            f"volume={music_volume},"
            f"afade=t=in:st=0:d=5,afade=t=out:st={video_dur-5}:d=5[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            final_output
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        shutil.rmtree(temp_dir, ignore_errors=True)

        if result.returncode == 0 and os.path.exists(final_output):
            size_mb = os.path.getsize(final_output) / (1024 * 1024)
            if verbose:
                print(f"  Done: {size_mb:.0f} MB, {total_duration/3600:.1f}h")
            return True, size_mb, total_duration
        else:
            if verbose:
                print(f"  Music merge failed")
            return False, 0, 0
    else:
        # No music — just rename concat output
        os.rename(concat_output, output_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if verbose:
            print(f"  Done (no music): {size_mb:.0f} MB, {total_duration/3600:.1f}h")
        return True, size_mb, total_duration


def _ambient_concat(segment_files, temp_dir):
    """Concatenate segments using concat demuxer (fast, no re-encode)."""
    concat_file = os.path.join(temp_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in segment_files:
            f.write(f"file '{os.path.abspath(sf)}'\n")

    concat_output = os.path.join(temp_dir, "video_only.mp4")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c", "copy",  # Stream copy — no re-encode for speed
        "-movflags", "+faststart",
        concat_output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Fallback: re-encode concat (handles mismatched segment params)
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
            "-c:v", "libx264", "-preset", "fast", "-crf", "24",
            "-pix_fmt", "yuv420p",
            concat_output
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

    return concat_output if result.returncode == 0 else None


def _get_duration(video_path):
    """Get video duration in seconds."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 3600.0  # Default 1 hour
