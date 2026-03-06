from __future__ import annotations

from pathlib import Path
import types


def test_mcp_lifecycle_exposes_pid_path_and_server_url(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from runtime import mcp_lifecycle

    assert mcp_lifecycle.get_pid_file_path().endswith(".omg/shared-memory/server.pid")
    assert mcp_lifecycle.get_server_url() == "http://127.0.0.1:8765/mcp"
    assert mcp_lifecycle.check_memory_server()["running"] is False


def test_start_memory_server_returns_started_payload_without_spawning_real_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from runtime import mcp_lifecycle

    captured: dict[str, object] = {}

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            self.pid = 43210

    monkeypatch.setattr(mcp_lifecycle.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(mcp_lifecycle, "_wait_for_health", lambda url, timeout=5.0: True)

    result = mcp_lifecycle.start_memory_server()

    assert result["status"] == "started"
    assert result["pid"] == 43210
    assert result["log_path"].endswith(".omg/shared-memory/server.log")
    assert Path(mcp_lifecycle.get_pid_file_path()).read_text(encoding="utf-8") == "43210"
    cmd = list(captured["args"][0])
    joined = " ".join(cmd)
    assert "runtime.mcp_memory_server" in joined
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == str(Path(mcp_lifecycle.__file__).resolve().parents[1])
    env = kwargs["env"]
    assert str(Path(mcp_lifecycle.__file__).resolve().parents[1]) in env["PYTHONPATH"]


def test_check_memory_server_reports_health_and_log_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from runtime import mcp_lifecycle

    monkeypatch.setattr(mcp_lifecycle, "is_server_running", lambda: True)
    monkeypatch.setattr(mcp_lifecycle, "_read_pid", lambda: 9876)
    monkeypatch.setattr(mcp_lifecycle, "_wait_for_health", lambda url, timeout=1.0: True)

    result = mcp_lifecycle.check_memory_server()

    assert result["running"] is True
    assert result["pid"] == 9876
    assert result["url"] == "http://127.0.0.1:8765/mcp"
    assert result["health_ok"] is True
    assert result["log_path"].endswith(".omg/shared-memory/server.log")


def test_mcp_memory_server_tools_are_importable():
    from runtime import mcp_memory_server

    assert callable(mcp_memory_server.get_host)
    assert callable(mcp_memory_server.get_port)
    assert callable(mcp_memory_server.run_server)
