# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from runtime.architecture_signal import build_architecture_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Structural tests — keys always present
# ---------------------------------------------------------------------------


def test_returns_summary_artifacts_perf_keys_always(tmp_path: Path) -> None:
    result = build_architecture_signal(str(tmp_path))

    assert "summary" in result
    assert "artifacts" in result
    assert "perf" in result
    assert "fallback" in result
    assert "dependency_graph" in result["artifacts"]
    assert "lsp_diagnostics" in result["artifacts"]
    assert "graph_ms" in result["perf"]
    assert "lsp_ms" in result["perf"]


def test_summary_is_string_and_bounded(tmp_path: Path) -> None:
    result = build_architecture_signal(str(tmp_path))

    assert isinstance(result["summary"], str)
    assert len(result["summary"]) <= 500


def test_perf_values_are_floats(tmp_path: Path) -> None:
    result = build_architecture_signal(str(tmp_path))

    assert isinstance(result["perf"]["graph_ms"], float)
    assert isinstance(result["perf"]["lsp_ms"], float)


# ---------------------------------------------------------------------------
# Fallback behavior — no signals available
# ---------------------------------------------------------------------------


def test_fallback_when_no_signals_available(tmp_path: Path) -> None:
    """No graph plugin, no LSP evidence → fallback result."""
    with mock.patch.dict(os.environ, {"OMG_CODEBASE_VIZ_ENABLED": "0"}, clear=False):
        result = build_architecture_signal(str(tmp_path))

    assert result["fallback"] is True
    assert result["artifacts"]["dependency_graph"] is None
    assert result["artifacts"]["lsp_diagnostics"] is None
    assert result["summary"] == "no architecture signals available"
    assert result["perf"]["graph_ms"] >= 0.0
    assert result["perf"]["lsp_ms"] >= 0.0


def test_does_not_fail_with_empty_project(tmp_path: Path) -> None:
    result = build_architecture_signal(str(tmp_path))

    assert isinstance(result, dict)
    assert "summary" in result
    assert "artifacts" in result
    assert "perf" in result


def test_does_not_fail_with_nonexistent_dir() -> None:
    result = build_architecture_signal("/nonexistent/path/abc123")

    assert isinstance(result, dict)
    assert "summary" in result
    assert result["fallback"] is True


# ---------------------------------------------------------------------------
# CODEBASE_VIZ disabled → dependency_graph is None
# ---------------------------------------------------------------------------


def test_dependency_graph_none_when_codebase_viz_disabled(tmp_path: Path) -> None:
    with mock.patch.dict(os.environ, {"OMG_CODEBASE_VIZ_ENABLED": "0"}, clear=False):
        result = build_architecture_signal(str(tmp_path))

    assert result["artifacts"]["dependency_graph"] is None


# ---------------------------------------------------------------------------
# Graceful fallback when graph plugin unavailable
# ---------------------------------------------------------------------------


def test_graceful_fallback_when_graph_plugin_unavailable(tmp_path: Path) -> None:
    """Even if CODEBASE_VIZ is on, missing graph_builder degrades gracefully."""
    with mock.patch.dict(os.environ, {"OMG_CODEBASE_VIZ_ENABLED": "1"}, clear=False):
        with mock.patch(
            "runtime.architecture_signal._get_feature_flag",
            return_value=True,
        ):
            # Simulate import failure of graph_builder
            with mock.patch(
                "plugins.viz.graph_builder.build_project_graph",
                side_effect=ImportError("no graph_builder"),
            ):
                result = build_architecture_signal(str(tmp_path))

    # Should still return valid structure, not crash
    assert isinstance(result, dict)
    assert "summary" in result
    assert "artifacts" in result


# ---------------------------------------------------------------------------
# LSP diagnostics integration
# ---------------------------------------------------------------------------


def test_lsp_diagnostics_included_when_evidence_exists(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".omg" / "evidence" / "lsp-diagnostics.json",
        {
            "diagnostics": [
                {"severity": "error", "message": "undefined var"},
                {"severity": "warning", "message": "unused import"},
                {"severity": "error", "message": "syntax error"},
            ]
        },
    )

    with mock.patch.dict(os.environ, {"OMG_CODEBASE_VIZ_ENABLED": "0"}, clear=False):
        result = build_architecture_signal(str(tmp_path))

    assert result["artifacts"]["lsp_diagnostics"] is not None
    assert result["fallback"] is False
    assert "2 errors" in result["summary"]
    assert "1 warnings" in result["summary"]
    assert "3 total" in result["summary"]


def test_lsp_diagnostics_none_when_no_evidence(tmp_path: Path) -> None:
    result = build_architecture_signal(str(tmp_path))

    assert result["artifacts"]["lsp_diagnostics"] is None


def test_lsp_handles_malformed_evidence(tmp_path: Path) -> None:
    bad_path = tmp_path / ".omg" / "evidence" / "lsp-diagnostics.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    _ = bad_path.write_text("{not valid json", encoding="utf-8")

    result = build_architecture_signal(str(tmp_path))

    assert isinstance(result, dict)
    assert result["artifacts"]["lsp_diagnostics"] is None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def test_writes_latest_json_state_file(tmp_path: Path) -> None:
    build_architecture_signal(str(tmp_path))

    latest = tmp_path / ".omg" / "state" / "architecture_signal" / "latest.json"
    assert latest.exists()

    data = json.loads(latest.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "artifacts" in data
    assert "perf" in data


# ---------------------------------------------------------------------------
# Graph + LSP combined
# ---------------------------------------------------------------------------


def test_combined_graph_and_lsp_summary(tmp_path: Path) -> None:
    """When both signals available, summary includes both."""
    _write_json(
        tmp_path / ".omg" / "evidence" / "lsp-diagnostics.json",
        {"diagnostics": [{"severity": "warning", "message": "w1"}]},
    )

    # Mock graph builder to return metrics
    mock_result: dict[str, object] = {
        "graph": {"a": ["b"], "b": []},
        "metrics": {
            "module_count": 2,
            "edge_count": 1,
            "max_depth": 1,
            "circular_deps": [],
            "coupling_score": 0.5,
        },
    }

    with mock.patch.dict(os.environ, {"OMG_CODEBASE_VIZ_ENABLED": "1"}, clear=False):
        with mock.patch(
            "runtime.architecture_signal._get_feature_flag",
            return_value=True,
        ):
            with mock.patch(
                "plugins.viz.graph_builder.build_project_graph",
                return_value=mock_result,
            ):
                result = build_architecture_signal(str(tmp_path))

    assert result["fallback"] is False
    assert result["artifacts"]["dependency_graph"] is not None
    assert result["artifacts"]["lsp_diagnostics"] is not None
    assert "graph:" in result["summary"]
    assert "lsp:" in result["summary"]
    assert "2 modules" in result["summary"]
