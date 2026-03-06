"""tmux session lifecycle manager for persistent model invocations."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
import uuid


_logger = logging.getLogger(__name__)


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

    def send_command(self, name: str, command: str, timeout: int = 120) -> str:
        """Send a command to a tmux session and return captured pane output."""
        if not self.is_tmux_available():
            return ""

        sentinel = f"__OMG_DONE_{uuid.uuid4().hex}__"
        deadline = time.monotonic() + timeout

        try:
            send_main = subprocess.run(
                ["tmux", "send-keys", "-t", name, command, "Enter"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if send_main.returncode != 0:
                return ""

            send_marker = subprocess.run(
                ["tmux", "send-keys", "-t", name, f"echo {sentinel}", "Enter"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if send_marker.returncode != 0:
                return ""

            last_output = ""
            while time.monotonic() < deadline:
                captured = subprocess.run(
                    ["tmux", "capture-pane", "-t", name, "-p"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if captured.returncode == 0:
                    last_output = captured.stdout
                    if sentinel in last_output:
                        return last_output.split(sentinel, 1)[0].rstrip()
                time.sleep(0.25)

            return last_output.rstrip()
        except Exception as exc:
            _logger.warning("Failed to send tmux command to %r: %s", name, exc)
            return ""

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
            for session_name in listed.stdout.splitlines():
                if session_name.startswith(prefix) and self.kill_session(session_name):
                    killed += 1
            return killed
        except Exception as exc:
            _logger.warning("Failed to cleanup tmux sessions for prefix %r: %s", self.session_prefix, exc)
            return 0
