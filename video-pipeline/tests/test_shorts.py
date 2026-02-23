"""Tests for utils.shorts — script parsing, clip scoring, metadata."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.shorts import (
    parse_script_segments,
    find_best_clips,
    make_shorts_title,
    make_shorts_description,
    make_shorts_tags,
    VERTICAL_WIDTH,
    VERTICAL_HEIGHT,
)


class TestParseScriptSegments:
    def test_parses_shorts_format(self, tmp_path):
        script = tmp_path / "test.txt"
        script.write_text(
            "---\ntitle: Test\nchannel: Test\n---\n\n"
            "## Hook (0:00-0:10)\n"
            "Did you know this amazing fact?\n"
            "[VISUAL: Amazing visual]\n\n"
            "## Fact 1 (0:10-0:25)\n"
            "Here is fact number one with details.\n"
            "[VISUAL: Fact one graphic]\n\n"
            "## Outro (0:25-0:30)\n"
            "Like and subscribe!\n"
        )
        segments = parse_script_segments(str(script))
        assert len(segments) == 3
        assert segments[0]["name"] == "Hook"
        assert segments[0]["start_sec"] == 0.0
        assert segments[0]["end_sec"] == 10.0

    def test_extracts_narration_without_visuals(self, tmp_path):
        script = tmp_path / "test.txt"
        script.write_text(
            "## Section (0:00-0:15)\n"
            "This is narration text.\n"
            "[VISUAL: Some visual description]\n"
            "More narration here.\n"
        )
        segments = parse_script_segments(str(script))
        assert len(segments) == 1
        assert "narration text" in segments[0]["text"]
        assert "More narration" in segments[0]["text"]
        assert "VISUAL" not in segments[0]["text"]

    def test_extracts_visual_descriptions(self, tmp_path):
        script = tmp_path / "test.txt"
        script.write_text(
            "## Section (0:00-0:20)\n"
            "Narration.\n"
            "[VISUAL: Cityscape at night]\n"
            "[VISUAL: Robot hand closeup]\n"
        )
        segments = parse_script_segments(str(script))
        assert len(segments[0]["visuals"]) == 2
        assert "Cityscape at night" in segments[0]["visuals"][0]
        assert "Robot hand closeup" in segments[0]["visuals"][1]

    def test_parses_chapter_format(self, tmp_path):
        script = tmp_path / "test.txt"
        script.write_text(
            "## Chapter 1: The Sky (0:30-3:30)\n"
            "The sky in films is a character itself.\n\n"
            "## Chapter 2: Food (3:30-7:00)\n"
            "Food is more than sustenance.\n"
        )
        segments = parse_script_segments(str(script))
        assert len(segments) == 2
        assert segments[0]["start_sec"] == 30.0
        assert segments[0]["end_sec"] == 210.0  # 3:30 = 210s
        assert segments[1]["start_sec"] == 210.0
        assert segments[1]["end_sec"] == 420.0  # 7:00 = 420s

    def test_empty_script_returns_empty(self, tmp_path):
        script = tmp_path / "test.txt"
        script.write_text("Just some text without any section headers.")
        segments = parse_script_segments(str(script))
        assert segments == []

    def test_strips_yaml_frontmatter(self, tmp_path):
        script = tmp_path / "test.txt"
        script.write_text(
            "---\ntitle: Test Title\nchannel: TestChannel\nformat: shorts_facts\n---\n\n"
            "## Hook (0:00-0:10)\nHook text here.\n"
        )
        segments = parse_script_segments(str(script))
        assert len(segments) == 1
        assert "title:" not in segments[0]["text"]
        assert "Hook text" in segments[0]["text"]


class TestFindBestClips:
    def _make_segments(self):
        return [
            {"name": "Hook", "start_sec": 0, "end_sec": 10,
             "text": "Did you know this amazing fact?", "visuals": ["hook visual"]},
            {"name": "Fact 1", "start_sec": 10, "end_sec": 35,
             "text": "Here is fact one with important details and conclusion.",
             "visuals": ["fact visual", "another visual"]},
            {"name": "Fact 2", "start_sec": 35, "end_sec": 55,
             "text": "Second fact about something interesting.",
             "visuals": ["second visual"]},
            {"name": "Outro", "start_sec": 55, "end_sec": 59,
             "text": "Like and subscribe!", "visuals": []},
        ]

    def test_returns_clips(self):
        segments = self._make_segments()
        clips = find_best_clips(segments)
        assert len(clips) > 0
        assert all("score" in c for c in clips)
        assert all("start_sec" in c for c in clips)
        assert all("end_sec" in c for c in clips)

    def test_sorted_by_score_descending(self):
        segments = self._make_segments()
        clips = find_best_clips(segments)
        scores = [c["score"] for c in clips]
        assert scores == sorted(scores, reverse=True)

    def test_respects_max_duration(self):
        segments = self._make_segments()
        clips = find_best_clips(segments, max_duration=30)
        for clip in clips:
            duration = clip["end_sec"] - clip["start_sec"]
            assert duration <= 30

    def test_respects_min_duration(self):
        segments = self._make_segments()
        clips = find_best_clips(segments, min_duration=20)
        for clip in clips:
            duration = clip["end_sec"] - clip["start_sec"]
            assert duration >= 20

    def test_hook_has_hook_text(self):
        segments = self._make_segments()
        clips = find_best_clips(segments)
        assert all("hook_text" in c for c in clips)

    def test_empty_segments_returns_empty(self):
        assert find_best_clips([]) == []


class TestMakeShortsTitle:
    def test_youtube_appends_shorts_tag(self):
        title = make_shorts_title("RichMind_Cool_Topic", platform="youtube")
        assert "#Shorts" in title

    def test_tiktok_no_shorts_tag(self):
        title = make_shorts_title("RichMind_Cool_Topic", platform="tiktok")
        assert "#Shorts" not in title

    def test_strips_timestamp(self):
        title = make_shorts_title("RichMind_Topic_20260221_194638", platform="youtube")
        assert "20260221" not in title

    def test_max_length(self):
        title = make_shorts_title("A" * 200, platform="youtube")
        assert len(title) <= 100


class TestMakeShortsDescription:
    def test_contains_ai_disclosure(self):
        desc = make_shorts_description("RichTech", "Cool AI Tools")
        assert "AI" in desc or "ai" in desc.lower()

    def test_youtube_format(self):
        desc = make_shorts_description("RichTech", "Cool Title", platform="youtube")
        assert len(desc) > 10

    def test_tiktok_format(self):
        desc = make_shorts_description("RichTech", "Cool Title", platform="tiktok")
        assert len(desc) > 10


class TestMakeShortsTags:
    def test_youtube_includes_shorts(self):
        tags = make_shorts_tags("RichTech", "AI Tools Review", platform="youtube")
        assert any("shorts" in t.lower() for t in tags)

    def test_returns_list(self):
        tags = make_shorts_tags("RichTech", "AI Tools Review")
        assert isinstance(tags, list)
        assert len(tags) >= 3

    def test_tiktok_includes_fyp(self):
        tags = make_shorts_tags("RichTech", "AI Tools", platform="tiktok")
        assert any("fyp" in t.lower() for t in tags)


class TestConstants:
    def test_vertical_dimensions(self):
        assert VERTICAL_WIDTH == 1080
        assert VERTICAL_HEIGHT == 1920
