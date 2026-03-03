#!/usr/bin/env python3
"""
Tests for REPL prelude helpers in python_repl.py

Tests the _build_prelude_namespace() function and each helper:
read_file, write_file, lines, search_code, grep, insert_at, delete_lines.
"""

import os
import sys
from unittest.mock import patch

import pytest

# Enable both feature flags for tests
os.environ["OMG_PYTHON_REPL_ENABLED"] = "true"
os.environ["OMG_REPL_HELPERS_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

import python_repl
from python_repl import (
    _build_prelude_namespace,
    _get_helpers_flag,
    execute_code,
    start_repl_session,
)


@pytest.fixture(autouse=True)
def clean_sessions():
    """Clear all sessions and force stdlib backend for each test."""
    python_repl._sessions.clear()
    python_repl._HAS_JUPYTER = False  # Force stdlib backend
    yield
    for session in list(python_repl._sessions.values()):
        backend = session.get("_backend")
        if backend:
            try:
                backend.close()
            except Exception:
                pass
    python_repl._sessions.clear()
    python_repl._HAS_JUPYTER = None


# --- TestBuildPreludeNamespace (3 tests) ---


class TestBuildPreludeNamespace:
    """Tests for _build_prelude_namespace function."""

    def test_returns_dict(self):
        """Prelude returns a dict of helper functions."""
        ns = _build_prelude_namespace()
        assert isinstance(ns, dict)
        assert len(ns) > 0

    def test_contains_all_helpers(self):
        """Prelude contains all expected helper names."""
        ns = _build_prelude_namespace()
        expected = {"read_file", "write_file", "lines", "search_code", "grep", "insert_at", "delete_lines"}
        assert expected == set(ns.keys())

    def test_flag_disabled_skips_injection(self):
        """When helpers flag is disabled, session namespace has no prelude helpers."""
        with patch.dict(os.environ, {"OMG_REPL_HELPERS_ENABLED": "false"}):
            session = start_repl_session(session_id="no-helpers")
            sid = session["session_id"]
            result = execute_code(sid, "'read_file' in dir()")
            # read_file should NOT be in the namespace
            assert result["result"] == "False"


# --- TestReadFile (2 tests) ---


class TestReadFile:
    """Tests for read_file helper."""

    def test_reads_content(self, tmp_path):
        """read_file returns file content."""
        test_file = tmp_path / "hello.txt"
        test_file.write_text("hello world")
        ns = _build_prelude_namespace()
        result = ns["read_file"](str(test_file))
        assert result == "hello world"

    def test_handles_missing_file(self):
        """read_file returns empty string for missing file."""
        ns = _build_prelude_namespace()
        result = ns["read_file"]("/nonexistent/path/to/file.txt")
        assert result == ""


# --- TestLines (2 tests) ---


class TestLines:
    """Tests for lines helper."""

    def test_returns_list(self, tmp_path):
        """lines returns list of file lines."""
        test_file = tmp_path / "multi.txt"
        test_file.write_text("line1\nline2\nline3")
        ns = _build_prelude_namespace()
        result = ns["lines"](str(test_file))
        assert result == ["line1", "line2", "line3"]

    def test_handles_missing_file(self):
        """lines returns empty list for missing file."""
        ns = _build_prelude_namespace()
        result = ns["lines"]("/nonexistent/path.txt")
        assert result == []


# --- TestSearchCode (2 tests) ---


class TestSearchCode:
    """Tests for search_code helper."""

    def test_finds_matches(self, tmp_path):
        """search_code finds pattern matches in files."""
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "a.py").write_text("def hello():\n    pass\n")
        (sub / "b.py").write_text("def goodbye():\n    pass\n")
        ns = _build_prelude_namespace()
        results = ns["search_code"]("def hello", str(tmp_path))
        assert len(results) >= 1
        assert results[0]["line"] == 1
        assert "def hello" in results[0]["match"]
        assert "file" in results[0]

    def test_handles_no_matches(self, tmp_path):
        """search_code returns empty list when no matches found."""
        (tmp_path / "empty.py").write_text("x = 1\n")
        ns = _build_prelude_namespace()
        results = ns["search_code"]("zzz_nonexistent_pattern", str(tmp_path))
        assert results == []


# --- TestGrepHelper (2 tests) ---


class TestGrepHelper:
    """Tests for grep helper."""

    def test_finds_matches(self):
        """grep returns matching lines from text."""
        text = "apple\nbanana\napricot\ncherry"
        ns = _build_prelude_namespace()
        result = ns["grep"]("^ap", text)
        assert result == ["apple", "apricot"]

    def test_handles_no_matches(self):
        """grep returns empty list when no lines match."""
        text = "hello\nworld"
        ns = _build_prelude_namespace()
        result = ns["grep"]("zzz", text)
        assert result == []


# --- TestInsertDeleteLines (2 tests) ---


class TestInsertDeleteLines:
    """Tests for insert_at and delete_lines helpers."""

    def test_insert_at_works(self):
        """insert_at inserts line at specified index."""
        ns = _build_prelude_namespace()
        original = ["a", "b", "c"]
        result = ns["insert_at"](original, 1, "X")
        assert result == ["a", "X", "b", "c"]
        # Original not mutated
        assert original == ["a", "b", "c"]

    def test_delete_lines_works(self):
        """delete_lines removes lines in range [start, end)."""
        ns = _build_prelude_namespace()
        original = ["a", "b", "c", "d", "e"]
        result = ns["delete_lines"](original, 1, 3)
        assert result == ["a", "d", "e"]
        # Original not mutated
        assert original == ["a", "b", "c", "d", "e"]


# --- TestWriteFile (2 tests) ---


class TestWriteFile:
    """Tests for write_file helper."""

    def test_writes_content(self, tmp_path):
        """write_file creates file with content."""
        target = tmp_path / "output.txt"
        ns = _build_prelude_namespace()
        result = ns["write_file"](str(target), "test content")
        assert result is True
        assert target.read_text() == "test content"

    def test_blocked_in_sandbox(self, tmp_path):
        """write_file returns False when sandbox is enabled."""
        target = tmp_path / "blocked.txt"
        ns = _build_prelude_namespace()
        with patch.dict(os.environ, {"OMG_REPL_SANDBOX_ENABLED": "true"}):
            result = ns["write_file"](str(target), "bad content")
        assert result is False
        assert not target.exists()


# --- TestPreludeIntegration (1 test) ---


class TestPreludeIntegration:
    """Test that prelude is injected into session namespace."""

    @patch.dict(os.environ, {
        "OMG_PYTHON_REPL_ENABLED": "true",
        "OMG_REPL_HELPERS_ENABLED": "true",
    })
    def test_helpers_available_in_session(self):
        """When helpers flag is enabled, helpers are callable in session."""
        session = start_repl_session(session_id="prelude-test")
        sid = session["session_id"]
        result = execute_code(sid, "grep('x', 'ax\\nbx\\ncy')")
        assert result["error"] is None
        assert result["result"] is not None
        assert "ax" in result["result"]
