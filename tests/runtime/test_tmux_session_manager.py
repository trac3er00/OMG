"""Tests for runtime/tmux_session_manager.py."""
from __future__ import annotations

import importlib.util
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load module via path to avoid import path issues
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MOD_PATH = _REPO_ROOT / "runtime" / "tmux_session_manager.py"
spec = importlib.util.spec_from_file_location("tmux_session_manager", _MOD_PATH)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
TmuxSessionManager = _mod.TmuxSessionManager

TMUX_AVAILABLE = shutil.which("tmux") is not None


def test_tmux_session_manager_instantiation():
    """TmuxSessionManager instantiates without errors."""
    mgr = TmuxSessionManager()
    assert mgr.session_prefix == "omg"


def test_is_tmux_available_returns_bool():
    """is_tmux_available() returns a boolean, never raises."""
    mgr = TmuxSessionManager()
    result = mgr.is_tmux_available()
    assert isinstance(result, bool)


def test_make_session_name_format():
    """make_session_name produces correct format."""
    mgr = TmuxSessionManager()
    name = mgr.make_session_name("codex")
    assert name == "omg-codex"


def test_make_session_name_with_unique_id():
    """make_session_name includes unique_id when provided."""
    mgr = TmuxSessionManager()
    name = mgr.make_session_name("codex", unique_id="abc123")
    assert name == "omg-codex-abc123"


def test_make_session_name_unique_ids_differ():
    """Two calls with different unique_ids produce different names."""
    mgr = TmuxSessionManager()
    name1 = mgr.make_session_name("test", unique_id="aaa")
    name2 = mgr.make_session_name("test", unique_id="bbb")
    assert name1 != name2


def test_extract_command_result_parses_marker_and_exit_code():
    """Captured tmux output should parse into deterministic output + exit code."""
    mgr = TmuxSessionManager()
    marker = "__OMG_DONE_test__"
    parsed = mgr._extract_command_result(
        "analysis line\nfinal line\n__OMG_DONE_test__::7\n",
        marker,
    )
    assert parsed["output"] == "analysis line\nfinal line"
    assert parsed["exit_code"] == 7
    assert parsed["completed"] is True


def test_extract_command_result_handles_missing_marker():
    """Missing marker should preserve output and report incomplete state."""
    mgr = TmuxSessionManager()
    parsed = mgr._extract_command_result("still running\n", "__OMG_DONE_missing__")
    assert parsed["output"] == "still running"
    assert parsed["exit_code"] is None
    assert parsed["completed"] is False


def test_graceful_when_tmux_not_available():
    """All methods return gracefully when tmux is not on PATH."""
    mgr = TmuxSessionManager()
    with patch.object(mgr, "is_tmux_available", return_value=False):
        assert mgr.session_exists("omg-test") is False
        assert mgr.create_session("omg-test") is False
        assert mgr.kill_session("omg-test") is False
        assert mgr.send_command("omg-test", "echo hi") == ""
        assert mgr.cleanup_stale_sessions() == 0


def test_send_command_quotes_argv_before_dispatch():
    mgr = TmuxSessionManager()
    calls: list[list[str]] = []
    sentinel = "__OMG_DONE_deadbeef__"

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["tmux", "capture-pane"]:
            return subprocess.CompletedProcess(args, 0, f"ok\n{sentinel}\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    with patch.object(mgr, "is_tmux_available", return_value=True), \
         patch.object(_mod.uuid, "uuid4", return_value=type("FakeUUID", (), {"hex": "deadbeef"})()), \
         patch.object(_mod.subprocess, "run", side_effect=fake_run), \
         patch.object(_mod.time, "sleep", return_value=None):
        output = mgr.send_command("omg-test", ["codex", "exec", "--json", "quote ' and space"], timeout=1)

    assert output == "ok"
    assert calls[0] == [
        "tmux",
        "send-keys",
        "-t",
        "omg-test",
        shlex.join(["codex", "exec", "--json", "quote ' and space"]),
        "Enter",
    ]


@pytest.mark.skipif(not TMUX_AVAILABLE, reason="tmux not available")
def test_session_lifecycle_create_exists_kill():
    """Full lifecycle: create, verify exists, kill, verify gone."""
    mgr = TmuxSessionManager()
    name = mgr.make_session_name("test", unique_id="lifecycle1")
    # Clean up first in case prior test left a session
    if mgr.session_exists(name):
        mgr.kill_session(name)
    try:
        assert mgr.create_session(name), "create_session failed"
        assert mgr.session_exists(name), "session not found after create"
        assert mgr.kill_session(name), "kill_session failed"
        assert not mgr.session_exists(name), "session still exists after kill"
    finally:
        # Safety cleanup
        if mgr.session_exists(name):
            mgr.kill_session(name)


@pytest.mark.skipif(not TMUX_AVAILABLE, reason="tmux not available")
def test_send_command_captures_output():
    """send_command sends echo and captures output."""
    mgr = TmuxSessionManager()
    name = mgr.make_session_name("test", unique_id="sendcmd1")
    if mgr.session_exists(name):
        mgr.kill_session(name)
    try:
        mgr.create_session(name)
        output = mgr.send_command(name, "echo hello_from_test", timeout=30)
        assert "hello_from_test" in output
    finally:
        if mgr.session_exists(name):
            mgr.kill_session(name)


@pytest.mark.skipif(not TMUX_AVAILABLE, reason="tmux not available")
def test_cleanup_stale_sessions():
    """cleanup_stale_sessions kills all omg-* sessions."""
    mgr = TmuxSessionManager()
    name1 = mgr.make_session_name("test", unique_id="cleanup1")
    name2 = mgr.make_session_name("test", unique_id="cleanup2")
    try:
        mgr.create_session(name1)
        mgr.create_session(name2)
        assert mgr.session_exists(name1)
        assert mgr.session_exists(name2)
        killed = mgr.cleanup_stale_sessions()
        assert killed >= 2
        assert not mgr.session_exists(name1)
        assert not mgr.session_exists(name2)
    finally:
        for n in [name1, name2]:
            if mgr.session_exists(n):
                mgr.kill_session(n)
