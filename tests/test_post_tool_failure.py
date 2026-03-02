#!/usr/bin/env python3
"""Tests for hooks/post-tool-failure.py.

Tests via subprocess to match real Claude Code invocation.
All hooks MUST exit 0 regardless of input (crash isolation invariant).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "post-tool-failure.py"


def _run(payload: dict, project_dir: str | Path) -> subprocess.CompletedProcess[str]:
    """Run post-tool-failure.py with given payload and project dir."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)},
        timeout=15,
    )


def _read_hook_errors(project: Path) -> list[dict]:
    """Read hook-errors.jsonl from project dir."""
    errors_path = project / ".oal" / "state" / "ledger" / "hook-errors.jsonl"
    if not errors_path.exists():
        return []
    
    entries = []
    for line in errors_path.read_text().strip().split('\n'):
        if line:
            entries.append(json.loads(line))
    return entries


# ━━━ 1. Valid input → creates/appends to hook-errors.jsonl ━━━

def test_tool_failure_logged(tmp_path):
    """A valid tool failure input should create/append to hook-errors.jsonl."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "error": "timeout",
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0, f"Expected exit 0, got {proc.returncode}. stderr: {proc.stderr}"

    errors = _read_hook_errors(tmp_path)
    assert len(errors) >= 1, f"Expected at least 1 error entry, got {len(errors)}"
    
    last_error = errors[-1]
    assert last_error["hook"] == "post-tool-failure"
    assert "timeout" in last_error["error"]
    assert last_error["context"]["tool"] == "Bash"


# ━━━ 2. Invalid JSON → exit 0 (crash isolation) ━━━

def test_invalid_json_exits_zero(tmp_path):
    """Invalid JSON input should exit 0 (crash isolation invariant)."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not valid json {{{",
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        timeout=15,
    )
    assert proc.returncode == 0, f"Expected exit 0 on invalid JSON, got {proc.returncode}"


# ━━━ 3. Missing error field → graceful handling ━━━

def test_missing_error_field_graceful(tmp_path):
    """Input without 'error' field should exit 0 and log 'unknown error'."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Write",
        # No 'error' or 'message' field
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    errors = _read_hook_errors(tmp_path)
    assert len(errors) >= 1
    
    last_error = errors[-1]
    assert last_error["hook"] == "post-tool-failure"
    assert "unknown error" in last_error["error"]
    assert last_error["context"]["tool"] == "Write"
