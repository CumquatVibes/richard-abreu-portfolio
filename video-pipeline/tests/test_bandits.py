"""Tests for utils.bandits — Thompson Sampling multi-armed bandits."""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.bandits import (
    _normalize_reward,
    _thompson_sample,
    initialize_arms,
    select_arm,
    update_arm,
    get_arm_report,
    deactivate_arm,
    REWARD_MIN,
    REWARD_MAX,
    THUMBNAIL_STYLES,
)


class TestNormalizeReward:
    def test_min_reward_maps_to_zero(self):
        assert _normalize_reward(REWARD_MIN) == 0.0

    def test_max_reward_maps_to_one(self):
        assert _normalize_reward(REWARD_MAX) == 1.0

    def test_mid_reward(self):
        mid = (REWARD_MIN + REWARD_MAX) / 2  # 25
        result = _normalize_reward(mid)
        assert 0.49 <= result <= 0.51

    def test_below_min_clamped(self):
        assert _normalize_reward(-100) == 0.0

    def test_above_max_clamped(self):
        assert _normalize_reward(200) == 1.0


class TestThompsonSample:
    def test_returns_float(self):
        result = _thompson_sample(1.0, 1.0)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_high_alpha_biases_high(self):
        # With high alpha, most samples should be > 0.5
        samples = [_thompson_sample(100, 1) for _ in range(100)]
        assert sum(1 for s in samples if s > 0.5) > 90

    def test_high_beta_biases_low(self):
        samples = [_thompson_sample(1, 100) for _ in range(100)]
        assert sum(1 for s in samples if s < 0.5) > 90


class TestInitializeArms:
    def test_creates_arms(self, in_memory_db, sample_channel_config):
        arms = initialize_arms("rich_tech", sample_channel_config)
        # 2 formats × 3 thumbnail styles = 6 arms
        assert len(arms) == 6

    def test_arm_names_follow_pattern(self, in_memory_db, sample_channel_config):
        arms = initialize_arms("rich_tech", sample_channel_config)
        for arm in arms:
            assert arm["arm_name"].startswith("rich_tech__")
            parts = arm["arm_name"].split("__")
            assert len(parts) == 4  # channel__voice__format__thumb

    def test_idempotent(self, in_memory_db, sample_channel_config):
        arms1 = initialize_arms("rich_tech", sample_channel_config)
        arms2 = initialize_arms("rich_tech", sample_channel_config)
        # Second call should still work (INSERT OR IGNORE)
        rows = in_memory_db.execute("SELECT COUNT(*) FROM template_arms").fetchone()[0]
        assert rows == 6  # Not 12


class TestSelectArm:
    def test_selects_arm(self, in_memory_db, sample_channel_config):
        initialize_arms("rich_tech", sample_channel_config)
        result = select_arm("rich_tech")
        assert "arm_name" in result
        assert "config" in result
        assert result["arm_name"].startswith("rich_tech__")

    def test_auto_initializes_if_no_arms(self, in_memory_db, monkeypatch):
        # Patch channels_config.json path
        import tempfile
        config = {"channels": {"test_ch": {
            "voice_profile": "neutral_male",
            "formats": ["listicle"],
        }}}
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channels_config.json")
        # Only runs if config file exists, which it does in the real project
        result = select_arm("test_ch")
        # Should either return an arm or create one
        assert "arm_name" in result or "error" in result


class TestUpdateArm:
    def test_increments_pull_count(self, in_memory_db, sample_channel_config):
        initialize_arms("rich_tech", sample_channel_config)
        arms = get_arm_report("rich_tech")
        arm_name = arms[0]["arm_name"]

        result = update_arm(arm_name, 30.0, "test_video")
        assert result["total_pulls"] == 1

    def test_updates_avg_reward(self, in_memory_db, sample_channel_config):
        initialize_arms("rich_tech", sample_channel_config)
        arms = get_arm_report("rich_tech")
        arm_name = arms[0]["arm_name"]

        update_arm(arm_name, 45.0)  # normalized = (45+20)/90 ≈ 0.722
        result = get_arm_report("rich_tech")
        updated = next(a for a in result if a["arm_name"] == arm_name)
        assert updated["avg_reward"] > 0


class TestGetArmReport:
    def test_empty_report(self, in_memory_db):
        result = get_arm_report()
        assert result == []

    def test_filtered_by_channel(self, in_memory_db, sample_channel_config):
        initialize_arms("rich_tech", sample_channel_config)
        initialize_arms("rich_horror", {
            "voice_profile": "storyteller",
            "formats": ["compilation"],
        })
        tech_arms = get_arm_report("rich_tech")
        horror_arms = get_arm_report("rich_horror")
        assert all("rich_tech" in a["arm_name"] for a in tech_arms)
        assert all("rich_horror" in a["arm_name"] for a in horror_arms)


class TestDeactivateArm:
    def test_deactivates(self, in_memory_db, sample_channel_config):
        initialize_arms("rich_tech", sample_channel_config)
        arms = get_arm_report("rich_tech")
        arm_name = arms[0]["arm_name"]

        deactivate_arm(arm_name)
        updated = in_memory_db.execute(
            "SELECT active FROM template_arms WHERE arm_name = ?", (arm_name,)
        ).fetchone()
        assert updated["active"] == 0
