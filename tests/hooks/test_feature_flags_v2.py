"""Tests for v2.0 feature flags registration (Wave 0 — Task 3)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add hooks to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hooks"))

from _common import get_feature_flag


def test_all_v2_feature_flags_exist_in_settings():
    """Verify all 6 new v2.0 feature flags are registered in settings.json."""
    settings_path = Path(__file__).parent.parent.parent / "settings.json"
    assert settings_path.exists(), f"settings.json not found at {settings_path}"
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    features = settings.get("_omg", {}).get("features", {})
    
    # All 6 new v2.0 flags must exist
    new_flags = [
        "COST_TRACKING",
        "GIT_WORKFLOW",
        "SESSION_ANALYTICS",
        "TEST_GENERATION",
        "DEP_HEALTH",
        "CODEBASE_VIZ",
    ]
    
    for flag in new_flags:
        assert flag in features, f"Feature flag '{flag}' not found in settings.json"


def test_all_v2_feature_flags_default_false():
    """Verify all 6 new v2.0 feature flags default to False."""
    settings_path = Path(__file__).parent.parent.parent / "settings.json"
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    features = settings.get("_omg", {}).get("features", {})
    
    new_flags = [
        "COST_TRACKING",
        "GIT_WORKFLOW",
        "SESSION_ANALYTICS",
        "TEST_GENERATION",
        "DEP_HEALTH",
        "CODEBASE_VIZ",
    ]
    
    for flag in new_flags:
        assert features[flag] is False, f"Feature flag '{flag}' should default to False, got {features[flag]}"


def test_get_feature_flag_returns_false_for_new_flags():
    """Verify get_feature_flag() returns False for all new v2.0 flags."""
    new_flags = [
        "COST_TRACKING",
        "GIT_WORKFLOW",
        "SESSION_ANALYTICS",
        "TEST_GENERATION",
        "DEP_HEALTH",
        "CODEBASE_VIZ",
    ]
    
    for flag in new_flags:
        result = get_feature_flag(flag, default=False)
        assert result is False, f"get_feature_flag('{flag}') should return False, got {result}"


def test_existing_feature_flags_unchanged():
    """Regression check: verify existing feature flags are unchanged."""
    settings_path = Path(__file__).parent.parent.parent / "settings.json"
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    features = settings.get("_omg", {}).get("features", {})
    
    # Existing flags and their expected values
    existing_flags = {
        "memory": False,
        "ralph_loop": True,
        "planning_enforcement": True,
        "compound_learning": False,
        "simplifier": True,
        "model_routing": True,
        "agent_registry": True,
        "circuit_breaker_v2": True,
        "cognitive_modes": True,
        "agent_routing": True,
    }
    
    for flag, expected_value in existing_flags.items():
        assert flag in features, f"Existing flag '{flag}' was removed"
        assert features[flag] == expected_value, (
            f"Existing flag '{flag}' changed from {expected_value} to {features[flag]}"
        )


def test_feature_flags_structure_valid():
    """Verify the _omg.features structure is valid JSON."""
    settings_path = Path(__file__).parent.parent.parent / "settings.json"
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    
    # Should have _omg namespace
    assert "_omg" in settings, "_omg namespace not found in settings.json"
    
    # Should have features dict
    assert "features" in settings["_omg"], "features dict not found in _omg namespace"
    
    # All feature values should be booleans
    features = settings["_omg"]["features"]
    for flag_name, flag_value in features.items():
        assert isinstance(flag_value, bool), (
            f"Feature flag '{flag_name}' has non-boolean value: {flag_value}"
        )
