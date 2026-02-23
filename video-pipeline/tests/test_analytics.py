"""Tests for utils.analytics — compute_reward function."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.analytics import compute_reward


class TestComputeReward:
    def test_no_data_returns_zero(self):
        result = compute_reward(None)
        assert result["total_reward"] == 0
        assert result["confidence"] == "no_data"

    def test_data_not_available_returns_zero(self):
        result = compute_reward({"data_available": False})
        assert result["total_reward"] == 0
        assert result["confidence"] == "no_data"

    def test_components_present(self, sample_metrics):
        result = compute_reward(sample_metrics)
        assert "watch_time" in result["components"]
        assert "retention" in result["components"]
        assert "engagement" in result["components"]
        assert "subscriber_growth" in result["components"]
        assert "cost_penalty" in result["components"]
        assert "risk_penalty" in result["components"]

    def test_watch_time_max_score(self):
        metrics = {"data_available": True, "views": 100,
                   "estimatedMinutesWatched": 200, "averageViewPercentage": 0,
                   "likes": 0, "comments": 0, "shares": 0,
                   "subscribersGained": 0, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert result["components"]["watch_time"] == 20.0

    def test_watch_time_partial(self):
        metrics = {"data_available": True, "views": 100,
                   "estimatedMinutesWatched": 50, "averageViewPercentage": 0,
                   "likes": 0, "comments": 0, "shares": 0,
                   "subscribersGained": 0, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert result["components"]["watch_time"] == 10.0

    def test_retention_max_score(self):
        metrics = {"data_available": True, "views": 100,
                   "estimatedMinutesWatched": 0, "averageViewPercentage": 60,
                   "likes": 0, "comments": 0, "shares": 0,
                   "subscribersGained": 0, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert result["components"]["retention"] == 20.0

    def test_engagement_rate(self, sample_metrics):
        result = compute_reward(sample_metrics)
        # (25 + 5*2 + 3*3) / 500 = 44/500 = 0.088
        # min(0.088/0.1, 1.0) * 15 = 0.88 * 15 = 13.2
        assert 13.0 <= result["components"]["engagement"] <= 13.5

    def test_subscriber_growth(self, sample_metrics):
        result = compute_reward(sample_metrics)
        # net_subs = 8 - 1 = 7, min(7/10, 1) * 15 = 10.5
        assert result["components"]["subscriber_growth"] == 10.5

    def test_cost_penalty_applied(self, sample_metrics):
        # $5 / 5 = 1.0, -min(1.0, 10) = -1.0
        result = compute_reward(sample_metrics, costs={"total_cost_usd": 5.0})
        assert result["components"]["cost_penalty"] == -1.0

    def test_cost_penalty_partial(self, sample_metrics):
        # $2.5 / 5 = 0.5, -min(0.5, 10) = -0.5
        result = compute_reward(sample_metrics, costs={"total_cost_usd": 2.5})
        assert result["components"]["cost_penalty"] == -0.5

    def test_no_cost_no_penalty(self, sample_metrics):
        result = compute_reward(sample_metrics, costs=None)
        assert result["components"]["cost_penalty"] == 0

    def test_risk_penalty_applied(self, sample_metrics):
        result = compute_reward(sample_metrics, risk_scores={"policy": 0.5, "copyright": 0.8})
        # max_risk = 0.8, penalty = -0.8 * 20 = -16
        assert result["components"]["risk_penalty"] == -16.0

    def test_confidence_very_low(self):
        metrics = {"data_available": True, "views": 5,
                   "estimatedMinutesWatched": 1, "averageViewPercentage": 10,
                   "likes": 0, "comments": 0, "shares": 0,
                   "subscribersGained": 0, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert result["confidence"] == "very_low"

    def test_confidence_low(self):
        metrics = {"data_available": True, "views": 50,
                   "estimatedMinutesWatched": 10, "averageViewPercentage": 20,
                   "likes": 2, "comments": 0, "shares": 0,
                   "subscribersGained": 0, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert result["confidence"] == "low"

    def test_confidence_medium(self):
        metrics = {"data_available": True, "views": 500,
                   "estimatedMinutesWatched": 100, "averageViewPercentage": 40,
                   "likes": 20, "comments": 3, "shares": 1,
                   "subscribersGained": 5, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert result["confidence"] == "medium"

    def test_confidence_high(self):
        metrics = {"data_available": True, "views": 5000,
                   "estimatedMinutesWatched": 1000, "averageViewPercentage": 50,
                   "likes": 200, "comments": 30, "shares": 10,
                   "subscribersGained": 50, "subscribersLost": 5}
        result = compute_reward(metrics)
        assert result["confidence"] == "high"

    def test_zero_views_no_division_error(self):
        metrics = {"data_available": True, "views": 0,
                   "estimatedMinutesWatched": 0, "averageViewPercentage": 0,
                   "likes": 0, "comments": 0, "shares": 0,
                   "subscribersGained": 0, "subscribersLost": 0}
        result = compute_reward(metrics)
        assert isinstance(result["total_reward"], (int, float))
