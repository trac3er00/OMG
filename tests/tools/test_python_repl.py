#!/usr/bin/env python3
"""
Tests for python_repl.py

Tests REPL session lifecycle, code execution, streaming output,
and feature flag gating. Uses stdlib backend for deterministic results.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

# Enable feature flag for tests
os.environ["OMG_PYTHON_REPL_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

import python_repl
from python_repl import (
    close_session,
    execute_code,
    get_session,
    list_sessions,
    start_repl_session,
    stream_execute,
)


@pytest.fixture(autouse=True)
def clean_sessions():
    """Clear all sessions and force stdlib backend for each test."""
    python_repl._sessions.clear()
    python_repl._HAS_JUPYTER = False  # Force stdlib backend
    yield
    # Cleanup: close backends and clear sessions
    for session in list(python_repl._sessions.values()):
        backend = session.get("_backend")
        if backend:
            try:
                backend.close()
            except Exception:
                pass
    python_repl._sessions.clear()
    python_repl._HAS_JUPYTER = None  # Reset for next test


# --- TestStartReplSession (4 tests) ---


class TestStartReplSession:
    """Tests for start_repl_session function."""

    def test_creates_session(self):
        """Start a new session and verify it has required keys."""
        result = start_repl_session()
        assert "session_id" in result
        assert "created_at" in result
        assert "last_used" in result
        assert result["exec_count"] == 0
        assert result["backend"] == "stdlib"

    def test_returns_id(self):
        """Session uses the provided session_id."""
        result = start_repl_session(session_id="custom-id-123")
        assert result["session_id"] == "custom-id-123"

    def test_flag_disabled(self):
        """Returns error dict when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_PYTHON_REPL_ENABLED": "false"}):
            result = start_repl_session()
            assert "error" in result
            assert "disabled" in result["error"].lower()

    def test_resumes_existing(self):
        """Resuming an existing session returns the same session_id."""
        s1 = start_repl_session(session_id="reuse-me")
        s2 = start_repl_session(session_id="reuse-me")
        assert s1["session_id"] == s2["session_id"]
        assert s1["created_at"] == s2["created_at"]


# --- TestExecuteCode (5 tests) ---


class TestExecuteCode:
    """Tests for execute_code function."""

    def test_basic_exec(self):
        """Execute a simple assignment statement."""
        session = start_repl_session()
        result = execute_code(session["session_id"], "x = 42")
        assert result["error"] is None
        assert result["exec_count"] == 1

    def test_captures_stdout(self):
        """Stdout from print() is captured."""
        session = start_repl_session()
        result = execute_code(session["session_id"], "print('hello world')")
        assert "hello world" in result["stdout"]

    def test_captures_stderr(self):
        """Stderr output is captured."""
        session = start_repl_session()
        result = execute_code(
            session["session_id"],
            "import sys; print('err_msg', file=sys.stderr)",
        )
        assert "err_msg" in result["stderr"]

    def test_error_handling(self):
        """Runtime errors are captured in the error field."""
        session = start_repl_session()
        result = execute_code(session["session_id"], "1/0")
        assert result["error"] is not None
        assert "ZeroDivisionError" in result["error"]

    def test_flag_disabled(self):
        """Returns error dict when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_PYTHON_REPL_ENABLED": "false"}):
            result = execute_code("any-id", "print('hi')")
            assert "error" in result


# --- TestGetSession (2 tests) ---


class TestGetSession:
    """Tests for get_session function."""

    def test_existing_session(self):
        """Returns session info for an active session."""
        session = start_repl_session(session_id="get-me")
        result = get_session("get-me")
        assert result is not None
        assert result["session_id"] == "get-me"
        assert result["exec_count"] == 0

    def test_nonexistent_session(self):
        """Returns None for a session that doesn't exist."""
        result = get_session("nonexistent")
        assert result is None


# --- TestCloseSession (2 tests) ---


class TestCloseSession:
    """Tests for close_session function."""

    def test_closes_existing(self):
        """Closing an active session returns True and removes it."""
        start_repl_session(session_id="close-me")
        result = close_session("close-me")
        assert result is True
        assert get_session("close-me") is None

    def test_nonexistent_returns_false(self):
        """Closing a nonexistent session returns False."""
        result = close_session("nonexistent")
        assert result is False


# --- TestStreamExecute (2 tests) ---


class TestStreamExecute:
    """Tests for stream_execute generator function."""

    def test_yields_chunks(self):
        """Stream execution yields stdout chunks."""
        session = start_repl_session()
        chunks = list(stream_execute(session["session_id"], "print('streamed')"))
        types = [c["type"] for c in chunks]
        assert "stdout" in types
        stdout_data = [c["data"] for c in chunks if c["type"] == "stdout"]
        assert any("streamed" in d for d in stdout_data)

    def test_flag_disabled(self):
        """Yields error chunk when feature flag is disabled."""
        with patch.dict(os.environ, {"OMG_PYTHON_REPL_ENABLED": "false"}):
            chunks = list(stream_execute("any-id", "print('hi')"))
            assert len(chunks) > 0
            assert chunks[0]["type"] == "error"


# --- TestListSessions ---


class TestListSessions:
    """Additional coverage for list_sessions."""

    def test_lists_active_sessions(self):
        """Lists all active sessions."""
        start_repl_session(session_id="s1")
        start_repl_session(session_id="s2")
        result = list_sessions()
        assert isinstance(result, list)
        assert len(result) == 2
        ids = {s["session_id"] for s in result}
        assert ids == {"s1", "s2"}


# --- TestSessionPersistence ---


class TestSessionPersistence:
    """Tests for session namespace persistence across executions."""

    def test_namespace_persists(self):
        """Variables set in one execution are available in the next."""
        session = start_repl_session(session_id="persist")
        execute_code("persist", "my_var = 99")
        result = execute_code("persist", "print(my_var)")
        assert "99" in result["stdout"]


# --- TestExpressionEval ---


class TestExpressionEval:
    """Tests for expression evaluation returning results."""

    def test_expression_returns_result(self):
        """A bare expression returns its repr in the result field."""
        session = start_repl_session()
        result = execute_code(session["session_id"], "2 + 2")
        assert result["result"] == "4"
        assert result["error"] is None
