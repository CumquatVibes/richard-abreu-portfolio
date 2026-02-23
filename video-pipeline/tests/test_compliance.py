"""Tests for utils.compliance — preflight compliance gate."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.compliance import (
    preflight_check,
    format_preflight_report,
    CLICKBAIT_PATTERNS,
    ADVERTISER_RISK_TERMS,
    SENSITIVE_TOPICS,
)


# ── Preflight Overall ──

class TestPreflightCheck:
    def test_clean_content_passes(self, sample_script_text):
        result = preflight_check(
            script_text=sample_script_text,
            title="5 Best AI Tools for 2026",
            description="Discover the top AI tools. Created with AI voice and visuals.",
            tags=["ai", "tools", "tech", "2026"],
        )
        assert result["publishable"] is True

    def test_risk_scores_initialized_to_zero_base(self):
        result = preflight_check(
            script_text="A " * 600,
            title="Simple Topic Here",
            description="A nice simple description that is over fifty chars easily. AI-generated content.",
            tags=["test", "video", "simple"],
            is_synthetic=False,
        )
        assert result["risk_scores"]["misleading_metadata"] == 0.0

    def test_synthetic_disclosure_required(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Simple Test Video",
            description="A description without any AI mention at all, over fifty characters.",
            tags=["test", "video", "content"],
            is_synthetic=True,
        )
        violations = [v for v in result["violations"] if v["type"] == "missing_synthetic_disclosure"]
        assert len(violations) == 1

    def test_synthetic_disclosure_present(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Simple Test Video",
            description="This video was created with AI-generated voice and visuals for your enjoyment.",
            tags=["test", "video", "content"],
            is_synthetic=True,
        )
        violations = [v for v in result["violations"] if v["type"] == "missing_synthetic_disclosure"]
        assert len(violations) == 0

    def test_is_synthetic_false_skips_disclosure(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Simple Test Video",
            description="No disclosure needed here, this is a real video over fifty characters.",
            tags=["test", "video", "content"],
            is_synthetic=False,
        )
        violations = [v for v in result["violations"] if v["type"] == "missing_synthetic_disclosure"]
        assert len(violations) == 0

    def test_critical_violation_blocks_publishing(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Drugs kill murder death gore blood",
            description="This video is about drugs and murder and death. AI-generated content.",
            tags=["drugs", "kill", "murder", "death", "gore"],
            is_synthetic=True,
        )
        assert result["publishable"] is False


# ── Misleading Metadata ──

class TestMisleadingMetadata:
    def test_clickbait_pattern_detected(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="You Won't Believe What Happened Next",
            description="Description over fifty chars easily. Created with AI voice and visuals.",
            tags=["amazing", "wow", "test"],
        )
        violations = [v for v in result["violations"] if v["type"] == "misleading_metadata"]
        assert len(violations) >= 1
        assert result["risk_scores"]["misleading_metadata"] >= 0.5

    def test_numeric_claim_mismatch(self):
        # Title claims 10 items but script only has 2 numbered items
        script = "1. First item\n2. Second item\n" + "Word " * 500
        result = preflight_check(
            script_text=script,
            title="10 Ways to Save Money",
            description="Money saving tips. Created with AI voice and visuals.",
            tags=["finance", "tips", "money"],
        )
        violations = [v for v in result["violations"]
                      if v["type"] == "misleading_metadata" and "items" in v.get("evidence", "")]
        assert len(violations) >= 1

    def test_no_clickbait_no_violation(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Best Budget Laptops for Students 2026",
            description="Laptop review guide. Created with AI voice and visuals.",
            tags=["laptop", "budget", "review"],
        )
        violations = [v for v in result["violations"]
                      if v["type"] == "misleading_metadata" and "Clickbait" in v.get("evidence", "")]
        assert len(violations) == 0

    def test_thumbnail_claim_unsupported(self):
        result = preflight_check(
            script_text="This is a normal video about cooking. " * 50,
            title="Cooking Tips",
            description="Great cooking tips. Created with AI voice and visuals.",
            tags=["cooking"],
            thumbnail_concept="EXPOSED: the truth about cooking oil",
        )
        violations = [v for v in result["violations"]
                      if "exposed" in v.get("evidence", "").lower()]
        assert len(violations) >= 1


# ── Advertiser Friendliness ──

class TestAdvertiserFriendly:
    def test_single_risk_term_warning(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Understanding Drug Policy Reform",
            description="Educational content about policy. Created with AI voice and visuals.",
            tags=["policy", "education", "drugs"],
        )
        violations = [v for v in result["violations"] if v["type"] == "advertiser_unfriendly"]
        assert any(v["severity"] == "warning" for v in violations)

    def test_three_risk_terms_critical(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Video about drugs and death and gore",
            description="Content description. Created with AI voice and visuals.",
            tags=["drugs", "death", "gore", "test"],
        )
        violations = [v for v in result["violations"] if v["type"] == "advertiser_unfriendly"]
        assert any(v["severity"] == "critical" for v in violations)

    def test_clean_metadata_no_violations(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Best Productivity Apps for 2026",
            description="App review content. Created with AI voice and visuals.",
            tags=["apps", "productivity", "2026"],
        )
        violations = [v for v in result["violations"] if v["type"] == "advertiser_unfriendly"]
        assert len(violations) == 0


# ── Sensitive Topics ──

class TestSensitiveTopics:
    def test_medical_topic_flagged(self):
        result = preflight_check(
            script_text="This medication can help with treatment of various conditions. " * 30,
            title="Health Tips",
            description="Health content. Created with AI voice and visuals.",
            tags=["health", "tips", "wellness"],
        )
        violations = [v for v in result["violations"] if v["type"] == "sensitive_topic"]
        assert len(violations) >= 1

    def test_neutral_content_not_flagged(self):
        result = preflight_check(
            script_text="Technology review about the latest smartphone features. " * 30,
            title="New Phone Review 2026",
            description="Phone review. Created with AI voice and visuals.",
            tags=["phone", "tech", "review"],
        )
        violations = [v for v in result["violations"] if v["type"] == "sensitive_topic"]
        assert len(violations) == 0


# ── Quality Gates ──

class TestQualityGates:
    def test_title_too_long(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="A" * 101,
            description="Description over fifty characters easily enough. AI-generated content.",
            tags=["test", "long", "title"],
        )
        violations = [v for v in result["violations"] if "Title too long" in v.get("evidence", "")]
        assert len(violations) == 1

    def test_title_too_short(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Hi",
            description="Description over fifty characters easily enough. AI-generated content.",
            tags=["test"],
        )
        violations = [v for v in result["violations"] if "Title too short" in v.get("evidence", "")]
        assert len(violations) == 1

    def test_description_too_short(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Normal Title Here",
            description="Short",
            tags=["test", "video", "content"],
        )
        violations = [v for v in result["violations"] if "Description" in v.get("evidence", "")]
        assert len(violations) >= 1

    def test_short_script_warning(self):
        result = preflight_check(
            script_text="Short script only a few words.",
            title="Test Video Title Here",
            description="Description over fifty characters easily. AI-generated content.",
            tags=["test", "video", "content"],
        )
        violations = [v for v in result["violations"] if "Script very short" in v.get("evidence", "")]
        assert len(violations) == 1


# ── Licenses ──

class TestLicenses:
    def test_no_manifest_warning(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Normal Title Here",
            description="Description over fifty chars. AI-generated content.",
            tags=["test", "video", "content"],
            asset_manifest=None,
        )
        violations = [v for v in result["violations"] if v["type"] == "missing_license_info"]
        assert len(violations) == 1

    def test_unlicensed_assets_critical(self):
        manifest = {
            "image1.png": {"license": "unknown"},
            "image2.png": {"license": "unknown"},
            "image3.png": {"license": "unknown"},
        }
        result = preflight_check(
            script_text="Word " * 600,
            title="Normal Title Here",
            description="Description over fifty chars. AI-generated content.",
            tags=["test", "video", "content"],
            asset_manifest=manifest,
        )
        violations = [v for v in result["violations"] if v["type"] == "unlicensed_assets"]
        assert any(v["severity"] == "critical" for v in violations)

    def test_all_licensed_clean(self):
        manifest = {
            "image1.png": {"license": "ai_generated", "source": "gemini"},
            "image2.png": {"license": "ai_generated", "source": "gemini"},
        }
        result = preflight_check(
            script_text="Word " * 600,
            title="Normal Title Here",
            description="Description over fifty chars. AI-generated content.",
            tags=["test", "video", "content"],
            asset_manifest=manifest,
        )
        violations = [v for v in result["violations"] if v["type"] in ("unlicensed_assets", "missing_license_info")]
        assert len(violations) == 0


# ── Format Report ──

class TestFormatReport:
    def test_pass_format(self):
        result = preflight_check(
            script_text="Word " * 600,
            title="Clean Title Here For Test",
            description="Clean description over fifty characters. Created with AI voice and visuals.",
            tags=["clean", "test", "video"],
            is_synthetic=True,
        )
        report = format_preflight_report(result)
        assert "Preflight: PASS" in report

    def test_fail_format(self):
        result = {"publishable": False, "violations": [], "required_fixes": [],
                  "risk_scores": {"policy": 0, "copyright": 0, "misleading_metadata": 0, "inauthentic_content": 0},
                  "disclosure": {"containsSyntheticMedia": True}}
        report = format_preflight_report(result)
        assert "Preflight: FAIL" in report
