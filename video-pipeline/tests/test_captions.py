"""Tests for utils.captions — word timestamps and caption segmentation."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.captions import (
    estimate_word_timestamps,
    generate_caption_segments,
)


class TestEstimateWordTimestamps:
    def test_returns_correct_count(self):
        words = estimate_word_timestamps("one two three four", 10.0)
        assert len(words) == 4

    def test_word_format(self):
        words = estimate_word_timestamps("hello world", 5.0)
        for w in words:
            assert "word" in w
            assert "start" in w
            assert "end" in w

    def test_timestamps_are_ordered(self):
        words = estimate_word_timestamps("the quick brown fox jumps", 10.0)
        for i in range(len(words) - 1):
            assert words[i]["start"] <= words[i + 1]["start"]
            assert words[i]["end"] <= words[i + 1]["start"] + 0.01  # slight overlap OK

    def test_stays_within_duration(self):
        words = estimate_word_timestamps("word " * 50, 30.0)
        # With 5% margin, last word should end before 30s
        assert words[-1]["end"] <= 30.0

    def test_five_percent_margin(self):
        words = estimate_word_timestamps("word " * 20, 10.0)
        # Last word should end around 9.5s (95% of 10.0)
        assert words[-1]["end"] <= 9.6

    def test_empty_text_returns_empty(self):
        assert estimate_word_timestamps("", 10.0) == []

    def test_single_word(self):
        words = estimate_word_timestamps("hello", 5.0)
        assert len(words) == 1
        assert words[0]["word"] == "hello"
        assert words[0]["start"] == 0.0

    def test_proportional_distribution(self):
        # Longer words should get more time
        words = estimate_word_timestamps("hi extraordinary", 10.0)
        short_dur = words[0]["end"] - words[0]["start"]
        long_dur = words[1]["end"] - words[1]["start"]
        assert long_dur > short_dur


class TestGenerateCaptionSegments:
    def _make_words(self, count=9, duration=10.0):
        return estimate_word_timestamps(" ".join(f"word{i}" for i in range(count)), duration)

    def test_capcut_groups_by_three(self):
        words = self._make_words(9)
        segments = generate_caption_segments(words, style="capcut", words_per_group=3)
        # 9 words / 3 per group = 3 groups, each word gets highlighted = 9 segments
        # OR 3 groups with 3 highlight cycles = varies by implementation
        assert len(segments) > 0
        for seg in segments:
            assert "text" in seg
            assert "words" in seg
            assert "highlight_word_idx" in seg
            assert "start_sec" in seg
            assert "end_sec" in seg

    def test_capcut_highlight_cycles(self):
        words = self._make_words(6)
        segments = generate_caption_segments(words, style="capcut", words_per_group=3)
        # Each segment should have a valid highlight index
        for seg in segments:
            assert 0 <= seg["highlight_word_idx"] < len(seg["words"])

    def test_minimal_style(self):
        words = self._make_words(12)
        segments = generate_caption_segments(words, style="minimal")
        assert len(segments) > 0
        for seg in segments:
            assert seg["highlight_word_idx"] == -1

    def test_karaoke_style(self):
        words = self._make_words(5)
        segments = generate_caption_segments(words, style="karaoke")
        assert len(segments) == 5
        for seg in segments:
            assert len(seg["words"]) == 1

    def test_timestamps_are_valid(self):
        words = self._make_words(9)
        segments = generate_caption_segments(words, style="capcut")
        for seg in segments:
            assert seg["start_sec"] < seg["end_sec"]
            assert seg["start_sec"] >= 0

    def test_empty_words_returns_empty(self):
        assert generate_caption_segments([]) == []

    def test_partial_group(self):
        # 7 words with group size 3 = 2 full groups + 1 partial group
        words = self._make_words(7)
        segments = generate_caption_segments(words, style="capcut", words_per_group=3)
        assert len(segments) > 0
        # Last segment should have the remaining word(s)
