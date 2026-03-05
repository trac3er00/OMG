"""Performance regression suite for OMG v2.0 hooks and plugins.

Benchmarks all new v2.0 components against their performance budgets:
  - PreToolUse hooks:  <100ms
  - PostToolUse hooks: <200ms
  - Stop hooks:        <15s per check

Uses time.perf_counter() for high-resolution timing.
Uses tmp_path fixtures for all filesystem operations.
Mocks all subprocess/HTTP calls — no real external I/O.
"""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure project root is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from hooks._token_counter import estimate_tokens
from hooks._cost_ledger import append_cost_entry
from hooks.secret_audit import mask_secret_path, log_secret_access
from plugins.viz.graph_builder import build_project_graph
from plugins.viz.diagram_generator import generate_mermaid
from plugins.viz.regex_parser import parse_js_imports
from plugins.viz.native_parsers import is_toolchain_available


# ---------------------------------------------------------------------------
# Helpers — generate realistic test data
# ---------------------------------------------------------------------------

def _make_python_source(lines: int) -> str:
    """Generate realistic Python source of `lines` lines."""
    parts = [
        "import os",
        "import sys",
        "import json",
        "from pathlib import Path",
        "",
        "",
        "def process_data(items: list[dict]) -> dict:",
        '    """Process data items and return summary."""',
        "    result = {}",
        "    for item in items:",
        '        key = item.get("name", "unknown")',
        "        value = item.get(\"value\", 0)",
        "        if key in result:",
        "            result[key] += value",
        "        else:",
        "            result[key] = value",
        "    return result",
        "",
        "",
        "class DataHandler:",
        '    """Handles data transformation and validation."""',
        "",
        "    def __init__(self, config: dict) -> None:",
        "        self.config = config",
        "        self._cache: dict = {}",
        "",
        "    def validate(self, data: dict) -> bool:",
        '        required = self.config.get("required_fields", [])',
        "        return all(f in data for f in required)",
        "",
    ]
    # Repeat to reach target lines
    source_lines: list[str] = []
    while len(source_lines) < lines:
        source_lines.extend(parts)
    return "\n".join(source_lines[:lines])


def _make_js_source(lines: int) -> str:
    """Generate realistic JS/TS source of `lines` lines."""
    parts = [
        "import React from 'react';",
        "import { useState, useEffect } from 'react';",
        "import axios from 'axios';",
        "import { Button } from '@/components/ui/button';",
        "import styles from './Component.module.css';",
        "",
        "const API_URL = process.env.REACT_APP_API_URL;",
        "",
        "export function DataTable({ items, onSelect }) {",
        "  const [loading, setLoading] = useState(false);",
        "  const [data, setData] = useState([]);",
        "",
        "  useEffect(() => {",
        "    setLoading(true);",
        "    axios.get(API_URL + '/data')",
        "      .then(res => setData(res.data))",
        "      .catch(err => console.error(err))",
        "      .finally(() => setLoading(false));",
        "  }, []);",
        "",
        "  if (loading) return <div>Loading...</div>;",
        "",
        "  return (",
        "    <div className={styles.container}>",
        "      {data.map(item => (",
        '        <Button key={item.id} onClick={() => onSelect(item)}>',
        "          {item.name}",
        "        </Button>",
        "      ))}",
        "    </div>",
        "  );",
        "}",
        "",
    ]
    source_lines: list[str] = []
    while len(source_lines) < lines:
        source_lines.extend(parts)
    return "\n".join(source_lines[:lines])


def _make_secret_paths(count: int) -> list[str]:
    """Generate a mix of secret and non-secret file paths."""
    patterns = [
        "/app/src/main.py",
        "/app/.env",
        "/app/.env.production",
        "/app/.env.example",
        "/app/config/database.yml",
        "/home/user/.ssh/id_rsa",
        "/app/credentials.json",
        "/app/src/utils.py",
        "/app/.aws/config",
        "/app/secrets/api_key.txt",
        "/app/src/components/Button.tsx",
        "/app/tokens.json",
        "/app/key.pem",
        "/app/.kube/config",
        "/app/src/index.ts",
    ]
    result: list[str] = []
    while len(result) < count:
        result.extend(patterns)
    return result[:count]


def _create_python_project(root, num_files: int) -> None:
    """Create a fake Python project with `num_files` .py files in tmp_path."""
    src_dir = root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    # Create .omg/state/ for graph persistence
    (root / ".omg" / "state").mkdir(parents=True, exist_ok=True)

    for i in range(num_files):
        subdir = src_dir / f"pkg{i // 10}"
        subdir.mkdir(parents=True, exist_ok=True)
        init_file = subdir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")

        module_file = subdir / f"mod{i}.py"
        # Each file imports a few modules for realistic edges
        imports = [
            "import os",
            "import sys",
            "import json",
        ]
        # Add cross-references to earlier modules
        if i > 0:
            prev_pkg = f"pkg{(i - 1) // 10}"
            prev_mod = f"mod{i - 1}"
            imports.append(f"from src.{prev_pkg}.{prev_mod} import process_data")

        body = "\n".join(imports) + "\n\ndef process_data(x):\n    return x\n"
        module_file.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Performance budget constants (from hooks/_common.py)
