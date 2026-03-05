"""Feature flag integration for claude_experimental — lazy import from hooks/_common.py."""
from __future__ import annotations
import importlib
import os
import sys


KNOWN_FLAGS: dict[str, str] = {
    "PARALLEL_DISPATCH": "OMG_PARALLEL_DISPATCH_ENABLED",
    "ULTRAWORKER": "OMG_ULTRAWORKER_ENABLED",
    "EXPERIMENTAL_MEMORY": "OMG_EXPERIMENTAL_MEMORY_ENABLED",
    "PATTERN_INTELLIGENCE": "OMG_PATTERN_INTELLIGENCE_ENABLED",
    "ADVANCED_INTEGRATION": "OMG_ADVANCED_INTEGRATION_ENABLED",
}


def _hooks_dir() -> str:
    """Return absolute path to hooks/ dir relative to this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "hooks")


def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """Lazy-import get_feature_flag from hooks/_common.py and call it."""
    hooks_dir = _hooks_dir()
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        common_module = importlib.import_module("_common")
        getter = getattr(common_module, "get_feature_flag", None)
        if callable(getter):
            return bool(getter(flag_name, default))
        return default
    except (ImportError, Exception):
        return default
