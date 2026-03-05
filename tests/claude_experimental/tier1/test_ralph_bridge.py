"""Tests for RalphBridge — state file coordination."""
from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from claude_experimental.parallel.ralph_bridge import RalphBridge


@pytest.mark.experimental
class TestRalphBridgeNoState:
    """Behavior when no state files exist (standalone mode)."""

    def test_is_ralph_active_false_by_default(self, tmp_path):
        bridge = RalphBridge(project_dir=str(tmp_path))
        assert bridge.is_ralph_active() is False

    def test_get_ralph_state_empty_dict(self, tmp_path):
        bridge = RalphBridge(project_dir=str(tmp_path))
        assert bridge.get_ralph_state() == {}

    def test_read_results_empty_list(self, tmp_path):
        bridge = RalphBridge(project_dir=str(tmp_path))
        assert bridge.read_results() == []


@pytest.mark.experimental
class TestRalphBridgeStateFiles:
    """Behavior with mock state files via tmp_path."""

    @pytest.fixture
    def bridge(self, tmp_path):
        state_dir = tmp_path / ".omg" / "state"
        state_dir.mkdir(parents=True)
        return RalphBridge(project_dir=str(tmp_path))

    def test_is_ralph_active_true(self, bridge, tmp_path):
        state_file = tmp_path / ".omg" / "state" / "ralph-loop.json"
        state_file.write_text(json.dumps({"active": True, "iteration": 3}))
        assert bridge.is_ralph_active() is True

    def test_is_ralph_active_false_when_inactive(self, bridge, tmp_path):
        state_file = tmp_path / ".omg" / "state" / "ralph-loop.json"
        state_file.write_text(json.dumps({"active": False}))
        assert bridge.is_ralph_active() is False

    def test_get_ralph_state_reads_full_state(self, bridge, tmp_path):
        state_data = {"active": True, "iteration": 5, "goal": "fix tests"}
        state_file = tmp_path / ".omg" / "state" / "ralph-loop.json"
        state_file.write_text(json.dumps(state_data))
        result = bridge.get_ralph_state()
        assert result["iteration"] == 5
        assert result["goal"] == "fix tests"

    def test_write_results(self, bridge):
        success = bridge.write_results([{"job_id": "j1", "status": "completed"}])
        assert success is True
        # Verify file written
        results = bridge.read_results()
        assert len(results) == 1
        assert results[0]["job_id"] == "j1"

    def test_signal_completion(self, bridge):
        success = bridge.signal_completion(
            job_id="job-001",
            status="completed",
            artifacts=[{"content": "output data"}],
        )
        assert success is True
        results = bridge.read_results()
        assert any(r["job_id"] == "job-001" for r in results)

    def test_signal_completion_upserts(self, bridge):
        """Signaling same job_id twice should upsert, not duplicate."""
        bridge.signal_completion("j1", "running")
        bridge.signal_completion("j1", "completed")
        results = bridge.read_results()
        j1_results = [r for r in results if r["job_id"] == "j1"]
        assert len(j1_results) == 1
        assert j1_results[0]["status"] == "completed"

    def test_clear_results(self, bridge):
        bridge.write_results([{"job_id": "j1"}])
        assert len(bridge.read_results()) == 1
        bridge.clear_results()
        assert bridge.read_results() == []

    def test_malformed_state_file_returns_none(self, bridge, tmp_path):
        state_file = tmp_path / ".omg" / "state" / "ralph-loop.json"
        state_file.write_text("not valid json {{{")
        assert bridge.is_ralph_active() is False
        assert bridge.get_ralph_state() == {}
