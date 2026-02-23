"""Tests for utils.broll — B-roll template lookup and visual extraction."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.broll import get_broll_template, extract_visuals, CHANNEL_BROLL_TEMPLATES, DEFAULT_TEMPLATE


class TestGetBrollTemplate:
    def test_known_channel_returns_config(self):
        template = get_broll_template("RichMind")
        assert "prefix" in template
        assert "suffix" in template
        assert "segment_duration" in template

    def test_unknown_channel_returns_default(self):
        template = get_broll_template("NonExistentChannel")
        assert template == DEFAULT_TEMPLATE

    def test_all_templates_have_required_keys(self):
        for channel, template in CHANNEL_BROLL_TEMPLATES.items():
            assert "prefix" in template, f"{channel} missing prefix"
            assert "suffix" in template, f"{channel} missing suffix"
            assert "segment_duration" in template, f"{channel} missing segment_duration"
            assert isinstance(template["segment_duration"], int), f"{channel} duration not int"

    def test_cumquat_vibes_brand_colors(self):
        template = get_broll_template("CumquatVibes")
        assert "#101922" in template["prefix"]
        assert "#e8941f" in template["prefix"]

    def test_segment_duration_range(self):
        for channel, template in CHANNEL_BROLL_TEMPLATES.items():
            assert 4 <= template["segment_duration"] <= 15, f"{channel} duration out of range"


class TestExtractVisuals:
    def test_standard_format(self, tmp_path):
        script = tmp_path / "test_script.txt"
        script.write_text(
            "Introduction text\n"
            "[VISUAL: futuristic cityscape at night]\n"
            "More narration here\n"
            "[VISUAL: close-up of robot hand]\n"
        )
        visuals = extract_visuals(str(script))
        assert len(visuals) == 2
        assert "futuristic cityscape" in visuals[0]
        assert "robot hand" in visuals[1]

    def test_alternative_format(self, tmp_path):
        script = tmp_path / "test_script.txt"
        script.write_text(
            "Some text\n"
            "**(Visual: beautiful sunset over ocean)**\n"
            "More text\n"
            "**(Visual: mountain landscape)**\n"
        )
        visuals = extract_visuals(str(script))
        assert len(visuals) == 2

    def test_no_visuals_returns_empty(self, tmp_path):
        script = tmp_path / "test_script.txt"
        script.write_text("Just plain text without any visual markers.")
        visuals = extract_visuals(str(script))
        assert len(visuals) == 0
