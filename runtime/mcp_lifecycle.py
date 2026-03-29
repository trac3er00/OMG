"""MCP server lifecycle manager — start/stop/health/ensure."""
from __future__ import annotations

import os
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


def get_pid_file_path() -> str:
    """Return path to the PID file for the memory server."""
    return str(Path.home() / ".omg" / "shared-memory" / "server.pid")


def get_server_url() -> str:
    """Return the MCP server URL using host/port from mcp_memory_server."""
    from runtime.mcp_memory_server import get_host, get_port

    return f"http://{get_host()}:{get_port()}/mcp"


def _read_pid() -> int | None:
    """Read PID from PID file. Returns None if missing or invalid."""
    try:
        return int(Path(get_pid_file_path()).read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def is_server_running() -> bool:
    """Check if the memory server process is alive."""
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it


def _wait_for_health(url: str, timeout: float = 5.0) -> bool:
    """Wait for server health endpoint to respond."""
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
    """Wait for a process to exit."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except (ProcessLookupError, PermissionError):
            return True
    return False


def start_memory_server() -> dict[str, Any]:
    """Start the MCP memory server as a background process."""
    if is_server_running():
        return {"status": "already_running", "url": get_server_url()}

    pid_path = Path(get_pid_file_path())
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        server_script = str(Path(__file__).parent / "mcp_memory_server.py")
        proc = subprocess.Popen(
            [sys.executable, server_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        health_url = get_server_url().replace("/mcp", "/health")
        if _wait_for_health(health_url):
            pid_path.write_text(str(proc.pid))
            return {"status": "started", "pid": proc.pid, "url": get_server_url()}
        rc = proc.poll()
        if rc is not None and rc != 0:
            if pid_path.exists():
                pid_path.unlink()
            return {
                "status": "error",
                "message": f"Server exited early with return code {rc}",
            }
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception as exc:
            _logger.debug("Failed to terminate unresponsive memory server process: %s", exc, exc_info=True)
            try:
                proc.kill()
            except Exception as kill_exc:
                _logger.debug("Failed to kill unresponsive memory server process: %s", kill_exc, exc_info=True)
        if pid_path.exists():
            pid_path.unlink()
        return {
            "status": "error",
            "message": "Server did not respond within timeout",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def stop_memory_server() -> dict[str, Any]:
    """Stop the MCP memory server."""
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
    """Check the memory server status."""
    running = is_server_running()
    if not running:
        return {"running": False, "url": None, "pid": None}

    return {
        "running": True,
        "url": get_server_url(),
        "pid": _read_pid(),
    }


_HTTP_MEMORY_RESTRICTED_PRESETS = frozenset({"safe", "balanced"})


def _get_current_preset() -> str:
    return os.environ.get("OMG_PRESET", "safe")


def ensure_memory_server() -> dict[str, Any]:
    """Ensure the memory server is running (idempotent).

    Skips startup when the active preset is ``safe`` or ``balanced`` —
    HTTP memory is an opt-in surface starting at the ``interop`` tier.
    """
    preset = _get_current_preset()
    if preset in _HTTP_MEMORY_RESTRICTED_PRESETS:
        return {"status": "skipped", "reason": f"HTTP memory disabled for preset '{preset}'"}
    if is_server_running():
        return {"status": "already_running", "url": get_server_url()}
    return start_memory_server()


# Feature flag: auto-start on import (respects preset restrictions)
if os.environ.get("OMG_MEMORY_AUTOSTART") == "1":
    ensure_memory_server()
