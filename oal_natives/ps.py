"""OAL Natives — ps: process listing.

Pure-Python fallback for process listing.
Uses ``os`` module — reads ``/proc`` on Linux, falls back to
``os.getpid()`` / ``os.getppid()`` on other platforms.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import os
import sys
from typing import List

from oal_natives._bindings import bind_function


def ps() -> list[dict]:
    """Return a list of process info dicts.

    Each dict contains ``{"pid": int, "name": str, "status": str}``.

    On Linux, reads ``/proc`` for process data. On other platforms,
    returns at minimum the current process and parent process.
    """
    processes: List[dict] = []

    if sys.platform == "linux" and os.path.isdir("/proc"):
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                pid = int(entry)
                name = _read_proc_name(pid)
                status = _read_proc_status(pid)
                processes.append({"pid": pid, "name": name, "status": status})
        except OSError:
            pass

    # Always include at least the current and parent process
    if not processes:
        processes.append({
            "pid": os.getpid(),
            "name": _get_current_process_name(),
            "status": "running",
        })
        ppid = os.getppid()
        if ppid > 0:
            processes.append({
                "pid": ppid,
                "name": "parent",
                "status": "running",
            })

    return processes


def _read_proc_name(pid: int) -> str:
    """Read the process name from /proc/<pid>/comm."""
    try:
        with open(f"/proc/{pid}/comm", "r") as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def _read_proc_status(pid: int) -> str:
    """Read the process status from /proc/<pid>/status."""
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("State:"):
                    return line.split(":", 1)[1].strip().split()[0]
    except OSError:
        pass
    return "unknown"


def _get_current_process_name() -> str:
    """Get the current process name."""
    try:
        return os.path.basename(sys.executable)
    except Exception:
        return "python"


# Self-register with the global binding registry
bind_function(
    name="ps",
    rust_symbol="oal_natives::ps::ps",
    python_fallback=ps,
)
