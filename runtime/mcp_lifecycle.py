"""MCP server lifecycle manager — start/stop/health/ensure."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_pid_file_path() -> str:
    return str(Path.home() / ".omg" / "shared-memory" / "server.pid")


def get_log_file_path() -> str:
    return str(Path.home() / ".omg" / "shared-memory" / "server.log")


def get_server_url() -> str:
    from runtime.mcp_memory_server import get_host, get_port

    return f"http://{get_host()}:{get_port()}/mcp"


def _read_pid() -> int | None:
    try:
        return int(Path(get_pid_file_path()).read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def is_server_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _wait_for_health(url: str, timeout: float = 5.0) -> bool:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def _wait_for_exit(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except (ProcessLookupError, PermissionError):
            return True
    return False


def start_memory_server() -> dict[str, Any]:
    if is_server_running():
        state = check_memory_server()
        return {
            "status": "already_running",
            "url": get_server_url(),
            "pid": state.get("pid"),
            "log_path": get_log_file_path(),
        }

    pid_path = Path(get_pid_file_path())
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(get_log_file_path())
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        root = _project_root()
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            f"{root}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else str(root)
        )
        launch_cmd = [
            sys.executable,
            "-c",
            "from runtime.mcp_memory_server import run_server; run_server()",
        ]
        with open(log_path, "ab") as log_handle:
            proc = subprocess.Popen(
                launch_cmd,
                cwd=str(root),
                env=env,
                stdout=log_handle,
                stderr=log_handle,
            )
        pid_path.write_text(str(proc.pid), encoding="utf-8")

        health_url = get_server_url().replace("/mcp", "/health")
        if _wait_for_health(health_url):
            return {
                "status": "started",
                "pid": proc.pid,
                "url": get_server_url(),
                "log_path": str(log_path),
            }
        return {
            "status": "error",
            "message": "Server did not respond within timeout",
            "log_path": str(log_path),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "log_path": str(log_path)}


def stop_memory_server() -> dict[str, Any]:
    if not is_server_running():
        return {"status": "not_running"}

    pid = _read_pid()
    if pid is None:
        return {"status": "not_running"}

    try:
        os.kill(pid, signal.SIGTERM)
        _wait_for_exit(pid)
        pid_path = Path(get_pid_file_path())
        if pid_path.exists():
            pid_path.unlink()
        return {"status": "stopped", "pid": pid}
    except ProcessLookupError:
        pid_path = Path(get_pid_file_path())
        if pid_path.exists():
            pid_path.unlink()
        return {"status": "stopped", "pid": pid}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def check_memory_server() -> dict[str, Any]:
    if not is_server_running():
        return {
            "running": False,
            "url": None,
            "pid": None,
            "health_ok": False,
            "log_path": get_log_file_path(),
        }
    url = get_server_url()
    health_ok = _wait_for_health(url.replace("/mcp", "/health"), timeout=1.0)
    return {
        "running": True,
        "url": url,
        "pid": _read_pid(),
        "health_ok": health_ok,
        "log_path": get_log_file_path(),
    }


def ensure_memory_server() -> dict[str, Any]:
    state = check_memory_server()
    if state.get("running") and state.get("health_ok"):
        return {
            "status": "already_running",
            "url": state.get("url"),
            "pid": state.get("pid"),
            "log_path": state.get("log_path"),
        }
    return start_memory_server()


if os.environ.get("OMG_MEMORY_AUTOSTART") == "1":
    ensure_memory_server()
