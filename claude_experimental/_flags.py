"""Feature flag integration for claude_experimental — lazy import from hooks/_common.py."""
from __future__ import annotations
import os
import sys


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
        from _common import get_feature_flag as _get  # type: ignore[import]
        return bool(_get(flag_name, default))
    except (ImportError, Exception):
        return default
