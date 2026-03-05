"""Import compatibility layer — ensures claude_experimental is importable from any OMG entry point."""
from __future__ import annotations
import os
import sys


def ensure_package_on_path() -> None:
    """Add the OMG project root to sys.path so claude_experimental is importable."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)  # parent of claude_experimental/
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
