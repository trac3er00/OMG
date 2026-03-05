"""Tests for ProceduralMemory — task decomposition and success tracking."""
from __future__ import annotations

import json

import pytest

from claude_experimental.memory.procedural import ProceduralMemory
from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestProceduralMemory:
    def test_store_and_find_procedure(self, tmp_path):
        """Stored procedure is findable via task description."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        pm = ProceduralMemory(store)

        mid = pm.store_procedure(
            task_type="authentication",
            steps=["setup oauth", "add tokens", "test flow"],
            prerequisites=["Python 3.10+"],
        )
        assert mid > 0

        procedures = pm.find_procedure("authentication")
        assert len(procedures) >= 1
        assert procedures[0]["task_type"] == "authentication"
        assert "setup oauth" in procedures[0]["steps"]

    def test_record_outcome_updates_success_rate(self, tmp_path):
        """Recording outcomes updates success rate via EMA."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        pm = ProceduralMemory(store)

        mid = pm.store_procedure(
            task_type="deployment",
            steps=["build", "test", "deploy"],
            success_rate=0.5,
        )

        # Record success: new_rate = 0.8 * 0.5 + 0.2 * 1.0 = 0.6
        pm.record_outcome(mid, success=True)

        memory = store.get_by_id(mid)
        assert memory is not None
        content = json.loads(str(memory["content"]))
        assert abs(content["success_rate"] - 0.6) < 0.01
        assert content["use_count"] == 1

    def test_get_low_success_procedures(self, tmp_path):
        """Procedures with low success rates are flagged for revision."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        pm = ProceduralMemory(store)

        pm.store_procedure(
            task_type="testing",
            steps=["write tests", "run suite"],
            success_rate=0.9,
        )
        pm.store_procedure(
            task_type="debugging",
            steps=["reproduce", "isolate", "fix"],
            success_rate=0.1,
        )

        flagged = pm.get_low_success_procedures(threshold=0.3)
        assert len(flagged) == 1
        assert flagged[0]["task_type"] == "debugging"
