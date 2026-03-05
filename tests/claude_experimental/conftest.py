"""Shared test fixtures for claude_experimental tests."""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

# Ensure project root is on sys.path so claude_experimental is importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary SQLite database file for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    return str(db_path)


@pytest.fixture
def feature_flag_enabled(monkeypatch):
    """Factory fixture: enable a specific feature flag via env var for the test."""

    def _enable(flag_name: str):
        env_key = f"OMG_{flag_name.upper()}_ENABLED"
        monkeypatch.setenv(env_key, "1")

    return _enable


@pytest.fixture
def feature_flag_disabled(monkeypatch):
    """Factory fixture: disable a specific feature flag via env var for the test."""

    def _disable(flag_name: str):
        env_key = f"OMG_{flag_name.upper()}_ENABLED"
        monkeypatch.setenv(env_key, "0")

    return _disable


@pytest.fixture
def mock_job_factory():
    """Create a mock job dict for testing job lifecycle."""

    def _make(job_id="test-job-001", agent_name="omg-architect", worktree=None):
        return {
            "job_id": job_id,
            "agent_name": agent_name,
            "prompt": "test prompt",
            "status": "queued",
            "worktree": worktree,
            "created_at": 0.0,
        }

    return _make
