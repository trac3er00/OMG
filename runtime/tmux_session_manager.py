"""tmux session lifecycle manager for persistent model invocations."""

from __future__ import annotations

from collections.abc import Sequence
import logging
import re
import shlex
import shutil
import subprocess
import time
import uuid
from typing import Any


_logger = logging.getLogger(__name__)

TMUX_REUSE_SCHEMA = "OmgTmuxReuseReport"
DEFAULT_MIN_REUSE_RATIO = 0.7


def build_tmux_reuse_report(
    *,
    reused_sessions: int,
    total_sessions: int,
    min_reuse_ratio: float = DEFAULT_MIN_REUSE_RATIO,
) -> dict[str, Any]:
    """Build a deterministic tmux session reuse summary."""
    total = max(int(total_sessions), 0)
    reused = max(int(reused_sessions), 0)
    if total == 0:
        reuse_ratio = 0.0
    else:
        reuse_ratio = round(reused / total, 2)
    return {
        "schema": TMUX_REUSE_SCHEMA,
        "reused_sessions": reused,
        "total_sessions": total,
        "reuse_ratio": reuse_ratio,
        "budgets": {"min_reuse_ratio": float(min_reuse_ratio)},
        "within_budget": reuse_ratio >= float(min_reuse_ratio),
    }


class TmuxSessionManager:
    """Manage lightweight tmux sessions used for provider command execution."""

    def __init__(self, session_prefix: str = "omg") -> None:
        """Initialize manager with a session name prefix."""
        self.session_prefix: str = session_prefix

    def is_tmux_available(self) -> bool:
        """Return True when tmux is available on PATH."""
        return shutil.which("tmux") is not None

    def session_exists(self, name: str) -> bool:
        """Return True if a tmux session exists."""
        if not self.is_tmux_available():
            return False
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as exc:
            _logger.warning("Failed to check tmux session %r: %s", name, exc)
            return False

    def create_session(self, name: str) -> bool:
        """Create a detached tmux session and return success state."""
        if not self.is_tmux_available():
            return False
        try:
            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            return result.returncode == 0
        except Exception as exc:
            _logger.warning("Failed to create tmux session %r: %s", name, exc)
            return False

    def kill_session(self, name: str) -> bool:
        """Kill a tmux session and return success state."""
        if not self.is_tmux_available():
            return False
        try:
            result = subprocess.run(
                ["tmux", "kill-session", "-t", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            return result.returncode == 0
        except Exception as exc:
            _logger.warning("Failed to kill tmux session %r: %s", name, exc)
            return False

    def _normalize_command(self, command: str | Sequence[str]) -> str:
        if isinstance(command, str):
            parts = shlex.split(command)
        else:
            parts = list(command)
        if not parts or any(not isinstance(part, str) or not part for part in parts):
            raise ValueError("tmux command must contain at least one non-empty argument")
        return shlex.join(parts)

    def send_command(self, name: str, command: str | Sequence[str], timeout: int = 120) -> str:
        """Send a command to a tmux session and return captured pane output."""
        result = self.send_command_result(name, command, timeout=timeout)
        return str(result.get("output", ""))

    def _extract_command_result(self, captured_output: str, marker: str) -> dict[str, Any]:
        """Parse tmux pane output into a stable result payload."""
        text = str(captured_output).rstrip()
        matches = list(re.finditer(rf"{re.escape(marker)}::(-?\d+)", text))
        if not matches:
            return {
                "output": text,
                "exit_code": None,
                "completed": False,
            }

        match = matches[-1]
        exit_code = int(match.group(1))
        output = text[: match.start()].rstrip()
        return {
            "output": output,
            "exit_code": exit_code,
            "completed": True,
        }

    def send_command_result(self, name: str, command: str | Sequence[str], timeout: int = 120) -> dict[str, Any]:
        """Send a command to tmux and return deterministic output, exit code, and completion state."""
        if not self.is_tmux_available():
            return {"output": "", "exit_code": None, "completed": False, "timed_out": False}

        sentinel = f"__OMG_DONE_{uuid.uuid4().hex}__"
        deadline = time.monotonic() + timeout
        wait_seconds = 0.1

        try:
            normalized_command = self._normalize_command(command)
            send_main = subprocess.run(
                ["tmux", "send-keys", "-t", name, normalized_command, "Enter"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if send_main.returncode != 0:
                return {"output": "", "exit_code": None, "completed": False, "timed_out": False}

            send_marker = subprocess.run(
                ["tmux", "send-keys", "-t", name, f"printf '%s::%s\\n' {sentinel} \"$?\"", "Enter"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if send_marker.returncode != 0:
                return {"output": "", "exit_code": None, "completed": False, "timed_out": False}

            last_result: dict[str, Any] = {
                "output": "",
                "exit_code": None,
                "completed": False,
                "timed_out": False,
            }
            while time.monotonic() < deadline:
                captured = subprocess.run(
                    ["tmux", "capture-pane", "-t", name, "-p"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if captured.returncode == 0:
                    last_result = self._extract_command_result(captured.stdout, sentinel)
                    if last_result["completed"]:
                        last_result["timed_out"] = False
                        return last_result
                time.sleep(wait_seconds)
                wait_seconds = min(1.0, wait_seconds * 1.5)

            last_result["timed_out"] = True
            return last_result
        except ValueError as exc:
            _logger.warning("Invalid tmux command for %r: %s", name, exc)
            return {"output": "", "exit_code": None, "completed": False, "timed_out": False}
        except Exception as exc:
            _logger.warning("Failed to send tmux command to %r: %s", name, exc)
            return {"output": "", "exit_code": None, "completed": False, "timed_out": False}

    def get_or_create_session(self, name: str) -> str:
        """Return a fresh tmux session name, recreating stale sessions if needed."""
        if self.session_exists(name):
            _ = self.kill_session(name)
        if not self.create_session(name):
            raise RuntimeError(f"Unable to create tmux session: {name}")
        return name

    def make_session_name(self, provider: str, unique_id: str | None = None) -> str:
        """Build a normalized tmux session name using provider and optional id."""
        provider_clean = re.sub(r"[^a-zA-Z0-9_-]", "-", provider).strip("-").lower() or "session"
        base_name = f"{self.session_prefix}-{provider_clean}"
        if unique_id:
            unique_clean = re.sub(r"[^a-zA-Z0-9_-]", "-", unique_id).strip("-").lower()
            if unique_clean:
                return f"{base_name}-{unique_clean}"
        return base_name

    def cleanup_stale_sessions(self) -> int:
        """Kill all tmux sessions matching this manager prefix and return count."""
        if not self.is_tmux_available():
            return 0

        try:
            listed = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if listed.returncode != 0:
                return 0

            killed = 0
            prefix = f"{self.session_prefix}-"
            for session_name in sorted(listed.stdout.splitlines()):
                if session_name.startswith(prefix) and self.kill_session(session_name):
                    killed += 1
            return killed
        except Exception as exc:
            _logger.warning("Failed to cleanup tmux sessions for prefix %r: %s", self.session_prefix, exc)
            return 0