# ---------------------------------------------------------------------------

BUDGET_PRE_TOOL_MS = 100    # PreToolUse hooks
BUDGET_POST_TOOL_MS = 200   # PostToolUse hooks
BUDGET_STOP_MS = 15000      # Stop hooks per check
BUDGET_TOOLCHAIN_MS = 50    # Toolchain availability check
BUDGET_GRAPH_MS = 5000      # Graph builder


# ===========================================================================
# TEST 1: estimate_tokens — 1000-line input (<100ms)
# ===========================================================================

class TestTokenCounterPerformance:
    """Benchmark estimate_tokens against PreToolUse budget (<100ms)."""

    def test_estimate_tokens_1000_lines(self) -> None:
        """estimate_tokens(tier=2) on 1000-line Python source < 100ms."""
        text = _make_python_source(1000)
        assert len(text.splitlines()) >= 1000

        start = time.perf_counter()
        result = estimate_tokens(text, tier=2)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result > 0, "Token count must be positive"
        assert elapsed_ms < BUDGET_PRE_TOOL_MS, (
            f"estimate_tokens(1000 lines) took {elapsed_ms:.1f}ms > {BUDGET_PRE_TOOL_MS}ms budget"
        )

    # ===================================================================
    # TEST 2: estimate_tokens — 10000-line input (<100ms)
    # ===================================================================

    def test_estimate_tokens_10000_lines(self) -> None:
        """estimate_tokens(tier=2) on 10000-line Python source < 100ms."""
        text = _make_python_source(10000)
        assert len(text.splitlines()) >= 10000

        start = time.perf_counter()
        result = estimate_tokens(text, tier=2)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result > 0, "Token count must be positive"
        assert elapsed_ms < BUDGET_PRE_TOOL_MS, (
            f"estimate_tokens(10000 lines) took {elapsed_ms:.1f}ms > {BUDGET_PRE_TOOL_MS}ms budget"
        )


# ===========================================================================
# TEST 3-4: Cost ledger append (<200ms)
# ===========================================================================

class TestCostLedgerPerformance:
    """Benchmark append_cost_entry against PostToolUse budget (<200ms)."""

    def test_append_single_entry(self, tmp_path) -> None:
        """append_cost_entry for a single entry < 200ms."""
        (tmp_path / ".omg" / "state" / "ledger").mkdir(parents=True)

        entry = {
            "ts": "2026-03-04T10:00:00+00:00",
            "tool": "Read",
            "tokens_in": 1500,
            "tokens_out": 200,
            "cost_usd": 0.0045,
            "model": "claude-sonnet-4-20250514",
            "session_id": "ses_perf_test",
        }

        start = time.perf_counter()
        append_cost_entry(str(tmp_path), entry)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < BUDGET_POST_TOOL_MS, (
            f"append_cost_entry(1 entry) took {elapsed_ms:.1f}ms > {BUDGET_POST_TOOL_MS}ms budget"
        )
        # Verify it actually wrote
        ledger = tmp_path / ".omg" / "state" / "ledger" / "cost-ledger.jsonl"
        assert ledger.exists()

    def test_append_100_entries(self, tmp_path) -> None:
        """append_cost_entry for 100 sequential entries < 200ms."""
        (tmp_path / ".omg" / "state" / "ledger").mkdir(parents=True)

        entries = [
            {
                "ts": f"2026-03-04T10:{i:02d}:00+00:00",
                "tool": f"Tool_{i}",
                "tokens_in": 1000 + i,
                "tokens_out": 100 + i,
                "cost_usd": 0.003 + (i * 0.0001),
                "model": "claude-sonnet-4-20250514",
                "session_id": f"ses_{i}",
            }
            for i in range(100)
        ]

        start = time.perf_counter()
        for entry in entries:
            append_cost_entry(str(tmp_path), entry)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < BUDGET_POST_TOOL_MS, (
            f"append_cost_entry(100 entries) took {elapsed_ms:.1f}ms > {BUDGET_POST_TOOL_MS}ms budget"
        )


# ===========================================================================
# TEST 5-6: Secret audit scan (<200ms)
# ===========================================================================

