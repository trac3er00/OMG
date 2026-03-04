"""Tests for plugins/viz/graph_builder.py — unified multi-language dependency graph."""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, cast

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_graph_builder = importlib.import_module("plugins.viz.graph_builder")
build_project_graph = cast(
    Callable[[str], dict[str, Any]], _graph_builder.build_project_graph
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


@pytest.fixture(autouse=True)
def _enable_codebase_viz(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable CODEBASE_VIZ feature flag for all tests."""
    monkeypatch.setenv("OMG_CODEBASE_VIZ_ENABLED", "1")


# --- Test 1: Python-only project ---
def test_build_python_only_project(tmp_path: Path) -> None:
    """build_project_graph returns correct graph for Python-only projects."""
    _write(tmp_path / "app.py", "import os\nimport sys\n")
    _write(tmp_path / "util.py", "from pathlib import Path\n")

    result = build_project_graph(str(tmp_path))
    graph = result["graph"]

    assert "app" in graph
    assert "util" in graph
    assert "os" in graph["app"]
    assert "sys" in graph["app"]
    assert "pathlib" in graph["util"]


# --- Test 2: JS-only project ---
def test_build_js_only_project(tmp_path: Path) -> None:
    """build_project_graph returns correct graph for JS-only projects."""
    _write(tmp_path / "index.js", "import React from 'react'\n")
    _write(tmp_path / "utils.ts", "import { helper } from './helper'\n")

    result = build_project_graph(str(tmp_path))
    graph = result["graph"]

    assert "index" in graph
    assert "utils" in graph
    assert "react" in graph["index"]
    assert "./helper" in graph["utils"]


# --- Test 3: Mixed Python+JS project ---
def test_build_mixed_project(tmp_path: Path) -> None:
    """build_project_graph includes both Python and JS modules."""
    _write(tmp_path / "main.py", "import os\n")
    _write(tmp_path / "app.js", "import express from 'express'\n")

    result = build_project_graph(str(tmp_path))
    graph = result["graph"]

    assert "main" in graph
    assert "app" in graph
    assert "os" in graph["main"]
    assert "express" in graph["app"]
    assert result["metrics"]["module_count"] == 2


# --- Test 4: Graph metrics computed correctly ---
def test_graph_metrics_computed(tmp_path: Path) -> None:
    """Metrics include module_count, edge_count, max_depth, circular_deps, coupling_score."""
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import c\n")
    _write(tmp_path / "c.py", "")

    result = build_project_graph(str(tmp_path))
    metrics = result["metrics"]

    assert metrics["module_count"] == 3
    assert metrics["edge_count"] == 2
    assert isinstance(metrics["max_depth"], int)
    assert isinstance(metrics["circular_deps"], list)
    assert isinstance(metrics["coupling_score"], (int, float))
    # coupling_score = edge_count / module_count = 2/3 ≈ 0.67
    assert abs(metrics["coupling_score"] - 2 / 3) < 0.01


# --- Test 5: Circular dependency detection ---
def test_circular_dependency_detection(tmp_path: Path) -> None:
    """Circular dependencies are detected and listed in metrics."""
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import a\n")

    result = build_project_graph(str(tmp_path))
    metrics = result["metrics"]

    assert len(metrics["circular_deps"]) > 0
    flat = set()
    for cycle in metrics["circular_deps"]:
        flat.update(cycle)
    assert "a" in flat
    assert "b" in flat


# --- Test 6: Persistence to .omg/state/dependency-graph.json ---
def test_persistence_to_json(tmp_path: Path) -> None:
    """Graph + metrics are persisted to .omg/state/dependency-graph.json."""
    _write(tmp_path / "m.py", "import os\n")

    result = build_project_graph(str(tmp_path))

    graph_path = tmp_path / ".omg" / "state" / "dependency-graph.json"
    assert graph_path.exists()

    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    assert payload["graph"] == result["graph"]
    assert payload["metrics"] == result["metrics"]


# --- Test 7: Incremental update ---
def test_incremental_update(tmp_path: Path) -> None:
    """Subsequent builds pick up file changes; unchanged files reuse cache."""
    _write(tmp_path / "a.py", "import os\n")
    _write(tmp_path / "b.py", "import sys\n")

    result1 = build_project_graph(str(tmp_path))
    assert "os" in result1["graph"]["a"]

    # Modify a.py — ensure mtime advances
    time.sleep(0.05)
    _write(tmp_path / "a.py", "import json\n")

    result2 = build_project_graph(str(tmp_path))
    # Updated import reflected
    assert "json" in result2["graph"]["a"]
    # Unchanged file still present
    assert "sys" in result2["graph"]["b"]


# --- Test 8: Empty project directory ---
def test_empty_project_dir(tmp_path: Path) -> None:
    """Empty project directory returns empty graph and zero metrics."""
    result = build_project_graph(str(tmp_path))

    assert result["graph"] == {}
    assert result["metrics"]["module_count"] == 0
    assert result["metrics"]["edge_count"] == 0
    assert result["metrics"]["coupling_score"] == 0.0


# --- Test 9: Nonexistent project directory (graceful) ---
def test_nonexistent_project_dir(tmp_path: Path) -> None:
    """Nonexistent directory is handled gracefully, no crash."""
    result = build_project_graph(str(tmp_path / "nonexistent"))

    assert result["graph"] == {}
    assert result["metrics"]["module_count"] == 0
