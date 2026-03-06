"""Tests for runtime/mcp_lifecycle.py — MCP server lifecycle manager."""
from __future__ import annotations

import os
import signal
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runtime.mcp_lifecycle import (
    check_memory_server,
    ensure_memory_server,
    get_pid_file_path,
    get_server_url,
    is_server_running,
    start_memory_server,
    stop_memory_server,
)


@pytest.fixture(autouse=True)
def _mock_server_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock runtime.mcp_memory_server to avoid FastMCP import chain."""
    mock_mod = types.ModuleType("runtime.mcp_memory_server")
    mock_mod.get_host = lambda: "127.0.0.1"  # type: ignore[attr-defined]
    mock_mod.get_port = lambda: 8765  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "runtime.mcp_memory_server", mock_mod)


# -- get_pid_file_path -----------------------------------------------


def test_get_pid_file_path_returns_correct_path() -> None:
    path = get_pid_file_path()
    assert path.endswith("server.pid")
    assert ".omg" in path
    assert "shared-memory" in path


# -- get_server_url --------------------------------------------------


def test_get_server_url_format() -> None:
    url = get_server_url()
    assert url == "http://127.0.0.1:8765/mcp"


# -- is_server_running -----------------------------------------------


def test_is_server_running_false_when_no_pid_file(tmp_path: Path) -> None:
    with patch(
        "runtime.mcp_lifecycle.get_pid_file_path",
        return_value=str(tmp_path / "nonexistent.pid"),
    ):
        assert is_server_running() is False


def test_is_server_running_false_when_pid_invalid(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("not_a_number")
    with patch(
        "runtime.mcp_lifecycle.get_pid_file_path",
        return_value=str(pid_file),
    ):
        assert is_server_running() is False


def test_is_server_running_false_when_process_dead(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("999999")
    with patch(
        "runtime.mcp_lifecycle.get_pid_file_path",
        return_value=str(pid_file),
    ):
        with patch("os.kill", side_effect=ProcessLookupError):
            assert is_server_running() is False


def test_is_server_running_true_when_process_alive(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("12345")
    with patch(
        "runtime.mcp_lifecycle.get_pid_file_path",
        return_value=str(pid_file),
    ):
        with patch("os.kill", return_value=None):
            assert is_server_running() is True


# -- start_memory_server ---------------------------------------------


def test_start_memory_server_returns_already_running() -> None:
    with patch("runtime.mcp_lifecycle.is_server_running", return_value=True):
        result = start_memory_server()
    assert result["status"] == "already_running"
    assert "url" in result


def test_start_memory_server_starts_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    mock_proc = MagicMock()
    mock_proc.pid = 42
    mock_proc.poll.return_value = None

    with patch("runtime.mcp_lifecycle.is_server_running", return_value=False), \
         patch("runtime.mcp_lifecycle.get_pid_file_path", return_value=str(pid_file)), \
         patch("subprocess.Popen", return_value=mock_proc), \
         patch("runtime.mcp_lifecycle._wait_for_health", return_value=True):
        result = start_memory_server()

    assert result["status"] == "started"
    assert result["pid"] == 42
    assert "url" in result
    assert pid_file.read_text() == "42"


def test_start_memory_server_returns_error_on_failure(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"

    with patch("runtime.mcp_lifecycle.is_server_running", return_value=False), \
         patch("runtime.mcp_lifecycle.get_pid_file_path", return_value=str(pid_file)), \
         patch("subprocess.Popen", side_effect=OSError("cannot start")):
        result = start_memory_server()

    assert result["status"] == "error"
    assert "message" in result


# -- stop_memory_server ----------------------------------------------


def test_stop_memory_server_not_running() -> None:
    with patch("runtime.mcp_lifecycle.is_server_running", return_value=False):
        result = stop_memory_server()
    assert result["status"] == "not_running"


def test_stop_memory_server_sends_sigterm(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("54321")

    with patch("runtime.mcp_lifecycle.get_pid_file_path", return_value=str(pid_file)), \
         patch("runtime.mcp_lifecycle.is_server_running", return_value=True), \
         patch("os.kill") as mock_kill, \
         patch("runtime.mcp_lifecycle._wait_for_exit", return_value=True):
        result = stop_memory_server()

    mock_kill.assert_any_call(54321, signal.SIGTERM)
    assert result["status"] == "stopped"
    assert result["pid"] == 54321


def test_stop_memory_server_removes_pid_file(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("54321")

    with patch("runtime.mcp_lifecycle.get_pid_file_path", return_value=str(pid_file)), \
         patch("runtime.mcp_lifecycle.is_server_running", return_value=True), \
         patch("os.kill"), \
         patch("runtime.mcp_lifecycle._wait_for_exit", return_value=True):
        stop_memory_server()

    assert not pid_file.exists()


# -- check_memory_server ---------------------------------------------


def test_check_memory_server_not_running() -> None:
    with patch("runtime.mcp_lifecycle.is_server_running", return_value=False):
        result = check_memory_server()
    assert result["running"] is False
    assert result["url"] is None
    assert result["pid"] is None


def test_check_memory_server_running(tmp_path: Path) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("12345")

    with patch("runtime.mcp_lifecycle.is_server_running", return_value=True), \
         patch("runtime.mcp_lifecycle.get_pid_file_path", return_value=str(pid_file)):
        result = check_memory_server()

    assert result["running"] is True
    assert result["url"] is not None
    assert result["pid"] == 12345


# -- ensure_memory_server --------------------------------------------


def test_ensure_memory_server_already_running() -> None:
    with patch("runtime.mcp_lifecycle.is_server_running", return_value=True):
        result = ensure_memory_server()
    assert result["status"] == "already_running"
    assert "url" in result


def test_ensure_memory_server_starts_if_not_running() -> None:
    expected: dict[str, Any] = {
        "status": "started",
        "pid": 99,
        "url": "http://127.0.0.1:8765/mcp",
    }
    with patch("runtime.mcp_lifecycle.is_server_running", return_value=False), \
         patch("runtime.mcp_lifecycle.start_memory_server", return_value=expected):
        result = ensure_memory_server()

    assert result["status"] == "started"
    assert result["pid"] == 99
