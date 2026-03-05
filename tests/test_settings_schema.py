"""Validate that settings.json uses the canonical flag names that the code actually reads.

hooks/_common.py resolves get_feature_flag(flag_name) by looking up
settings["_omg"]["features"][flag_name] directly. The key must exactly match
the string passed to get_feature_flag().

  memory/__init__.py  → get_feature_flag("EXPERIMENTAL_MEMORY")
  integration/__init__.py → get_feature_flag("ADVANCED_INTEGRATION")
"""
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETTINGS_PATH = os.path.join(_ROOT, "settings.json")


def _features() -> dict:
    with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)
    return settings.get("_omg", {}).get("features", {})


def test_experimental_memory_flag_present():
    """settings.json must use EXPERIMENTAL_MEMORY (not REFLECTIVE_MEMORY)."""
    features = _features()
    assert "EXPERIMENTAL_MEMORY" in features, (
        "settings.json is missing EXPERIMENTAL_MEMORY — "
        "memory/__init__.py reads this key; REFLECTIVE_MEMORY is a stale name"
    )
    assert "REFLECTIVE_MEMORY" not in features, "Stale key REFLECTIVE_MEMORY still in settings.json"


def test_advanced_integration_flag_present():
    """settings.json must use ADVANCED_INTEGRATION (not INTEGRATION_BRIDGE)."""
    features = _features()
    assert "ADVANCED_INTEGRATION" in features, (
        "settings.json is missing ADVANCED_INTEGRATION — "
        "integration/__init__.py reads this key; INTEGRATION_BRIDGE is a stale name"
    )
    assert "INTEGRATION_BRIDGE" not in features, "Stale key INTEGRATION_BRIDGE still in settings.json"
