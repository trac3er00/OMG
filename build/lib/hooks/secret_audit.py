#!/usr/bin/env python3
"""Secret access audit logging for OMG v1 (T21).

Logs every secret access attempt (allow/deny/ask) to
.omg/state/ledger/secret-access.jsonl with:
- fcntl file locking (same pattern as tool-ledger.py)
- 5MB rotation with single .1 archive
- Secret path masking (redact paths matching secret patterns)

Pure stdlib — no external dependencies.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone

# --- Constants ---

SECRET_ACCESS_LOG = "secret-access.jsonl"
SECRET_ACCESS_MAX_BYTES = 5 * 1024 * 1024  # 5MB

# Patterns that indicate a path should be redacted in audit logs.
# Aligned with policy_engine.py SECRET_FILE_PATTERNS / BLOCKED_PATH_PATTERNS.
_REDACT_PATH_PATTERNS = [
    r"\.(env|pem|key|p12|pfx|jks|keystore|netrc|npmrc|pypirc)(\.\w+)?$",
    r"(^|/)\.aws/",
    r"(^|/)\.ssh/",
    r"(^|/)\.kube/",
    r"(^|/)\.gnupg/",
    r"(^|/)secrets?/",
    r"(^|/)credentials?\.",
    r"(^|/)passwords?\.",
    r"(^|/)tokens?\.",
]

# Safe env reference files that should NOT be redacted
_SAFE_ENV_PATTERN = re.compile(r"\.env\.(example|sample|template)$", re.IGNORECASE)


def mask_secret_path(file_path: str) -> str:
    """Redact file paths that match secret patterns.

    Returns '[REDACTED]' for paths matching known secret file patterns.
    Safe references (.env.example, .env.sample, .env.template) are NOT redacted.
    """
    if not file_path:
        return file_path

    # Safe env references pass through unmasked
    basename = os.path.basename(file_path)
    if _SAFE_ENV_PATTERN.search(basename):
        return file_path

    for pat in _REDACT_PATH_PATTERNS:
        if re.search(pat, file_path, re.IGNORECASE):
            return "[REDACTED]"

    return file_path


def _rotate_log(log_path: str) -> None:
    """Rotate log file if it exceeds 5MB. Same pattern as tool-ledger.py."""
    try:
        if not os.path.exists(log_path):
            return
        size = os.path.getsize(log_path)
        if size <= SECRET_ACCESS_MAX_BYTES:
            return

        archive = log_path + ".1"
        # Keep only one archive — replace old one
        if os.path.exists(archive):
            try:
                os.remove(archive)
            except OSError:
                pass
        shutil.move(log_path, archive)
    except Exception:
        pass


def log_secret_access(
    project_dir: str,
    tool: str,
    file_path: str,
    decision: str,
    reason: str,
    allowlisted: bool,
) -> None:
    """Log a secret access decision to .omg/state/ledger/secret-access.jsonl.

    Args:
        project_dir: Project root directory
        tool: Tool name (Read, Write, Edit, MultiEdit)
        file_path: File being accessed (will be masked if it matches secret patterns)
        decision: Policy decision (allow, deny, ask)
        reason: Human-readable reason for the decision
        allowlisted: Whether the access was via an allowlist bypass

    Creates the ledger directory if it doesn't exist.
    Uses fcntl file locking for concurrent safety.
    Rotates at 5MB with a single .1 archive.
    Silently fails — never raises exceptions (crash isolation invariant).
    """
    try:
        ledger_dir = os.path.join(project_dir, ".omg", "state", "ledger")
        os.makedirs(ledger_dir, exist_ok=True)

        log_path = os.path.join(ledger_dir, SECRET_ACCESS_LOG)

        # Rotate if needed
        _rotate_log(log_path)

        # Build entry with masked path
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "file": mask_secret_path(file_path),
            "decision": decision,
            "reason": reason,
            "allowlisted": allowlisted,
        }

        # Write with fcntl locking (same pattern as tool-ledger.py)
        try:
            import fcntl

            fd = open(log_path, "a")
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(json.dumps(entry, separators=(",", ":")) + "\n")
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()
        except (ImportError, BlockingIOError):
            # Fallback: write without locking
            try:
                with open(log_path, "a") as f:
                    f.write(json.dumps(entry, separators=(",", ":")) + "\n")
            except Exception:
                pass
    except Exception:
        pass  # Crash isolation: never fail the hook
