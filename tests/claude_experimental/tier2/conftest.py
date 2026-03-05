"""Shared fixtures for tier-2 memory tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _enable_memory(monkeypatch, tmp_path):
    """Enable experimental memory feature flag and isolate project dir for all tier2 tests."""
    monkeypatch.setenv("OMG_EXPERIMENTAL_MEMORY_ENABLED", "1")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
