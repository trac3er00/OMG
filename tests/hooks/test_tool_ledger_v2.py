#!/usr/bin/env python3
"""Tests for tool-ledger.py latency tracking (duration_ms field).

TDD: Written BEFORE implementation. All tests should FAIL initially.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
HOOK_SCRIPT = PROJECT_ROOT / "hooks" / "tool-ledger.py"


def run_tool_ledger(stdin_data: dict, env_overrides: dict | None = None) -> dict:
    """Run tool-ledger.py as subprocess and return the last JSONL entry written."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .omg structure so hook can write
        omg_dir = os.path.join(tmpdir, ".omg", "state", "ledger")
        os.makedirs(omg_dir, exist_ok=True)

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = tmpdir
        if env_overrides:
            env.update(env_overrides)

        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(stdin_data),
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

        assert result.returncode == 0, f"Hook crashed: {result.stderr}"

        ledger_path = os.path.join(omg_dir, "tool-ledger.jsonl")
        assert os.path.exists(ledger_path), "Ledger file not created"

        with open(ledger_path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]

        assert len(lines) >= 1, "No entries written to ledger"
        return json.loads(lines[-1])


class TestDurationMsFieldPresent:
    """Test that duration_ms field is present in new ledger entries."""

    def test_duration_ms_field_exists_in_entry(self):
        """New entries MUST have a duration_ms field."""
        stdin = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": "file.txt"},
        }
        entry = run_tool_ledger(stdin)
        assert "duration_ms" in entry, "duration_ms field missing from ledger entry"

    def test_duration_ms_is_int_or_null(self):
        """duration_ms must be int or null, never string/float."""
        stdin = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "tool_response": {"content": "hello"},
        }
        entry = run_tool_ledger(stdin)
        assert "duration_ms" in entry
        val = entry["duration_ms"]
        assert val is None or isinstance(val, int), (
            f"duration_ms must be int or null, got {type(val).__name__}: {val}"
        )


class TestDurationMsFromStartEndTime:
    """Test duration_ms calculation from stdin startTime/endTime."""

    def test_calculates_from_iso8601_start_end_time(self):
        """When startTime and endTime are provided as ISO8601, compute delta."""
        stdin = {
            "tool_name": "Bash",
            "tool_input": {"command": "sleep 0.1"},
            "tool_response": {"stdout": ""},
            "startTime": "2026-03-04T10:00:00.000Z",
            "endTime": "2026-03-04T10:00:01.500Z",
        }
        entry = run_tool_ledger(stdin)
        assert "duration_ms" in entry
        # 1.5 seconds = 1500 ms
        assert entry["duration_ms"] == 1500

    def test_calculates_from_fractional_seconds(self):
        """Handles fractional seconds correctly."""
        stdin = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "tool_response": {"stdout": "hi"},
            "startTime": "2026-03-04T10:00:00.000Z",
            "endTime": "2026-03-04T10:00:00.250Z",
        }
        entry = run_tool_ledger(stdin)
        assert entry["duration_ms"] == 250


class TestDurationMsFallback:
    """Test wall-clock fallback when startTime/endTime not available."""

    def test_wall_clock_fallback_when_no_timestamps(self):
        """Without startTime/endTime, use wall clock (non-negative int)."""
        stdin = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
            "tool_response": {"stdout": "hello"},
        }
        entry = run_tool_ledger(stdin)
        assert "duration_ms" in entry
        val = entry["duration_ms"]
        # Wall clock delta should be a non-negative integer (hook runs fast)
        assert isinstance(val, int), f"Expected int, got {type(val).__name__}"
        assert val >= 0, f"duration_ms should be non-negative, got {val}"


class TestDurationMsErrorResilience:
    """Test that malformed timestamps don't crash the hook."""

    def test_malformed_start_time_yields_null_or_fallback(self):
        """Malformed startTime should not crash; duration_ms = null or wall clock."""
        stdin = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo x"},
            "tool_response": {"stdout": "x"},
            "startTime": "not-a-date",
            "endTime": "2026-03-04T10:00:01.000Z",
        }
        entry = run_tool_ledger(stdin)
        # Hook must not crash (returncode == 0 checked in helper)
        assert "duration_ms" in entry
        # Value should be null or a non-negative int (wall clock fallback)
        val = entry["duration_ms"]
        assert val is None or (isinstance(val, int) and val >= 0)

    def test_missing_end_time_yields_null_or_fallback(self):
        """Only startTime without endTime should not crash."""
        stdin = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo x"},
            "tool_response": {"stdout": "x"},
            "startTime": "2026-03-04T10:00:00.000Z",
        }
        entry = run_tool_ledger(stdin)
        assert "duration_ms" in entry
        val = entry["duration_ms"]
        assert val is None or (isinstance(val, int) and val >= 0)


class TestBackwardCompatibility:
    """Old entries without duration_ms must still parse without error."""

    def test_old_entries_without_duration_ms_parse(self):
        """Reading old JSONL entries missing duration_ms should work via .get()."""
        old_entry_json = '{"ts":"2026-01-01T00:00:00Z","tool":"Bash","pid":12345,"command":"ls"}'
        parsed = json.loads(old_entry_json)
        duration = parsed.get("duration_ms", None)
        assert duration is None, "Old entries should return None for missing duration_ms"

    def test_new_entries_coexist_with_old(self):
        """A ledger file can contain both old entries (no duration_ms) and new ones."""
        old_line = '{"ts":"2026-01-01T00:00:00Z","tool":"Bash","pid":1}'
        new_line = '{"ts":"2026-03-04T10:00:00Z","tool":"Bash","pid":2,"duration_ms":42}'

        entries = [json.loads(old_line), json.loads(new_line)]

        # Both parse fine
        assert entries[0].get("duration_ms") is None
        assert entries[1].get("duration_ms") == 42
