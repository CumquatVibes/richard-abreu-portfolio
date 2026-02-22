"""Preflight compliance gate for YouTube publishing.

Checks before every upload:
1. Misleading metadata — title/thumbnail claims must be supported by script
2. Advertiser-friendliness — flag sensitive topics/language
3. Synthetic content disclosure — ensure AI content is properly disclosed
4. License registry — verify all assets have documented licenses
5. Packaging coherence — title + thumbnail + description alignment

Returns a structured verdict: publishable (bool) + risk scores + required fixes.
"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_REGISTRY_PATH = os.path.join(BASE_DIR, "output", "license_registry.json")

# Topics that require human review before publishing
SENSITIVE_TOPICS = {
    "medical", "health advice", "medication", "diagnosis", "treatment",
    "legal advice", "lawsuit", "court", "attorney",
    "financial advice", "investment", "trading signal", "guaranteed returns",
    "weapons", "firearms", "explosives",
    "minors", "children", "child safety",
    "self-harm", "suicide", "eating disorder",
    "hate speech", "slurs", "discrimination",
    "conspiracy", "disinformation",
    "election", "voting", "political candidate",
}

# Words/phrases that signal advertiser-unfriendly content
ADVERTISER_RISK_TERMS = {
    "kill", "murder", "death", "dead body", "gore", "blood",
    "drugs", "cocaine", "heroin", "meth",
    "sex", "sexual", "pornography", "nude",
    "terrorist", "terrorism", "bomb", "shooting",
    "school shooting", "mass shooting",
    "rape", "assault",
    "slur", "n-word", "f-word",
}

# Clickbait patterns that may violate misleading metadata policy
CLICKBAIT_PATTERNS = [
    r"you won't believe",
    r"doctors hate",
    r"one weird trick",
    r"this changes everything",
    r"secret they don't want you to know",
    r"banned",
    r"\d+\s*(million|billion)\s*dollar",
    r"free money",
    r"get rich quick",
    r"100%\s*guaranteed",
    r"cure for",
]


def preflight_check(script_text, title, description, tags, thumbnail_concept=None,
                    asset_manifest=None, is_synthetic=True):
    """Run full preflight compliance check before publishing.

    Args:
        script_text: Full script content
        title: Video title
        description: Video description
        tags: List of tags
        thumbnail_concept: Description of thumbnail content (optional)
        asset_manifest: Dict of {asset_name: license_info} (optional)
        is_synthetic: Whether content uses AI-generated voice/visuals (default True)

    Returns:
        dict with keys:
            publishable (bool): Whether the video can be published
            violations (list): Detected issues with type/evidence/severity
            required_fixes (list): Actions needed before publishing
            risk_scores (dict): 0-1 scores for policy/copyright/misleading/inauthentic
            disclosure (dict): Required disclosure flags
    """
    result = {
        "publishable": True,
        "violations": [],
        "required_fixes": [],
        "risk_scores": {
            "policy": 0.0,
            "copyright": 0.0,
            "misleading_metadata": 0.0,
            "inauthentic_content": 0.0,
        },
        "disclosure": {
            "containsSyntheticMedia": is_synthetic,
        },
    }

    # 1. Misleading metadata check
    _check_misleading_metadata(result, script_text, title, description, thumbnail_concept)

    # 2. Advertiser-friendliness check
    _check_advertiser_friendly(result, title, description, tags, thumbnail_concept)

    # 3. Sensitive topic check
    _check_sensitive_topics(result, script_text, title, description)

    # 4. Synthetic disclosure check
    _check_synthetic_disclosure(result, is_synthetic, title, description)

    # 5. License registry check
    _check_licenses(result, asset_manifest)

    # 6. Basic quality gates
    _check_quality_gates(result, script_text, title, description, tags)

    # Determine publishability
    has_critical = any(v["severity"] == "critical" for v in result["violations"])
    high_risk = any(score > 0.7 for score in result["risk_scores"].values())

    if has_critical or high_risk:
        result["publishable"] = False

    return result


def _check_misleading_metadata(result, script_text, title, description, thumbnail_concept):
    """Check if title/thumbnail promise content not present in script."""
    title_lower = title.lower()
    script_lower = script_text.lower()

    # Check for numeric claims in title (e.g., "7 Tricks", "10 Ways")
    number_match = re.search(r'(\d+)\s+(tricks?|ways?|steps?|secrets?|tips?|reasons?|facts?|signs?|habits?|rules?|methods?|strategies?|techniques?|lessons?|things?)', title_lower)
    if number_match:
        claimed_count = int(number_match.group(1))
        # Look for numbered items in script
        items_found = len(re.findall(r'(?:^|\n)\s*(?:\d+[\.\):]|#{1,3}\s*\d+|number\s+\d+)', script_lower))
        if items_found > 0 and items_found < claimed_count * 0.5:
            result["violations"].append({
                "type": "misleading_metadata",
                "evidence": f"Title claims {claimed_count} items but script appears to have ~{items_found}",
                "severity": "warning",
            })
            result["risk_scores"]["misleading_metadata"] = max(
                result["risk_scores"]["misleading_metadata"], 0.4
            )

    # Check clickbait patterns
    for pattern in CLICKBAIT_PATTERNS:
        if re.search(pattern, title_lower):
            result["violations"].append({
                "type": "misleading_metadata",
                "evidence": f"Clickbait pattern detected in title: '{pattern}'",
                "severity": "warning",
            })
            result["risk_scores"]["misleading_metadata"] = max(
                result["risk_scores"]["misleading_metadata"], 0.5
            )
            break  # One clickbait warning is enough

    # Check thumbnail text claims vs script
    if thumbnail_concept:
        thumb_lower = thumbnail_concept.lower()
        # If thumbnail mentions specific claims, check they exist in script
        for claim_word in ["proof", "exposed", "caught", "leaked", "shocking"]:
            if claim_word in thumb_lower and claim_word not in script_lower:
                result["violations"].append({
                    "type": "misleading_metadata",
                    "evidence": f"Thumbnail uses '{claim_word}' but script doesn't support this claim",
                    "severity": "warning",
                })
                result["risk_scores"]["misleading_metadata"] = max(
                    result["risk_scores"]["misleading_metadata"], 0.6
                )


def _check_advertiser_friendly(result, title, description, tags, thumbnail_concept):
    """Check for advertiser-unfriendly content in metadata."""
    all_text = f"{title} {description} {' '.join(tags or [])} {thumbnail_concept or ''}".lower()

    risk_terms_found = []
    for term in ADVERTISER_RISK_TERMS:
        if term in all_text:
            risk_terms_found.append(term)

    if risk_terms_found:
        severity = "critical" if len(risk_terms_found) >= 3 else "warning"
        result["violations"].append({
            "type": "advertiser_unfriendly",
            "evidence": f"Risk terms in metadata: {', '.join(risk_terms_found[:5])}",
            "severity": severity,
        })
        risk_level = min(0.3 + len(risk_terms_found) * 0.15, 1.0)
        result["risk_scores"]["policy"] = max(result["risk_scores"]["policy"], risk_level)

        if severity == "critical":
            result["required_fixes"].append(
                "Remove or rephrase advertiser-unfriendly terms in title/description/tags"
            )


def _check_sensitive_topics(result, script_text, title, description):
    """Flag sensitive topics that may need human review."""
    all_text = f"{title} {description} {script_text}".lower()

    found_topics = []
    for topic in SENSITIVE_TOPICS:
        if topic in all_text:
            found_topics.append(topic)

    if found_topics:
        result["violations"].append({
            "type": "sensitive_topic",
            "evidence": f"Sensitive topics detected: {', '.join(found_topics[:5])}",
            "severity": "warning",
        })
        result["risk_scores"]["policy"] = max(
            result["risk_scores"]["policy"],
            min(0.2 + len(found_topics) * 0.1, 0.8)
        )


def _check_synthetic_disclosure(result, is_synthetic, title, description):
    """Ensure AI-generated content is properly disclosed."""
    if not is_synthetic:
        return

    # Check if description mentions AI/synthetic content
    desc_lower = (description or "").lower()
    has_disclosure = any(phrase in desc_lower for phrase in [
        "ai-generated", "ai generated", "created with ai",
        "artificial intelligence", "ai voice", "ai narration",
        "generated using", "made with ai", "ai-assisted",
    ])

    if not has_disclosure:
        result["violations"].append({
            "type": "missing_synthetic_disclosure",
            "evidence": "AI-generated content but no disclosure in description",
            "severity": "warning",
        })
        result["required_fixes"].append(
            "Add AI content disclosure to video description (e.g., 'Created with AI voice and visuals')"
        )
        result["risk_scores"]["policy"] = max(result["risk_scores"]["policy"], 0.3)

    result["disclosure"]["containsSyntheticMedia"] = True


def _check_licenses(result, asset_manifest):
    """Verify all assets have documented licenses."""
    if not asset_manifest:
        # No manifest = unknown license status
        result["violations"].append({
            "type": "missing_license_info",
            "evidence": "No asset license manifest provided",
            "severity": "warning",
        })
        result["risk_scores"]["copyright"] = max(result["risk_scores"]["copyright"], 0.3)
        return

    unlicensed = []
    weak_license = []

    for asset_name, license_info in asset_manifest.items():
        if not license_info or license_info.get("license") == "unknown":
            unlicensed.append(asset_name)
        elif license_info.get("license") == "creative_commons" and not license_info.get("attribution"):
            weak_license.append(asset_name)

    if unlicensed:
        result["violations"].append({
            "type": "unlicensed_assets",
            "evidence": f"Assets without license: {', '.join(unlicensed[:5])}",
            "severity": "critical" if len(unlicensed) > 2 else "warning",
        })
        result["risk_scores"]["copyright"] = max(
            result["risk_scores"]["copyright"],
            min(0.4 + len(unlicensed) * 0.15, 1.0)
        )
        result["required_fixes"].append(
            f"Document licenses for: {', '.join(unlicensed[:5])}"
        )

    if weak_license:
        result["violations"].append({
            "type": "missing_attribution",
            "evidence": f"CC assets missing attribution: {', '.join(weak_license[:5])}",
            "severity": "warning",
        })
        result["required_fixes"].append(
            f"Add attribution for Creative Commons assets: {', '.join(weak_license[:5])}"
        )


def _check_quality_gates(result, script_text, title, description, tags):
    """Basic quality gates for publishing readiness."""
    # Title length
    if len(title) > 100:
        result["violations"].append({
            "type": "quality",
            "evidence": f"Title too long ({len(title)} chars, max 100)",
            "severity": "warning",
        })
        result["required_fixes"].append("Shorten title to under 100 characters")

    if len(title) < 10:
        result["violations"].append({
            "type": "quality",
            "evidence": f"Title too short ({len(title)} chars)",
            "severity": "warning",
        })

    # Description minimum
    if not description or len(description) < 50:
        result["violations"].append({
            "type": "quality",
            "evidence": "Description is too short or missing",
            "severity": "warning",
        })
        result["required_fixes"].append("Add a meaningful description (50+ chars)")

    # Tags check
    if not tags or len(tags) < 3:
        result["violations"].append({
            "type": "quality",
            "evidence": f"Too few tags ({len(tags or [])})",
            "severity": "info",
        })

    # Script word count
    word_count = len(script_text.split())
    if word_count < 500:
        result["violations"].append({
            "type": "quality",
            "evidence": f"Script very short ({word_count} words)",
            "severity": "warning",
        })
        result["risk_scores"]["inauthentic_content"] = max(
            result["risk_scores"]["inauthentic_content"], 0.4
        )


def load_license_registry():
    """Load the asset license registry from disk."""
    if os.path.exists(LICENSE_REGISTRY_PATH):
        with open(LICENSE_REGISTRY_PATH) as f:
            return json.load(f)
    return {}


def save_license_registry(registry):
    """Save the asset license registry to disk."""
    os.makedirs(os.path.dirname(LICENSE_REGISTRY_PATH), exist_ok=True)
    with open(LICENSE_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


def register_asset(asset_name, license_type, source=None, attribution=None, expiry=None):
    """Register an asset's license information.

    Args:
        asset_name: Unique asset identifier (filename or URL)
        license_type: e.g. "youtube_audio_library", "creative_commons", "purchased", "ai_generated"
        source: Where the asset came from
        attribution: Required attribution text (for CC assets)
        expiry: License expiry date if applicable
    """
    registry = load_license_registry()
    registry[asset_name] = {
        "license": license_type,
        "source": source,
        "attribution": attribution,
        "expiry": expiry,
    }
    save_license_registry(registry)
    return registry[asset_name]


def format_preflight_report(result):
    """Format a preflight result as a readable string."""
    lines = []
    status = "PASS" if result["publishable"] else "FAIL"
    lines.append(f"Preflight: {status}")

    if result["violations"]:
        lines.append(f"  Violations ({len(result['violations'])}):")
        for v in result["violations"]:
            icon = {"critical": "X", "warning": "!", "info": "i"}[v["severity"]]
            lines.append(f"    [{icon}] {v['type']}: {v['evidence']}")

    if result["required_fixes"]:
        lines.append(f"  Required fixes:")
        for fix in result["required_fixes"]:
            lines.append(f"    > {fix}")

    lines.append(f"  Risk scores: " + ", ".join(
        f"{k}={v:.2f}" for k, v in result["risk_scores"].items()
    ))

    if result["disclosure"]["containsSyntheticMedia"]:
        lines.append(f"  Disclosure: containsSyntheticMedia=true")

    return "\n".join(lines)
