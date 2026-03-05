"""Tests for CCG mode execution (dispatch plan → actual agent execution).

Validates that cmd_ccg / execute_ccg_mode actually invoke agents
after the dispatch planning phase, rather than just returning a plan.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# execute_ccg_mode unit tests
# ---------------------------------------------------------------------------


class TestExecuteCcgMode:
    """Unit tests for runtime.team_router.execute_ccg_mode()."""

    @patch("runtime.team_router.execute_agents_parallel")
    def test_returns_dict_with_required_keys(self, mock_parallel: MagicMock) -> None:
        """execute_ccg_mode must return dict with status/phases/model_mix/synthesis."""
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="review auth flow",
            project_dir="/tmp/test",
        )

        assert isinstance(result, dict)
        for key in ("status", "phases", "model_mix"):
            assert key in result, f"Missing key: {key}"

    @patch("runtime.team_router.execute_agents_parallel")
    def test_status_is_ok(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="review auth flow",
            project_dir="/tmp/test",
        )
        assert result["status"] == "ok"

    @patch("runtime.team_router.execute_agents_parallel")
    def test_dispatches_two_tracks(self, mock_parallel: MagicMock) -> None:
        """CCG mode should dispatch exactly 2 parallel tracks (backend + frontend)."""
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        execute_ccg_mode(
            problem="review full stack",
            project_dir="/tmp/test",
        )

        mock_parallel.assert_called_once()
        tasks = mock_parallel.call_args[0][0]
        assert len(tasks) == 2
        agent_names = {t["agent_name"] for t in tasks}
        assert "backend-engineer" in agent_names
        assert "frontend-designer" in agent_names

    @patch("runtime.team_router.execute_agents_parallel")
    def test_passes_project_dir(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        execute_ccg_mode(
            problem="test",
            project_dir="/my/project",
        )

        mock_parallel.assert_called_once()
        assert mock_parallel.call_args[0][1] == "/my/project"

    @patch("runtime.team_router.execute_agents_parallel")
    def test_context_included_in_prompts(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
            context="extra context here",
        )

        tasks = mock_parallel.call_args[0][0]
        for task in tasks:
            assert "extra context here" in task["prompt"]

    @patch("runtime.team_router.execute_agents_parallel")
    def test_files_included_in_prompts(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
            files=["src/app.py", "src/ui.tsx"],
        )

        tasks = mock_parallel.call_args[0][0]
        for task in tasks:
            assert "src/app.py" in task["prompt"]

    @patch("runtime.team_router.execute_agents_parallel")
    def test_phases_include_orchestrator_and_agents(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
        )

        phases = result["phases"]
        assert len(phases) >= 3  # orchestrator + 2 tracks + synthesis
        phase_agents = [p.get("agent") for p in phases]
        assert "claude-orchestrator" in phase_agents
        assert "backend-engineer" in phase_agents
        assert "frontend-designer" in phase_agents

    @patch("runtime.team_router.execute_agents_parallel")
    def test_model_mix_categorises_results(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
        )

        mm = result["model_mix"]
        assert isinstance(mm, dict)
        assert "gpt" in mm
        assert "gemini" in mm
        assert "claude" in mm

    @patch("runtime.team_router.execute_agents_parallel")
    def test_worker_count_is_two(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
        )

        assert result["worker_count"] == 2
        assert result["target_worker_count"] == 2

    @patch("runtime.team_router.execute_agents_parallel")
    def test_parallel_execution_flag(self, mock_parallel: MagicMock) -> None:
        mock_parallel.return_value = self._two_track_results()
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
        )

        assert result["parallel_execution"] is True
        assert result["sequential_execution"] is False

    @patch("runtime.team_router.execute_agents_parallel")
    def test_handles_agent_errors_gracefully(self, mock_parallel: MagicMock) -> None:
        """If agents return errors, execute_ccg_mode should still return ok status."""
        mock_parallel.return_value = [
            {"agent": "backend-engineer", "order": 1, "status": "error", "error": "timeout", "fallback": "claude"},
            {"agent": "frontend-designer", "order": 2, "status": "completed", "exit_code": 0, "output": "ok", "model": "gemini-cli"},
        ]
        from runtime.team_router import execute_ccg_mode

        result = execute_ccg_mode(
            problem="test",
            project_dir="/tmp/test",
        )

        assert result["status"] == "ok"
        assert result["worker_count"] == 2

    # --- helpers ---

    @staticmethod
    def _two_track_results() -> list[dict[str, Any]]:
        return [
            {
                "agent": "backend-engineer",
                "order": 1,
                "status": "completed",
                "exit_code": 0,
                "output": "Backend analysis done",
                "model": "codex-cli",
            },
            {
                "agent": "frontend-designer",
                "order": 2,
                "status": "completed",
                "exit_code": 0,
                "output": "Frontend analysis done",
                "model": "gemini-cli",
            },
        ]


# ---------------------------------------------------------------------------
# cmd_ccg integration (mocked agents, direct function call)
# ---------------------------------------------------------------------------


class TestCmdCcgIntegration:
    """Test that cmd_ccg calls execute_ccg_mode (not just dispatch_team)."""

    @patch("runtime.team_router.execute_agents_parallel")
    def test_cmd_ccg_returns_execution_result(self, mock_parallel: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_parallel.return_value = TestExecuteCcgMode._two_track_results()

        import sys
        sys.path.insert(0, str(ROOT))
        from scripts.omg import cmd_ccg

        args = MagicMock()
        args.problem = "review auth"
        args.context = ""
        args.files = ""
        args.expected_outcome = ""

        rc = cmd_ccg(args)
        assert rc == 0

        captured = capsys.readouterr()
        start = captured.out.find("{")
        assert start >= 0
        out = json.loads(captured.out[start:])

        assert out["status"] == "ok"
        assert "phases" in out
        assert "worker_count" in out
        assert "model_mix" in out

    @patch("runtime.team_router.execute_agents_parallel")
    def test_cmd_ccg_not_just_dispatch_plan(self, mock_parallel: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_parallel.return_value = TestExecuteCcgMode._two_track_results()

        import sys
        sys.path.insert(0, str(ROOT))
        from scripts.omg import cmd_ccg

        args = MagicMock()
        args.problem = "test"
        args.context = ""
        args.files = ""
        args.expected_outcome = ""

        rc = cmd_ccg(args)
        assert rc == 0

        captured = capsys.readouterr()
        start = captured.out.find("{")
        assert start >= 0
        out = json.loads(captured.out[start:])

        assert "schema" not in out or out.get("schema") != "TeamDispatchResult"
        assert "phases" in out
