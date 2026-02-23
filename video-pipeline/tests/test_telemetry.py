"""Tests for utils.telemetry — SQLite telemetry database operations."""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.telemetry import (
    log_video_planned,
    log_video_produced,
    log_video_preflight,
    log_video_published,
    log_video_quality,
    update_costs,
    log_metrics,
    log_decision,
    log_incident,
    get_recent_performance,
    get_channel_summary,
    get_cost_report,
    detect_performance_drift,
)


class TestVideoLifecycle:
    def test_log_video_planned(self, in_memory_db):
        log_video_planned("test_video_1", "RichTech", topic="AI Tools")
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'test_video_1'").fetchone()
        assert row is not None
        assert row["channel"] == "RichTech"
        assert row["status"] == "planned"

    def test_log_video_planned_idempotent(self, in_memory_db):
        log_video_planned("test_video_1", "RichTech")
        log_video_planned("test_video_1", "RichTech")  # Should not duplicate
        count = in_memory_db.execute("SELECT COUNT(*) FROM videos WHERE video_name = 'test_video_1'").fetchone()[0]
        assert count == 1

    def test_log_video_produced(self, in_memory_db):
        log_video_planned("test_video_2", "RichHorror")
        log_video_produced("test_video_2", video_duration_sec=300.5, video_size_mb=45.2)
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'test_video_2'").fetchone()
        assert row["status"] == "produced"
        assert row["video_duration_sec"] == 300.5
        assert row["video_size_mb"] == 45.2

    def test_log_video_preflight(self, in_memory_db):
        log_video_planned("test_video_3", "RichTech")
        preflight = {
            "publishable": True,
            "risk_scores": {"policy": 0.1, "copyright": 0.2, "misleading_metadata": 0.0, "inauthentic_content": 0.0},
        }
        log_video_preflight("test_video_3", preflight)
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'test_video_3'").fetchone()
        assert row["preflight_passed"] == 1
        assert row["risk_policy"] == 0.1

    def test_log_video_published(self, in_memory_db):
        log_video_planned("test_video_4", "RichPets")
        log_video_published("test_video_4", "YT_VIDEO_ID_123", quota_used=1600)
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'test_video_4'").fetchone()
        assert row["status"] == "published"
        assert row["youtube_video_id"] == "YT_VIDEO_ID_123"
        assert row["youtube_quota_used"] == 1600

    def test_log_video_quality(self, in_memory_db):
        log_video_planned("test_video_5", "RichMind")
        log_video_quality("test_video_5", 85, details={"pacing": "good", "visuals": "excellent"})
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'test_video_5'").fetchone()
        assert row["quality_score"] == 85
        details = json.loads(row["quality_details"])
        assert details["pacing"] == "good"


class TestCostTracking:
    def test_update_costs(self, in_memory_db):
        log_video_planned("cost_video", "RichTech")
        update_costs("cost_video", tts_cost_usd=0.50, broll_cost_usd=1.20)
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'cost_video'").fetchone()
        assert row["tts_cost_usd"] == 0.50
        assert row["broll_cost_usd"] == 1.20

    def test_total_cost_is_sum(self, in_memory_db):
        log_video_planned("cost_video_2", "RichTech")
        update_costs("cost_video_2", tts_cost_usd=0.30, broll_cost_usd=0.70)
        row = in_memory_db.execute("SELECT * FROM videos WHERE video_name = 'cost_video_2'").fetchone()
        assert row["total_cost_usd"] == 1.0


class TestMetrics:
    def test_log_metrics(self, in_memory_db):
        log_metrics("test_vid", "7d", youtube_video_id="abc123", views=100, likes=10)
        row = in_memory_db.execute("SELECT * FROM metrics WHERE video_name = 'test_vid'").fetchone()
        assert row["window"] == "7d"
        assert row["views"] == 100
        assert row["likes"] == 10

    def test_multiple_windows(self, in_memory_db):
        log_metrics("test_vid", "7d", views=100)
        log_metrics("test_vid", "28d", views=500)
        rows = in_memory_db.execute("SELECT * FROM metrics WHERE video_name = 'test_vid'").fetchall()
        assert len(rows) == 2
        windows = {r["window"] for r in rows}
        assert windows == {"7d", "28d"}


class TestDecisions:
    def test_log_decision(self, in_memory_db):
        log_decision("test_vid", "template_selection", "maximize_ctr",
                     "arm_bold_text", alternatives=["arm_a", "arm_b"])
        row = in_memory_db.execute("SELECT * FROM decisions WHERE video_name = 'test_vid'").fetchone()
        assert row["decision_type"] == "template_selection"
        assert row["chosen_action"] == "arm_bold_text"


class TestIncidents:
    def test_log_incident(self, in_memory_db):
        log_incident("test_vid", "drift_detected", "warning", "15% regression in reward")
        row = in_memory_db.execute("SELECT * FROM incidents WHERE video_name = 'test_vid'").fetchone()
        assert row["incident_type"] == "drift_detected"
        assert row["severity"] == "warning"


class TestQueries:
    def test_get_recent_performance_empty(self, in_memory_db):
        result = get_recent_performance(10)
        assert result == []

    def test_get_channel_summary(self, in_memory_db):
        log_video_planned("v1", "RichTech")
        log_video_planned("v2", "RichTech")
        log_video_planned("v3", "RichHorror")
        result = get_channel_summary()
        assert len(result) == 2
        tech = next(r for r in result if r["channel"] == "RichTech")
        assert tech["total_videos"] == 2

    def test_get_cost_report(self, in_memory_db):
        log_video_planned("cv1", "RichTech")
        update_costs("cv1", tts_cost_usd=0.5, broll_cost_usd=1.0)
        result = get_cost_report(30)
        assert result is not None

    def test_detect_drift_insufficient_data(self, in_memory_db):
        result = detect_performance_drift(5, 20)
        assert result["drift_detected"] is False
        assert result["reason"] == "insufficient_data"
