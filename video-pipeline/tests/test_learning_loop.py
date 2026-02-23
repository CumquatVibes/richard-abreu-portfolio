"""Tests for the closed-loop learning system."""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from utils.bandits import (
    select_arm_by_type, _auto_initialize, _init_arms,
    TITLE_FORMULAS, HOOK_CATEGORIES, SHORTS_CROP_STRATEGIES,
    SHORTS_CAPTION_STYLES, SHORTS_CAPTION_POSITIONS,
    VOICE_PARAM_PRESETS, POSTING_SLOTS,
)
from utils.analytics import compute_shorts_reward
from utils.telemetry import log_retention_curve, get_retention_curve


class TestSelectArmByType:
    """Tests for select_arm_by_type() -- Thompson Sampling by arm type."""

    def test_auto_initializes_title_arms(self, in_memory_db):
        result = select_arm_by_type("test_channel", "title_formula")
        assert "error" not in result
        assert result["arm_type"] == "title_formula"
        assert "config" in result
        assert "formula" in result["config"]

    def test_auto_initializes_hook_arms(self, in_memory_db):
        result = select_arm_by_type("test_channel", "hook_category")
        assert "error" not in result
        assert result["config"]["hook_category"] in HOOK_CATEGORIES

    def test_auto_initializes_shorts_arms(self, in_memory_db):
        result = select_arm_by_type("test_channel", "shorts_config")
        assert "error" not in result
        config = result["config"]
        assert config["crop_strategy"] in SHORTS_CROP_STRATEGIES
        assert config["caption_style"] in SHORTS_CAPTION_STYLES
        assert config["caption_position"] in SHORTS_CAPTION_POSITIONS

    def test_auto_initializes_voice_arms(self, in_memory_db):
        result = select_arm_by_type("test_channel", "voice_params")
        assert "error" not in result
        config = result["config"]
        assert "stability" in config
        assert "speed" in config

    def test_auto_initializes_schedule_arms(self, in_memory_db):
        result = select_arm_by_type("test_channel", "posting_schedule")
        assert "error" not in result
        assert result["config"]["posting_slot"] in POSTING_SLOTS

    def test_returns_arm_name(self, in_memory_db):
        result = select_arm_by_type("test_channel", "title_formula")
        assert "arm_name" in result
        assert result["arm_name"].startswith("test_channel__")

    def test_returns_sampled_value(self, in_memory_db):
        result = select_arm_by_type("test_channel", "hook_category")
        assert "sampled_value" in result
        assert 0 <= result["sampled_value"] <= 1

    def test_different_channels_independent(self, in_memory_db):
        r1 = select_arm_by_type("channel_a", "title_formula")
        r2 = select_arm_by_type("channel_b", "title_formula")
        assert r1["arm_name"].startswith("channel_a__")
        assert r2["arm_name"].startswith("channel_b__")


class TestShortsReward:
    """Tests for compute_shorts_reward() -- Shorts-specific reward function."""

    @pytest.fixture
    def sample_metrics(self):
        return {
            "data_available": True,
            "views": 1000,
            "engagedViews": 400,
            "averageViewPercentage": 70,
            "shares": 15,
            "subscribersGained": 8,
            "subscribersLost": 1,
        }

    def test_returns_total_reward(self, sample_metrics):
        result = compute_shorts_reward(sample_metrics)
        assert "total_reward" in result
        assert result["total_reward"] > 0

    def test_retention_weighted_higher(self, sample_metrics):
        result = compute_shorts_reward(sample_metrics)
        assert result["components"]["retention"] <= 30  # max 30 pts

    def test_engaged_view_rate(self, sample_metrics):
        result = compute_shorts_reward(sample_metrics)
        # 400/1000 = 40% engaged, score = min(0.4/0.5, 1) * 20 = 16
        assert result["components"]["engaged_view_rate"] == 16.0

    def test_share_score(self, sample_metrics):
        result = compute_shorts_reward(sample_metrics)
        # 15/1000 = 1.5% share rate, score = min(0.015/0.02, 1) * 15 = 11.25
        assert result["components"]["shares"] == 11.25

    def test_cost_penalty_lower_for_shorts(self, sample_metrics):
        result = compute_shorts_reward(sample_metrics, costs={"total_cost_usd": 2})
        # $2 / 2 = 1.0, -min(1.0, 5) = -1.0
        assert result["components"]["cost_penalty"] == -1.0

    def test_no_data(self):
        result = compute_shorts_reward(None)
        assert result["confidence"] == "no_data"

    def test_empty_metrics(self):
        result = compute_shorts_reward({})
        assert result["confidence"] == "no_data"

    def test_high_confidence_threshold(self, sample_metrics):
        result = compute_shorts_reward(sample_metrics)
        assert result["confidence"] == "high"  # 1000 views

    def test_low_views_confidence(self, sample_metrics):
        sample_metrics["views"] = 50
        result = compute_shorts_reward(sample_metrics)
        assert result["confidence"] == "low"


