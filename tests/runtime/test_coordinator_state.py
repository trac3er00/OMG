"""Tests for coordinator state management (NF5b: Shared memory across model switches)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "team_router.py"
_SPEC = importlib.util.spec_from_file_location("runtime_team_router_for_coordinator_tests", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
team_router = importlib.util.module_from_spec(_SPEC)
sys.modules["runtime_team_router_for_coordinator_tests"] = team_router
_SPEC.loader.exec_module(team_router)

save_coordinator_state = team_router.save_coordinator_state
load_coordinator_state = team_router.load_coordinator_state
update_coordinator_state = team_router.update_coordinator_state
build_model_handoff_context = team_router.build_model_handoff_context


class TestSaveCoordinatorState:
    """Tests for save_coordinator_state function."""

    def test_creates_file_in_correct_location(self, tmp_path: Path) -> None:
        """save_coordinator_state creates file at .omg/state/coordinator/<task_id>.json."""
        project_dir = str(tmp_path)
        task_id = "test-task-001"
        state = {"decisions": ["initial decision"], "files_touched": []}

        result_path = save_coordinator_state(project_dir, task_id, state)

        expected_path = tmp_path / ".omg" / "state" / "coordinator" / f"{task_id}.json"
        assert os.path.exists(result_path)
        assert result_path == str(expected_path)

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        """save_coordinator_state creates parent directories if missing."""
        project_dir = str(tmp_path)
        task_id = "nested-task"
        state = {"decisions": ["test"]}

        save_coordinator_state(project_dir, task_id, state)

        assert (tmp_path / ".omg" / "state" / "coordinator").is_dir()

    def test_persists_state_with_metadata(self, tmp_path: Path) -> None:
        """save_coordinator_state adds _saved_at and _task_id metadata."""
        project_dir = str(tmp_path)
        task_id = "meta-task"
        state = {"decisions": ["decision A"], "evidence": {"key": "value"}}

        result_path = save_coordinator_state(project_dir, task_id, state)

        with open(result_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["decisions"] == ["decision A"]
        assert saved["evidence"] == {"key": "value"}
        assert "_saved_at" in saved
        assert saved["_task_id"] == task_id


class TestLoadCoordinatorState:
    """Tests for load_coordinator_state function."""

    def test_reads_back_saved_state(self, tmp_path: Path) -> None:
        """load_coordinator_state returns saved state correctly."""
        project_dir = str(tmp_path)
        task_id = "load-test"
        state = {
            "decisions": ["step 1", "step 2"],
            "files_touched": ["file.py"],
            "model_history": ["claude", "codex"],
        }

        save_coordinator_state(project_dir, task_id, state)
        loaded = load_coordinator_state(project_dir, task_id)

        assert loaded is not None
        assert loaded["decisions"] == ["step 1", "step 2"]
        assert loaded["files_touched"] == ["file.py"]
        assert loaded["model_history"] == ["claude", "codex"]

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """load_coordinator_state returns None when file does not exist."""
        project_dir = str(tmp_path)
        task_id = "nonexistent-task"

        result = load_coordinator_state(project_dir, task_id)

        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        """load_coordinator_state returns None for corrupt JSON files."""
        project_dir = str(tmp_path)
        task_id = "corrupt-task"

        # Create invalid JSON file
        state_dir = tmp_path / ".omg" / "state" / "coordinator"
        state_dir.mkdir(parents=True)
        corrupt_file = state_dir / f"{task_id}.json"
        corrupt_file.write_text("{ invalid json }", encoding="utf-8")

        result = load_coordinator_state(project_dir, task_id)

        assert result is None


class TestUpdateCoordinatorState:
    """Tests for update_coordinator_state function."""

    def test_merges_updates_into_existing_state(self, tmp_path: Path) -> None:
        """update_coordinator_state merges new data into existing state."""
        project_dir = str(tmp_path)
        task_id = "merge-test"
        initial = {"decisions": ["first"], "files_touched": ["a.py"]}

        save_coordinator_state(project_dir, task_id, initial)
        updates = {"decisions": ["second"], "unsolved": ["issue X"]}

        result = update_coordinator_state(project_dir, task_id, updates)

        # Lists should be extended
        assert result["decisions"] == ["first", "second"]
        assert result["files_touched"] == ["a.py"]
        assert result["unsolved"] == ["issue X"]

    def test_creates_state_if_missing(self, tmp_path: Path) -> None:
        """update_coordinator_state creates new state if none exists."""
        project_dir = str(tmp_path)
        task_id = "new-state"
        updates = {"decisions": ["initial decision"], "evidence": {"key": "val"}}

        result = update_coordinator_state(project_dir, task_id, updates)

        assert result["decisions"] == ["initial decision"]
        assert result["evidence"] == {"key": "val"}

    def test_adds_timestamp_to_update_history(self, tmp_path: Path) -> None:
        """update_coordinator_state records timestamps in update_history."""
        project_dir = str(tmp_path)
        task_id = "history-test"
        initial = {"decisions": []}

        save_coordinator_state(project_dir, task_id, initial)
        update_coordinator_state(project_dir, task_id, {"decisions": ["one"]})
        result = update_coordinator_state(project_dir, task_id, {"decisions": ["two"]})

        assert "update_history" in result
        assert len(result["update_history"]) == 2
        assert "timestamp" in result["update_history"][0]
        assert "keys_updated" in result["update_history"][0]

    def test_merges_nested_dicts_shallow(self, tmp_path: Path) -> None:
        """update_coordinator_state shallow-merges dict values."""
        project_dir = str(tmp_path)
        task_id = "dict-merge"
        initial = {"evidence": {"track_a": {"status": "ok"}}}

        save_coordinator_state(project_dir, task_id, initial)
        updates = {"evidence": {"track_b": {"status": "failed"}}}

        result = update_coordinator_state(project_dir, task_id, updates)

        # Both tracks should be present
        assert "track_a" in result["evidence"]
        assert "track_b" in result["evidence"]


class TestBuildModelHandoffContext:
    """Tests for build_model_handoff_context function."""

    def test_codex_target_produces_terse_format(self) -> None:
        """build_model_handoff_context for codex returns terse bullet format."""
        state = {
            "decisions": ["auth fix", "rate limit added"],
            "files_touched": ["auth.py", "api.py"],
            "evidence": {"test_passed": True},
            "unsolved": ["logging issue"],
            "model_history": ["claude", "gemini"],
        }

        result = build_model_handoff_context(state, "codex")

        assert "# Coordinator Handoff (terse)" in result
        assert "## Decisions" in result
        assert "- auth fix" in result
        assert "## Files" in result
        assert "- auth.py" in result
        assert "## Unsolved" in result
        assert "- logging issue" in result
        assert "## Evidence Keys" in result
        assert "## Prior Models" in result

    def test_gemini_target_produces_visual_format(self) -> None:
        """build_model_handoff_context for gemini returns visual-focused format."""
        state = {
            "decisions": ["layout change"],
            "files_touched": ["Button.tsx", "styles.css", "api.py"],
            "evidence": {"snapshot": "path/to/snapshot.png"},
            "unsolved": ["mobile breakpoint"],
            "model_history": ["claude"],
        }

        result = build_model_handoff_context(state, "gemini")

        assert "# Coordinator Handoff (visual context)" in result
        assert "## Files to Review" in result
        # UI files should be categorized
        assert "### UI Components" in result
        assert "Button.tsx" in result
        assert "styles.css" in result
        assert "### Other Files" in result
        assert "api.py" in result
        assert "## Open Questions" in result
        assert "- mobile breakpoint" in result
        assert "## Model Chain" in result
        assert "-> gemini" in result

    def test_default_target_produces_full_format(self) -> None:
        """build_model_handoff_context for unknown target returns full format."""
        state = {
            "decisions": ["decision A"],
            "files_touched": ["file.py"],
            "evidence": {"key": "short value"},
            "unsolved": [],
            "model_history": ["codex"],
        }

        result = build_model_handoff_context(state, "claude")

        assert "# Coordinator State Handoff" in result
        assert "## Decisions" in result
        assert "- decision A" in result
        assert "## Files Touched" in result
        assert "## Evidence" in result
        assert "- key: short value" in result

    def test_handles_empty_state(self) -> None:
        """build_model_handoff_context handles empty state dict."""
        state: dict = {}

        result_codex = build_model_handoff_context(state, "codex")
        result_gemini = build_model_handoff_context(state, "gemini")

        # Should not raise and should contain header
        assert "# Coordinator Handoff (terse)" in result_codex
        assert "# Coordinator Handoff (visual context)" in result_gemini

    def test_limits_output_for_large_state(self) -> None:
        """build_model_handoff_context limits items for large states."""
        state = {
            "decisions": [f"decision {i}" for i in range(20)],
            "files_touched": [f"file{i}.py" for i in range(20)],
            "evidence": {f"key{i}": f"value{i}" for i in range(20)},
            "model_history": [f"model{i}" for i in range(10)],
        }

        result = build_model_handoff_context(state, "codex")

        # Should have limited items (last 5 decisions, last 10 files, etc.)
        assert "decision 15" in result
        assert "decision 19" in result
        # Early decisions should be truncated
        assert "decision 0" not in result
