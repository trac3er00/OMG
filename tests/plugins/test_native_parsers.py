"""Tests for plugins/viz/native_parsers.py — native toolchain dependency parsers."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from typing import Any, Callable, cast
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_native_parsers = importlib.import_module("plugins.viz.native_parsers")
is_toolchain_available = cast(Callable[[str], bool], _native_parsers.is_toolchain_available)
parse_go_native = cast(Callable[[str], dict[str, Any]], _native_parsers.parse_go_native)
parse_typescript_native = cast(
    Callable[[str], dict[str, Any]], _native_parsers.parse_typescript_native
)
parse_rust_native = cast(Callable[[str], dict[str, Any]], _native_parsers.parse_rust_native)


# ---------------------------------------------------------------------------
# Test 1: is_toolchain_available returns True when tool exists
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value="/usr/local/bin/go")
def test_is_toolchain_available_found(mock_which: MagicMock) -> None:
    """is_toolchain_available returns True when shutil.which finds the binary."""
    result = is_toolchain_available("go")
    assert result is True
    mock_which.assert_called_once_with("go")


# ---------------------------------------------------------------------------
# Test 2: is_toolchain_available returns False for nonexistent tool
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value=None)
def test_is_toolchain_available_not_found(mock_which: MagicMock) -> None:
    """is_toolchain_available returns False for a missing binary."""
    result = is_toolchain_available("nonexistent_tool_xyz")
    assert result is False
    mock_which.assert_called_once_with("nonexistent_tool_xyz")


# ---------------------------------------------------------------------------
# Test 3: parse_go_native when go not available returns error dict
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value=None)
def test_parse_go_native_toolchain_missing(mock_which: MagicMock) -> None:
    """parse_go_native returns error dict when go is not installed."""
    result = parse_go_native("/some/project")
    assert "error" in result
    assert result["graph"] == {}
    assert result["accuracy"] == "N/A"


# ---------------------------------------------------------------------------
# Test 4: parse_typescript_native when tsc not available returns error dict
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value=None)
def test_parse_typescript_native_toolchain_missing(mock_which: MagicMock) -> None:
    """parse_typescript_native returns error dict when tsc is not installed."""
    result = parse_typescript_native("/some/project")
    assert "error" in result
    assert result["graph"] == {}
    assert result["accuracy"] == "N/A"


# ---------------------------------------------------------------------------
# Test 5: parse_rust_native when cargo not available returns error dict
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value=None)
def test_parse_rust_native_toolchain_missing(mock_which: MagicMock) -> None:
    """parse_rust_native returns error dict when cargo is not installed."""
    result = parse_rust_native("/some/project")
    assert "error" in result
    assert result["graph"] == {}
    assert result["accuracy"] == "N/A"


# ---------------------------------------------------------------------------
# Test 6: parse_go_native with mocked subprocess returns correct graph
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value="/usr/local/bin/go")
@patch("subprocess.run")
def test_parse_go_native_success(mock_run: MagicMock, mock_which: MagicMock) -> None:
    """parse_go_native parses go list -json output into correct adjacency list."""
    # go list -json outputs concatenated JSON objects (not an array)
    go_output = (
        json.dumps({
            "Dir": "/project/cmd/app",
            "ImportPath": "github.com/user/repo/cmd/app",
            "Imports": ["fmt", "os", "github.com/user/repo/pkg/util"],
        })
        + "\n"
        + json.dumps({
            "Dir": "/project/pkg/util",
            "ImportPath": "github.com/user/repo/pkg/util",
            "Imports": ["strings"],
        })
    )
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=go_output,
        stderr="",
    )

    result = parse_go_native("/project")

    assert result["language"] == "go"
    assert result["accuracy"] == "native-95%"
    graph = result["graph"]
    assert "github.com/user/repo/cmd/app" in graph
    assert "github.com/user/repo/pkg/util" in graph
    assert "fmt" in graph["github.com/user/repo/cmd/app"]
    assert "github.com/user/repo/pkg/util" in graph["github.com/user/repo/cmd/app"]
    assert "strings" in graph["github.com/user/repo/pkg/util"]


# ---------------------------------------------------------------------------
# Test 7: Graceful handling of subprocess timeout
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value="/usr/local/bin/go")
@patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["go"], timeout=30))
def test_parse_go_native_timeout(mock_run: MagicMock, mock_which: MagicMock) -> None:
    """parse_go_native handles subprocess timeout gracefully."""
    result = parse_go_native("/some/project")
    assert "error" in result
    assert result["graph"] == {}
    assert "timeout" in result["error"].lower() or "timed out" in result["error"].lower()


# ---------------------------------------------------------------------------
# Test 8: Return format consistency — all parsers return graph+accuracy keys
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value=None)
def test_return_format_consistency(mock_which: MagicMock) -> None:
    """All parsers always return dict with 'graph' and 'accuracy' keys."""
    for parser_fn in [parse_go_native, parse_typescript_native, parse_rust_native]:
        result = parser_fn("/nonexistent")
        assert "graph" in result, f"{parser_fn.__name__} missing 'graph' key"
        assert "accuracy" in result, f"{parser_fn.__name__} missing 'accuracy' key"
        assert isinstance(result["graph"], dict), f"{parser_fn.__name__} graph not a dict"


# ---------------------------------------------------------------------------
# Test 9: parse_typescript_native with mocked subprocess returns file list
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value="/usr/local/bin/tsc")
@patch("subprocess.run")
def test_parse_typescript_native_success(mock_run: MagicMock, mock_which: MagicMock) -> None:
    """parse_typescript_native extracts module names from tsc --listFiles output."""
    tsc_output = (
        "/project/src/index.ts\n"
        "/project/src/utils/helper.ts\n"
        "/project/node_modules/typescript/lib/lib.es5.d.ts\n"
    )
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=tsc_output,
        stderr="",
    )

    result = parse_typescript_native("/project")

    assert result["language"] == "typescript"
    assert result["accuracy"] == "native-95%"
    graph = result["graph"]
    # node_modules files should be excluded
    for key in graph:
        assert "node_modules" not in key


# ---------------------------------------------------------------------------
# Test 10: parse_rust_native with mocked subprocess returns crate deps
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value="/usr/local/bin/cargo")
@patch("subprocess.run")
def test_parse_rust_native_success(mock_run: MagicMock, mock_which: MagicMock) -> None:
    """parse_rust_native extracts crate dependencies from cargo metadata."""
    cargo_output = json.dumps({
        "packages": [
            {
                "name": "my-crate",
                "version": "0.1.0",
                "dependencies": [
                    {"name": "serde", "kind": None},
                    {"name": "tokio", "kind": None},
                ],
            },
        ],
        "workspace_members": ["my-crate 0.1.0 (path+file:///project)"],
    })
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=cargo_output,
        stderr="",
    )

    result = parse_rust_native("/project")

    assert result["language"] == "rust"
    assert result["accuracy"] == "native-95%"
    graph = result["graph"]
    assert "my-crate" in graph
    assert "serde" in graph["my-crate"]
    assert "tokio" in graph["my-crate"]


# ---------------------------------------------------------------------------
# Test 11: parse_rust_native handles subprocess non-zero exit
# ---------------------------------------------------------------------------
@patch("shutil.which", return_value="/usr/local/bin/cargo")
@patch("subprocess.run")
def test_parse_rust_native_nonzero_exit(mock_run: MagicMock, mock_which: MagicMock) -> None:
    """parse_rust_native handles non-zero exit code gracefully."""
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="error: could not find `Cargo.toml`",
    )

    result = parse_rust_native("/project")

    assert "error" in result
    assert result["graph"] == {}
