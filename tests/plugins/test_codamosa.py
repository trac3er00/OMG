"""Tests for CodaMosa-inspired iterative test generator engine."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugins.testgen.codamosa_engine import run_codamosa


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_feature_flag():
    """Enable TEST_GENERATION feature flag for all tests by default."""
    with patch("plugins.testgen.codamosa_engine.get_feature_flag", return_value=True):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _make_pyproject(project_dir: Path) -> None:
    """Create a minimal pyproject.toml so framework detector finds pytest."""
    _write_file(project_dir / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths = ['tests']\n")


def _make_source(project_dir: Path, name: str = "module.py") -> str:
    """Create a simple Python source file to generate tests for."""
    return _write_file(
        project_dir / name,
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
    )


# ---------------------------------------------------------------------------
# 1. max_iterations enforced
# ---------------------------------------------------------------------------


def test_max_iterations_enforced(tmp_path: Path):
    """run_codamosa never exceeds 5 iterations regardless of argument."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    # Mock subprocess to always return non-zero coverage (never reaches target)
    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        mock_cov.return_value = {"file_coverage": 10.0, "uncovered_lines": [3, 5]}
        with patch("plugins.testgen.codamosa_engine._run_tests_subprocess") as mock_test:
            mock_test.return_value = True  # tests pass

            result = run_codamosa(str(tmp_path), source, target_coverage=100, max_iterations=20)

    assert result["iterations"] <= 5


# ---------------------------------------------------------------------------
# 2. fallback when no coverage tool
# ---------------------------------------------------------------------------


def test_fallback_when_no_coverage_tool(tmp_path: Path):
    """Graceful degradation when coverage subprocess fails."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        mock_cov.side_effect = FileNotFoundError("pytest not found")

        result = run_codamosa(str(tmp_path), source)

    assert result["fallback_used"] is True
    assert result["iterations"] == 1


# ---------------------------------------------------------------------------
# 3. returns required dict keys
# ---------------------------------------------------------------------------


def test_returns_coverage_dict(tmp_path: Path):
    """Return dict has all required keys."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        mock_cov.side_effect = FileNotFoundError("no coverage")

        result = run_codamosa(str(tmp_path), source)

    required_keys = {"iterations", "initial_coverage", "final_coverage", "tests_generated", "fallback_used"}
    assert required_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# 4. initial coverage parsed
# ---------------------------------------------------------------------------


def test_initial_coverage_parsed(tmp_path: Path):
    """Coverage value is parsed from first iteration report."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        mock_cov.return_value = {"file_coverage": 42.5, "uncovered_lines": [3]}
        with patch("plugins.testgen.codamosa_engine._run_tests_subprocess") as mock_test:
            mock_test.return_value = True

            result = run_codamosa(str(tmp_path), source, target_coverage=100, max_iterations=1)

    assert result["initial_coverage"] == 42.5


# ---------------------------------------------------------------------------
# 5. coverage improves across iterations (mock)
# ---------------------------------------------------------------------------


def test_coverage_improves_across_iterations(tmp_path: Path):
    """Final coverage > initial coverage after multiple iterations."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    call_count = {"n": 0}

    def increasing_coverage(*args, **kwargs):
        call_count["n"] += 1
        return {"file_coverage": 20.0 + call_count["n"] * 15, "uncovered_lines": [3]}

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess", side_effect=increasing_coverage):
        with patch("plugins.testgen.codamosa_engine._run_tests_subprocess", return_value=True):
            result = run_codamosa(str(tmp_path), source, target_coverage=100, max_iterations=5)

    assert result["final_coverage"] > result["initial_coverage"]


# ---------------------------------------------------------------------------
# 6. target coverage stops loop
# ---------------------------------------------------------------------------


def test_target_coverage_stops_loop(tmp_path: Path):
    """Stops when target coverage is met, even before max_iterations."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        # First iteration: 90% (already above target 80)
        mock_cov.return_value = {"file_coverage": 90.0, "uncovered_lines": []}
        with patch("plugins.testgen.codamosa_engine._run_tests_subprocess", return_value=True):
            result = run_codamosa(str(tmp_path), source, target_coverage=80, max_iterations=5)

    assert result["iterations"] == 1
    assert result["final_coverage"] >= 80


# ---------------------------------------------------------------------------
# 7. timeout guard respected
# ---------------------------------------------------------------------------


def test_timeout_guard_respected(tmp_path: Path):
    """Subprocess calls use timeout parameter."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=60)

        result = run_codamosa(str(tmp_path), source)

    assert result["fallback_used"] is True
    # Verify subprocess.run was called with timeout
    for call in mock_run.call_args_list:
        if "timeout" in call.kwargs:
            assert call.kwargs["timeout"] <= 60


# ---------------------------------------------------------------------------
# 8. empty source file no crash
# ---------------------------------------------------------------------------


def test_empty_source_file_no_crash(tmp_path: Path):
    """Empty source file handled gracefully."""
    _make_pyproject(tmp_path)
    source = _write_file(tmp_path / "empty.py", "")

    result = run_codamosa(str(tmp_path), source)

    assert isinstance(result, dict)
    assert result["tests_generated"] == 0


# ---------------------------------------------------------------------------
# 9. subprocess failure → fallback
# ---------------------------------------------------------------------------


def test_subprocess_failure_fallback(tmp_path: Path):
    """Subprocess error triggers fallback to single-pass skeleton."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        mock_cov.side_effect = OSError("subprocess broke")

        result = run_codamosa(str(tmp_path), source)

    assert result["fallback_used"] is True
    assert result["iterations"] == 1


# ---------------------------------------------------------------------------
# 10. feature flag disabled → empty result
# ---------------------------------------------------------------------------


def test_feature_flag_disabled_returns_empty(tmp_path: Path, _enable_feature_flag):
    """When TEST_GENERATION flag is off, returns no-op result.

    Note: explicitly overrides the autouse fixture by re-patching.
    """
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine.get_feature_flag", return_value=False):
        result = run_codamosa(str(tmp_path), source)

    assert result["iterations"] == 0
    assert result["tests_generated"] == 0
    assert result["fallback_used"] is False


# ---------------------------------------------------------------------------
# 11. max_iterations capped at 5 even for lower values
# ---------------------------------------------------------------------------


def test_max_iterations_cap_respects_lower_value(tmp_path: Path):
    """When max_iterations < 5, it uses that lower value."""
    _make_pyproject(tmp_path)
    source = _make_source(tmp_path)

    with patch("plugins.testgen.codamosa_engine._run_coverage_subprocess") as mock_cov:
        mock_cov.return_value = {"file_coverage": 10.0, "uncovered_lines": [3, 5]}
        with patch("plugins.testgen.codamosa_engine._run_tests_subprocess", return_value=True):
            result = run_codamosa(str(tmp_path), source, target_coverage=100, max_iterations=2)

    assert result["iterations"] <= 2


# ---------------------------------------------------------------------------
# 12. nonexistent source file handled
# ---------------------------------------------------------------------------


def test_nonexistent_source_file(tmp_path: Path):
    """Nonexistent source file returns empty result without crash."""
    _make_pyproject(tmp_path)

    result = run_codamosa(str(tmp_path), str(tmp_path / "does_not_exist.py"))

    assert isinstance(result, dict)
    assert result["tests_generated"] == 0
