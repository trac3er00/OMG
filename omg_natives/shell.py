"""OMG Natives — shell: subprocess execution.

Pure-Python fallback for subprocess execution.
Uses ``subprocess.run`` with capture and timeout support.

Feature flag: ``OMG_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence

from omg_natives._bindings import bind_function


_SHELL_METACHARS = frozenset({"|", "&", ";", "<", ">", "$", "`", "\n", "\r"})


def _normalize_command(cmd: str | Sequence[str]) -> list[str]:
    if isinstance(cmd, str):
        stripped = cmd.strip()
        if not stripped:
            raise ValueError("Command must not be empty")
        if any(char in stripped for char in _SHELL_METACHARS):
            raise ValueError(
                "Shell metacharacters are not supported; pass an argv sequence instead"
            )
        parts = shlex.split(stripped)
    else:
        parts = list(cmd)

    if not parts or any(not isinstance(part, str) or not part for part in parts):
        raise ValueError("Command sequence must contain at least one non-empty string")
    return parts


def shell(cmd: str | Sequence[str], timeout: int = 30) -> dict:
    """Execute *cmd* in a subprocess without invoking a shell.

    Returns ``{"stdout": str, "stderr": str, "returncode": int, "success": bool}``.
    On timeout or other errors, ``returncode`` is ``-1`` and ``success`` is ``False``.
    """
    try:
        argv = _normalize_command(cmd)
        result = subprocess.run(
            argv,
            shell=False,
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
    except ValueError as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "success": False,
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
    type_hints={"cmd": "str | list[str]", "timeout": "int"},
)
