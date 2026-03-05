"""Tests for EpisodicMemory — event recording and recall."""
from __future__ import annotations

import json

import pytest

from claude_experimental.memory.episodic import EpisodicMemory
from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestEpisodicMemory:
    def test_record_and_recall_round_trip(self, tmp_path):
        """Recorded episode is recallable via FTS search."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        em = EpisodicMemory(store)

        mid = em.record("success", "fixed auth bug", "tests pass")
        assert mid > 0

        memories = em.recall("auth", temperature=0.9)
        assert len(memories) >= 1

    def test_temperature_affects_result_count(self, tmp_path):
        """Lower temperature filters more aggressively (higher min_score)."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        em = EpisodicMemory(store)

        # Record 5 events sharing the keyword "deploy" to get varied rank scores
        em.record("success", "deploy v1 completed", "all systems operational")
        em.record("failure", "deploy v2 attempted", "timeout during deploy")
        em.record("decision", "deploy strategy chosen", "blue green deploy")
        em.record("discovery", "deploy issue found", "port conflict in deploy")
        em.record("success", "deploy v3 released", "deploy successful")

        # High temperature (0.9) → min_score=0.1 → more results pass
        high_temp = em.recall("deploy", temperature=0.9, limit=10)
        # Low temperature (0.1) → min_score=0.9 → fewer results pass
        low_temp = em.recall("deploy", temperature=0.1, limit=10)

        assert len(high_temp) >= len(low_temp)
        assert len(high_temp) > 0

    def test_event_type_filter(self, tmp_path):
        """Recall filters by event_type when specified."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        em = EpisodicMemory(store)

        em.record("success", "build first passed", "all green")
        em.record("failure", "build second failed", "timeout")
        em.record("success", "build third passed", "deployed")
        em.record("discovery", "build fourth analyzed", "optimization found")

        # temperature=1.0 → min_score=0.0 so only event_type filter matters
        successes = em.recall("build", temperature=1.0, event_type_filter="success")

        assert len(successes) >= 1
        for s in successes:
            meta = s.get("metadata", "{}")
            if isinstance(meta, str):
                meta = json.loads(meta)
            assert meta.get("event_type") == "success"

    def test_invalid_event_type_raises(self, tmp_path):
        """Invalid event_type in record raises ValueError."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        em = EpisodicMemory(store)

        with pytest.raises(ValueError, match="Invalid event_type"):
            em.record("invalid_type", "context", "outcome")