class TestRetentionCurve:
    """Tests for retention curve storage and retrieval."""

    def test_log_and_get_retention(self, in_memory_db):
        data = [
            {"elapsed_pct": 0.0, "watch_ratio": 1.0, "relative_perf": 0.5},
            {"elapsed_pct": 0.25, "watch_ratio": 1.2, "relative_perf": 0.6},
            {"elapsed_pct": 0.5, "watch_ratio": 0.8, "relative_perf": 0.4},
            {"elapsed_pct": 0.75, "watch_ratio": 0.6, "relative_perf": 0.3},
            {"elapsed_pct": 1.0, "watch_ratio": 0.3, "relative_perf": 0.2},
        ]
        log_retention_curve("test_video", "yt123", data)

        stored = get_retention_curve("test_video")
        assert len(stored) == 5
        assert stored[0]["elapsed_pct"] == 0.0
        assert stored[1]["audience_watch_ratio"] == 1.2

    def test_empty_retention_data(self, in_memory_db):
        log_retention_curve("test_video", "yt123", [])
        stored = get_retention_curve("test_video")
        assert stored == []

    def test_nonexistent_video(self, in_memory_db):
        stored = get_retention_curve("nonexistent")
        assert stored == []


class TestRetentionInformedClipping:
    """Tests for retention-informed clip scoring in find_best_clips."""

    def test_high_retention_boosts_score(self):
        from utils.shorts import find_best_clips

        segments = [
            {"name": "Intro", "start_sec": 0, "end_sec": 30,
             "text": "Hook text here", "visuals": ["v1", "v2"]},
            {"name": "Middle", "start_sec": 30, "end_sec": 60,
             "text": "Middle content", "visuals": ["v3"]},
        ]

        # Without retention data
        clips_no_ret = find_best_clips(segments)

        # With high retention on the intro segment
        retention_data = [
            {"elapsed_pct": 0.0, "watch_ratio": 1.5},
            {"elapsed_pct": 0.1, "watch_ratio": 1.4},
            {"elapsed_pct": 0.2, "watch_ratio": 1.3},
            {"elapsed_pct": 0.5, "watch_ratio": 0.3},
            {"elapsed_pct": 0.8, "watch_ratio": 0.2},
        ]

        clips_with_ret = find_best_clips(segments, retention_data=retention_data)

        # The intro clip should have a higher score with retention data
        if clips_no_ret and clips_with_ret:
            intro_no_ret = next((c for c in clips_no_ret if c["name"] == "Intro"), None)
            intro_with_ret = next((c for c in clips_with_ret if c["name"] == "Intro"), None)
            if intro_no_ret and intro_with_ret:
                assert intro_with_ret["score"] >= intro_no_ret["score"]


class TestArmTypeConstants:
    """Tests for arm type configuration constants."""

    def test_title_formulas_count(self):
        assert len(TITLE_FORMULAS) == 12

    def test_hook_categories_count(self):
        assert len(HOOK_CATEGORIES) == 7

    def test_shorts_config_combinations(self):
        total = (len(SHORTS_CROP_STRATEGIES) *
                 len(SHORTS_CAPTION_STYLES) *
                 len(SHORTS_CAPTION_POSITIONS))
        assert total == 27

    def test_voice_presets_have_required_keys(self):
        for name, preset in VOICE_PARAM_PRESETS.items():
            assert "stability" in preset
            assert "speed" in preset
            assert "style" in preset

    def test_posting_slots_count(self):
        assert len(POSTING_SLOTS) == 7


class TestRetrainingTriggers:
    """Tests for retraining trigger detection."""

    def test_check_returns_list(self, in_memory_db):
        from utils.alerts import check_retraining_triggers
        triggers = check_retraining_triggers()
        assert isinstance(triggers, list)

    def test_execute_with_no_triggers(self, in_memory_db):
        from utils.alerts import execute_retraining
        actions = execute_retraining([])
        assert actions == []

    def test_execute_drift_trigger(self, in_memory_db):
        from utils.alerts import execute_retraining
        actions = execute_retraining([("performance_drift", {"direction": "regression"})])
        assert len(actions) > 0
        assert "drift" in actions[0].lower() or "reset" in actions[0].lower()
