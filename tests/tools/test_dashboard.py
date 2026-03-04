"""Tests for tools/dashboard_generator.py — HTML dashboard generation."""

import json
import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.dashboard_generator import generate_dashboard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path, tool_entries=None, cost_entries=None):
    """Create a minimal project dir with optional JSONL ledger data."""
    project_dir = str(tmp_path / "project")
    ledger_dir = os.path.join(project_dir, ".omg", "state", "ledger")
    os.makedirs(ledger_dir, exist_ok=True)

    if tool_entries is not None:
        path = os.path.join(ledger_dir, "tool-ledger.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for entry in tool_entries:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")

    if cost_entries is not None:
        path = os.path.join(ledger_dir, "cost-ledger.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for entry in cost_entries:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")

    return project_dir


SAMPLE_TOOL_ENTRIES = [
    {"ts": "2026-03-04T10:00:00+00:00", "tool": "Read", "file": "main.py", "duration_ms": 50},
    {"ts": "2026-03-04T10:01:00+00:00", "tool": "Write", "file": "main.py", "success": True, "duration_ms": 120},
    {"ts": "2026-03-04T10:02:00+00:00", "tool": "Bash", "command": "pytest", "exit_code": 0, "duration_ms": 3000},
    {"ts": "2026-03-04T10:03:00+00:00", "tool": "Read", "file": "utils.py", "duration_ms": 30},
    {"ts": "2026-03-04T10:04:00+00:00", "tool": "Edit", "file": "utils.py", "success": True, "duration_ms": 80},
]

SAMPLE_COST_ENTRIES = [
    {"ts": "2026-03-04T10:00:00+00:00", "tool": "Read", "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.001, "model": "claude-3", "session_id": "s1"},
    {"ts": "2026-03-04T10:01:00+00:00", "tool": "Write", "tokens_in": 200, "tokens_out": 100, "cost_usd": 0.002, "model": "claude-3", "session_id": "s1"},
    {"ts": "2026-03-04T10:02:00+00:00", "tool": "Bash", "tokens_in": 50, "tokens_out": 500, "cost_usd": 0.008, "model": "claude-3", "session_id": "s1"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDashboardCreatesFile:
    """test_generate_dashboard_creates_html_file"""

    def test_generate_dashboard_creates_html_file(self, tmp_path):
        """Dashboard generates an HTML file at the specified output path."""
        project_dir = _make_project(tmp_path)
        output_path = str(tmp_path / "dashboard.html")

        result = generate_dashboard(project_dir, output_path)

        assert os.path.exists(output_path), "Dashboard HTML file should exist"
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("<!DOCTYPE html>") or "<html" in content


class TestDashboardContainsChartJs:
    """test_dashboard_contains_chartjs_cdn"""

    def test_dashboard_contains_chartjs_cdn(self, tmp_path):
        """Dashboard HTML includes the Chart.js CDN script tag."""
        project_dir = _make_project(tmp_path, SAMPLE_TOOL_ENTRIES, SAMPLE_COST_ENTRIES)
        output_path = str(tmp_path / "dashboard.html")

        generate_dashboard(project_dir, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "cdn.jsdelivr.net/npm/chart.js" in content


class TestDashboardWithEmptyLedgers:
    """test_dashboard_with_empty_ledgers"""

    def test_dashboard_with_empty_ledgers(self, tmp_path):
        """Dashboard generates successfully when ledger files are missing."""
        project_dir = str(tmp_path / "empty_project")
        os.makedirs(project_dir, exist_ok=True)
        # No .omg/state/ledger/ directory at all
        output_path = str(tmp_path / "dashboard.html")

        # Should NOT raise an exception
        result = generate_dashboard(project_dir, output_path)

        assert os.path.exists(output_path), "Dashboard should still be created"
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<html" in content

    def test_dashboard_with_empty_jsonl_files(self, tmp_path):
        """Dashboard handles empty JSONL files without crashing."""
        project_dir = _make_project(tmp_path, tool_entries=[], cost_entries=[])
        output_path = str(tmp_path / "dashboard.html")

        result = generate_dashboard(project_dir, output_path)
        assert os.path.exists(output_path)


class TestDashboardWithSampleData:
    """test_dashboard_with_sample_data"""

    def test_dashboard_with_sample_data(self, tmp_path):
        """Dashboard HTML contains chart data when ledger has entries."""
        project_dir = _make_project(tmp_path, SAMPLE_TOOL_ENTRIES, SAMPLE_COST_ENTRIES)
        output_path = str(tmp_path / "dashboard.html")

        generate_dashboard(project_dir, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Tool names from sample data should appear in the chart data
        assert "Read" in content
        assert "Write" in content
        assert "Bash" in content

    def test_dashboard_contains_cost_data(self, tmp_path):
        """Dashboard includes cost data when cost ledger has entries."""
        project_dir = _make_project(tmp_path, SAMPLE_TOOL_ENTRIES, SAMPLE_COST_ENTRIES)
        output_path = str(tmp_path / "dashboard.html")

        generate_dashboard(project_dir, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Cost values should be present somewhere in the HTML
        assert "0.001" in content or "0.002" in content or "0.008" in content or "0.011" in content


class TestDashboardReturnsOutputPath:
    """test_dashboard_returns_output_path"""

    def test_dashboard_returns_output_path(self, tmp_path):
        """generate_dashboard returns the output_path string."""
        project_dir = _make_project(tmp_path)
        output_path = str(tmp_path / "dashboard.html")

        result = generate_dashboard(project_dir, output_path)

        assert result == output_path

    def test_dashboard_default_output_path(self, tmp_path):
        """generate_dashboard uses default .omg/state/dashboard.html when output_path is None."""
        project_dir = _make_project(tmp_path)

        result = generate_dashboard(project_dir)

        expected = os.path.join(project_dir, ".omg", "state", "dashboard.html")
        assert result == expected
        assert os.path.exists(expected)


class TestDashboardSelfContained:
    """Dashboard should be a single self-contained HTML file."""

    def test_dashboard_is_valid_html(self, tmp_path):
        """Dashboard has proper HTML structure."""
        project_dir = _make_project(tmp_path, SAMPLE_TOOL_ENTRIES, SAMPLE_COST_ENTRIES)
        output_path = str(tmp_path / "dashboard.html")

        generate_dashboard(project_dir, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content
        assert "<script" in content
        # Chart.js is loaded, not inline — CDN reference
        assert "cdn.jsdelivr.net/npm/chart.js" in content
