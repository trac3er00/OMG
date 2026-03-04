"""OMG Natives — shell: subprocess execution.

Pure-Python fallback for subprocess execution.
Uses ``subprocess.run`` with capture and timeout support.

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import subprocess

from omg_natives._bindings import bind_function


def shell(cmd: str, timeout: int = 30) -> dict:
    """Execute *cmd* in a subprocess shell.

    Returns ``{"stdout": str, "stderr": str, "returncode": int, "success": bool}``.
    On timeout or other errors, ``returncode`` is ``-1`` and ``success`` is ``False``.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
            "success": False,
        }
    except OSError as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "success": False,
        }


# Self-register with the global binding registry
bind_function(
    name="shell",
    rust_symbol="omg_natives::shell::shell",
    python_fallback=shell,
    type_hints={"cmd": "str", "timeout": "int"},
)
