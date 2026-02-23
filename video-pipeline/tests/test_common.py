"""Tests for utils.common — filename parsing and path helpers."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.common import strip_timestamp, get_channel_from_filename, find_audio_for_script


class TestStripTimestamp:
    def test_strips_valid_timestamp(self):
        assert strip_timestamp("RichTech_Title_20260221_120000") == "RichTech_Title"

    def test_preserves_name_without_timestamp(self):
        assert strip_timestamp("RichTech_Title") == "RichTech_Title"

    def test_non_numeric_suffix_preserved(self):
        assert strip_timestamp("RichTech_Title_extra") == "RichTech_Title_extra"

    def test_single_word_name(self):
        result = strip_timestamp("RichTech")
        assert result == "RichTech"

    def test_multiple_underscores(self):
        result = strip_timestamp("RichTech_Some_Long_Title_20260221_120000")
        assert result == "RichTech_Some_Long_Title"

    def test_partial_timestamp_not_stripped(self):
        # Only 1 numeric segment, not 2
        result = strip_timestamp("RichTech_Title_20260221")
        assert result == "RichTech_Title_20260221"


class TestGetChannelFromFilename:
    def test_extracts_channel_prefix(self):
        assert get_channel_from_filename("RichTech_Some_Title.mp4") == "RichTech"

    def test_handles_path(self):
        assert get_channel_from_filename("/path/to/RichHorror_Scary.mp4") == "RichHorror"

    def test_handles_txt_extension(self):
        assert get_channel_from_filename("EvaReyes_Some_Topic.txt") == "EvaReyes"

    def test_no_underscore(self):
        result = get_channel_from_filename("SingleWord.mp4")
        assert result == "SingleWord"


class TestFindAudioForScript:
    def test_finds_matching_audio(self, tmp_path, monkeypatch):
        # Create a fake audio file
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        audio_file = audio_dir / "RichTech_Title.mp3"
        audio_file.write_text("fake audio")

        monkeypatch.setattr("utils.common.AUDIO_DIR", str(audio_dir))
        path, name = find_audio_for_script("RichTech_Title_20260221_120000")
        assert path is not None
        assert "RichTech_Title.mp3" in path

    def test_missing_audio_returns_none(self, tmp_path, monkeypatch):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()

        monkeypatch.setattr("utils.common.AUDIO_DIR", str(audio_dir))
        path, name = find_audio_for_script("NonExistent_Script")
        assert path is None
