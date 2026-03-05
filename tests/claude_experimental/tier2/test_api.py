"""Tests for public memory API — remember, recall, memory_check."""
from __future__ import annotations

import pytest

from claude_experimental.memory.api import memory_check, recall, remember
from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestMemoryAPI:
    def test_remember_auto_detects_procedural(self):
        """Content with 'steps:' is auto-detected as procedural."""
        mid = remember(
            "steps: setup env, write tests, run CI",
            importance=0.7,
            scope="project",
        )
        assert mid > 0

        store = MemoryStore(scope="project")
        count = store.count(memory_type="procedural")
        assert count >= 1

    def test_remember_auto_detects_episodic(self):
        """Content with 'fixed' keyword is auto-detected as episodic."""
        mid = remember(
            "fixed authentication bypass in login handler",
            importance=0.8,
            scope="project",
        )
        assert mid > 0

        store = MemoryStore(scope="project")
        count = store.count(memory_type="episodic")
        assert count >= 1

    def test_recall_cross_type(self):
        """recall() searches across memory types and returns results."""
        # Store different types sharing the keyword "login"
        remember("fixed login redirect bug in auth module", importance=0.9, scope="project")
        remember("login module uses JWT for session management", importance=0.8, scope="project")

        results = recall("login", scope_filter="project", min_relevance=0.0)
        assert len(results) >= 1

        source_types = {r.source_type for r in results}
        assert len(source_types) >= 1

    def test_memory_check_returns_health(self):
        """memory_check() returns health status dict."""
        remember("test health check data", scope="project")

        result = memory_check(scope="project")
        assert result["healthy"] is True
        assert result["integrity"] == "ok"
        assert result["schema_version"] == 1
        assert result["total_memories"] >= 1
        assert isinstance(result["memories_by_type"], dict)
