"""Shared test fixtures for the video pipeline test suite."""

import json
import os
import sqlite3
import sys

import pytest

# Add pipeline to path
PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PIPELINE_DIR)


class _NoCloseConnection:
    """Wrapper that makes close() a no-op so the shared connection survives."""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass  # no-op

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def in_memory_db(monkeypatch):
    """Provide an in-memory SQLite database for telemetry tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    from utils.telemetry import _create_tables
    _create_tables(conn)

    wrapper = _NoCloseConnection(conn)

    def _fake_get_db():
        return wrapper

    monkeypatch.setattr("utils.telemetry._get_db", _fake_get_db)

    try:
        monkeypatch.setattr("utils.bandits._get_db", _fake_get_db)
    except Exception:
        pass

    yield wrapper
    conn.close()


@pytest.fixture
def sample_script_text():
    """Sample script text for compliance/analysis tests."""
    return (
        "# Channel: RichTech\n"
        "# Topic: 5 Best AI Tools for 2026\n"
        "\n"
        "[CHAPTER: Introduction]\n"
        "Have you ever wondered which AI tools are actually worth your time?\n"
        "\n"
        "[VISUAL: futuristic tech workspace with holographic displays]\n"
        "\n"
        "Today we cover the top 5 AI tools changing the game in 2026.\n"
        "\n"
        "[CHAPTER: 1. Claude by Anthropic]\n"
        "[VISUAL: Claude AI interface on a laptop screen]\n"
        "First up is Claude by Anthropic. This assistant has become the go-to.\n"
        "\n"
        "[CHAPTER: 2. Gemini by Google]\n"
        "[VISUAL: Google Gemini logo on gradient background]\n"
        "Number two is Google Gemini with multimodal capabilities.\n"
        "\n"
        "[CHAPTER: 3. Midjourney V7]\n"
        "[VISUAL: stunning AI-generated artwork gallery]\n"
        "Midjourney version seven takes image generation to new heights.\n"
        "\n"
        "[CHAPTER: 4. Cursor IDE]\n"
        "[VISUAL: developer coding in Cursor IDE]\n"
        "Cursor has changed how developers write code forever.\n"
        "\n"
        "[CHAPTER: 5. ElevenLabs]\n"
        "[VISUAL: sound wave visualization]\n"
        "ElevenLabs delivers the most realistic AI voice cloning.\n"
        "\n"
        "[CHAPTER: Conclusion]\n"
        "Those are the 5 best AI tools for 2026. Like and subscribe!\n"
        "Created with AI voice and visuals.\n"
        + " word" * 450  # Pad to ~500 words
    )


@pytest.fixture
def sample_metrics():
    """Sample YouTube metrics dict."""
    return {
        "video_id": "abc123",
        "data_available": True,
        "views": 500,
        "estimatedMinutesWatched": 150,
        "averageViewDuration": 180,
        "averageViewPercentage": 45.0,
        "likes": 25,
        "comments": 5,
        "shares": 3,
        "subscribersGained": 8,
        "subscribersLost": 1,
    }


@pytest.fixture
def sample_channel_config():
    """Sample channel config dict for testing."""
    return {
        "name": "RichTech",
        "handle": "@RichTech",
        "niche": "technology, gadgets",
        "faceless": True,
        "voice_profile": "neutral_male",
        "formats": ["listicle", "explainer"],
        "sub_topics": ["AI tools", "smartphones", "laptops"],
    }