class TestSecretAuditPerformance:
    """Benchmark secret audit scanning against PostToolUse budget (<200ms)."""

    def test_mask_secret_path_1000_paths(self) -> None:
        """mask_secret_path over 1000 file paths < 200ms."""
        paths = _make_secret_paths(1000)
        assert len(paths) == 1000

        start = time.perf_counter()
        results = [mask_secret_path(p) for p in paths]
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify some were actually redacted
        redacted_count = sum(1 for r in results if r == "[REDACTED]")
        assert redacted_count > 0, "Should have redacted some paths"
        assert elapsed_ms < BUDGET_POST_TOOL_MS, (
            f"mask_secret_path(1000 paths) took {elapsed_ms:.1f}ms > {BUDGET_POST_TOOL_MS}ms budget"
        )

    def test_mask_secret_path_10000_paths(self) -> None:
        """mask_secret_path over 10000 file paths < 200ms."""
        paths = _make_secret_paths(10000)
        assert len(paths) == 10000

        start = time.perf_counter()
        results = [mask_secret_path(p) for p in paths]
        elapsed_ms = (time.perf_counter() - start) * 1000

        redacted_count = sum(1 for r in results if r == "[REDACTED]")
        assert redacted_count > 0, "Should have redacted some paths"
        assert elapsed_ms < BUDGET_POST_TOOL_MS, (
            f"mask_secret_path(10000 paths) took {elapsed_ms:.1f}ms > {BUDGET_POST_TOOL_MS}ms budget"
        )


# ===========================================================================
# TEST 7: Graph builder — 50-file Python project (<5s)
# ===========================================================================

class TestGraphBuilderPerformance:
    """Benchmark build_project_graph against Stop budget (<5s)."""

    def test_build_graph_50_files(self, tmp_path) -> None:
        """build_project_graph on 50-file Python project < 5s."""
        _create_python_project(tmp_path, 50)

        # Enable the feature flag for this test
        with patch.dict(os.environ, {"OMG_CODEBASE_VIZ_ENABLED": "1"}):
            start = time.perf_counter()
            result = build_project_graph(str(tmp_path))
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(result, dict)
        graph = result.get("graph", {})
        assert len(graph) > 0, "Graph should contain modules"
        assert elapsed_ms < BUDGET_GRAPH_MS, (
            f"build_project_graph(50 files) took {elapsed_ms:.1f}ms > {BUDGET_GRAPH_MS}ms budget"
        )


# ===========================================================================
# TEST 8: Diagram generator — 100-node graph (<100ms)
# ===========================================================================

class TestDiagramGeneratorPerformance:
    """Benchmark generate_mermaid against PreToolUse budget (<100ms)."""

    def test_generate_mermaid_100_nodes(self) -> None:
        """generate_mermaid() on 100-node graph < 100ms."""
        # Build a 100-node graph with realistic edges
        graph: dict[str, list[str]] = {}
        for i in range(100):
            deps = []
            # Each node depends on 2-3 previous nodes
            if i > 0:
                deps.append(f"module_{i - 1}")
            if i > 5:
                deps.append(f"module_{i - 5}")
            if i > 10:
                deps.append(f"module_{i - 10}")
            graph[f"module_{i}"] = deps

        assert len(graph) == 100

        start = time.perf_counter()
        result = generate_mermaid(graph)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) > 0, "Mermaid output should not be empty"
        assert result.startswith("graph TD"), "Should be a valid Mermaid graph"
        assert elapsed_ms < BUDGET_PRE_TOOL_MS, (
            f"generate_mermaid(100 nodes) took {elapsed_ms:.1f}ms > {BUDGET_PRE_TOOL_MS}ms budget"
        )


# ===========================================================================
# TEST 9: Regex parser — 500-line JS file (<100ms)
# ===========================================================================

class TestRegexParserPerformance:
    """Benchmark parse_js_imports against PreToolUse budget (<100ms)."""

    def test_parse_js_imports_500_lines(self, tmp_path) -> None:
        """parse_js_imports() on 500-line JS file < 100ms."""
        js_source = _make_js_source(500)
        js_file = tmp_path / "component.tsx"
        js_file.write_text(js_source, encoding="utf-8")

        start = time.perf_counter()
        result = parse_js_imports(str(js_file))
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert "imports" in result
        assert len(result["imports"]) > 0, "Should find imports"
        assert elapsed_ms < BUDGET_PRE_TOOL_MS, (
            f"parse_js_imports(500 lines) took {elapsed_ms:.1f}ms > {BUDGET_PRE_TOOL_MS}ms budget"
        )


# ===========================================================================
# TEST 10: Native parser — toolchain check (<50ms)
# ===========================================================================

class TestNativeParserPerformance:
    """Benchmark is_toolchain_available against tight budget (<50ms)."""

    def test_is_toolchain_available_speed(self) -> None:
        """is_toolchain_available() completes < 50ms."""
        # Test with a common binary (python3 is guaranteed to exist)
        start = time.perf_counter()
        result = is_toolchain_available("python3")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(result, bool)
        assert elapsed_ms < BUDGET_TOOLCHAIN_MS, (
            f"is_toolchain_available() took {elapsed_ms:.1f}ms > {BUDGET_TOOLCHAIN_MS}ms budget"
        )

    def test_is_toolchain_available_missing_binary(self) -> None:
        """is_toolchain_available() for missing binary completes < 50ms."""
        start = time.perf_counter()
        result = is_toolchain_available("nonexistent_binary_xyz_12345")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result is False
        assert elapsed_ms < BUDGET_TOOLCHAIN_MS, (
            f"is_toolchain_available(missing) took {elapsed_ms:.1f}ms > {BUDGET_TOOLCHAIN_MS}ms budget"
        )
