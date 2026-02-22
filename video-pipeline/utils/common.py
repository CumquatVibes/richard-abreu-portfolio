"""Common utilities shared across the video pipeline."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "scripts")
AUDIO_DIR = os.path.join(BASE_DIR, "output", "audio")
BROLL_DIR = os.path.join(BASE_DIR, "output", "broll")
VIDEOS_DIR = os.path.join(BASE_DIR, "output", "videos")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")


def find_audio_for_script(script_basename):
    """Find matching audio file for a script (strips timestamp suffix).

    Script: Channel_Title_YYYYMMDD_HHMMSS.txt -> Audio: Channel_Title.mp3

    Returns:
        tuple: (audio_path, audio_name) — audio_path is None if not found
    """
    parts = script_basename.rsplit("_", 2)
    if len(parts) >= 3:
        try:
            int(parts[-1])
            int(parts[-2])
            audio_name = "_".join(parts[:-2])
        except ValueError:
            audio_name = script_basename
    else:
        audio_name = script_basename

    audio_path = os.path.join(AUDIO_DIR, f"{audio_name}.mp3")
    if os.path.exists(audio_path):
        return audio_path, audio_name
    return None, audio_name


def strip_timestamp(basename):
    """Remove YYYYMMDD_HHMMSS timestamp suffix from a basename.

    Returns the cleaned name (no timestamp).
    """
    parts = basename.rsplit("_", 2)
    if len(parts) >= 3:
        try:
            int(parts[-1])
            int(parts[-2])
            return "_".join(parts[:-2])
        except ValueError:
            pass
    return basename


def get_channel_from_filename(filename):
    """Extract channel name from a pipeline filename (e.g. RichMind_Title_...)."""
    basename = os.path.splitext(os.path.basename(filename))[0]
    return basename.split("_")[0]
