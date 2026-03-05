"""Tests for cost ledger storage (v2.0 — Task 6).

Tests append_cost_entry, read_cost_summary, and rotate_cost_ledger
following the JSONL + fcntl locking pattern from tool-ledger.py.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Add hooks to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hooks"))

from _cost_ledger import append_cost_entry, read_cost_summary, rotate_cost_ledger


def _make_entry(**overrides) -> dict:
    """Helper to create a valid cost entry with defaults."""
    base = {
        "ts": "2026-01-15T10:30:00Z",
        "tool": "Bash",
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.001,
        "model": "claude-sonnet",
        "session_id": "sess-001",
    }
    base.update(overrides)
    return base


def _ledger_path(project_dir: str) -> str:
    return os.path.join(project_dir, ".omg", "state", "ledger", "cost-ledger.jsonl")


# ── Test 1: append creates directory and file ──


def test_append_creates_ledger_file():
    """append_cost_entry creates .omg/state/ledger/ and writes JSONL."""
    with tempfile.TemporaryDirectory() as d:
        entry = _make_entry()
        append_cost_entry(d, entry)

        path = _ledger_path(d)
        assert os.path.exists(path), "cost-ledger.jsonl should be created"

        with open(path, "r") as f:
            line = f.readline().strip()
        parsed = json.loads(line)
        assert parsed["tool"] == "Bash"
        assert parsed["tokens_in"] == 100
        assert parsed["cost_usd"] == 0.001


# ── Test 2: append appends multiple entries ──


def test_append_multiple_entries():
    """Multiple appends produce multiple JSONL lines."""
    with tempfile.TemporaryDirectory() as d:
        for i in range(5):
            append_cost_entry(d, _make_entry(tokens_in=100 + i))

        path = _ledger_path(d)
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 5
        assert json.loads(lines[0])["tokens_in"] == 100
        assert json.loads(lines[4])["tokens_in"] == 104


# ── Test 3: read_cost_summary returns empty for missing file ──


def test_read_summary_missing_file():
    """read_cost_summary returns empty summary when no ledger exists."""
    with tempfile.TemporaryDirectory() as d:
        summary = read_cost_summary(d)
        assert summary["total_tokens"] == 0
        assert summary["total_cost_usd"] == 0.0
        assert summary["by_tool"] == {}
        assert summary["by_session"] == {}
        assert summary["entry_count"] == 0


# ── Test 4: read_cost_summary aggregates correctly ──


def test_read_summary_aggregation():
    """read_cost_summary correctly aggregates tokens, cost, by_tool, by_session."""
    with tempfile.TemporaryDirectory() as d:
        append_cost_entry(d, _make_entry(tool="Bash", tokens_in=100, tokens_out=50, cost_usd=0.001, session_id="s1"))
        append_cost_entry(d, _make_entry(tool="Read", tokens_in=200, tokens_out=80, cost_usd=0.002, session_id="s1"))
        append_cost_entry(d, _make_entry(tool="Bash", tokens_in=150, tokens_out=60, cost_usd=0.0015, session_id="s2"))

        summary = read_cost_summary(d)

        assert summary["entry_count"] == 3
        assert summary["total_tokens"] == 100 + 50 + 200 + 80 + 150 + 60  # 640
        assert abs(summary["total_cost_usd"] - 0.0045) < 1e-9

        # by_tool
        assert summary["by_tool"]["Bash"]["tokens"] == (100 + 50) + (150 + 60)  # 360
        assert abs(summary["by_tool"]["Bash"]["cost_usd"] - 0.0025) < 1e-9
        assert summary["by_tool"]["Read"]["tokens"] == 200 + 80  # 280

        # by_session
        assert summary["by_session"]["s1"]["tokens"] == (100 + 50) + (200 + 80)  # 430
        assert summary["by_session"]["s2"]["tokens"] == 150 + 60  # 210


# ── Test 5: read_cost_summary skips malformed lines ──


def test_read_summary_skips_malformed_lines():
    """Malformed JSONL lines are skipped without error."""
    with tempfile.TemporaryDirectory() as d:
        path = _ledger_path(d)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w") as f:
            f.write(json.dumps(_make_entry(tokens_in=100, tokens_out=50, cost_usd=0.001)) + "\n")
            f.write("THIS IS NOT JSON\n")
            f.write("{bad json\n")
            f.write(json.dumps(_make_entry(tokens_in=200, tokens_out=80, cost_usd=0.002)) + "\n")

        summary = read_cost_summary(d)
        assert summary["entry_count"] == 2
        assert summary["total_tokens"] == 100 + 50 + 200 + 80  # 430


# ── Test 6: rotate_cost_ledger rotates at 5MB ──


def test_rotate_cost_ledger():
    """rotate_cost_ledger moves file to .1 archive when >5MB."""
    with tempfile.TemporaryDirectory() as d:
        path = _ledger_path(d)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Write >5MB of data
        with open(path, "w") as f:
            # Each line ~100 bytes, need ~52000 lines for 5MB
            line = json.dumps(_make_entry()) + "\n"
            count = (5 * 1024 * 1024 // len(line)) + 100
            for _ in range(count):
                f.write(line)

        assert os.path.getsize(path) > 5 * 1024 * 1024

        rotate_cost_ledger(d)

        archive = path + ".1"
        assert os.path.exists(archive), "Archive .1 should be created"
        assert not os.path.exists(path), "Original file should be moved"


# ── Test 7: rotate_cost_ledger replaces existing archive ──


def test_rotate_replaces_existing_archive():
    """Rotation replaces an existing .1 archive."""
    with tempfile.TemporaryDirectory() as d:
        path = _ledger_path(d)
        archive = path + ".1"
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Create old archive
        with open(archive, "w") as f:
            f.write("old archive content\n")

        # Write >5MB main file
        with open(path, "w") as f:
            line = json.dumps(_make_entry()) + "\n"
            count = (5 * 1024 * 1024 // len(line)) + 100
            for _ in range(count):
                f.write(line)

        rotate_cost_ledger(d)

        assert os.path.exists(archive)
        assert os.path.getsize(archive) > 5 * 1024 * 1024
        assert not os.path.exists(path)


# ── Test 8: rotate does nothing when file is small ──


def test_rotate_noop_when_small():
    """rotate_cost_ledger does nothing when file < 5MB."""
    with tempfile.TemporaryDirectory() as d:
        path = _ledger_path(d)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w") as f:
            f.write(json.dumps(_make_entry()) + "\n")

        rotate_cost_ledger(d)

        assert os.path.exists(path), "Small file should remain"
        assert not os.path.exists(path + ".1"), "No archive for small file"


# ── Test 9: rotate handles missing file gracefully ──


def test_rotate_missing_file_noop():
    """rotate_cost_ledger does nothing when no ledger file exists."""
    with tempfile.TemporaryDirectory() as d:
        # No file created — should not raise
        rotate_cost_ledger(d)

        path = _ledger_path(d)
        assert not os.path.exists(path)


# ── Test 10: entry schema fields all present in written JSONL ──


def test_entry_schema_completeness():
    """All required schema fields are preserved in JSONL output."""
    with tempfile.TemporaryDirectory() as d:
        entry = _make_entry(
            ts="2026-03-01T12:00:00Z",
            tool="Write",
            tokens_in=500,
            tokens_out=250,
            cost_usd=0.05,
            model="claude-opus-4",
            session_id="sess-xyz",
        )
        append_cost_entry(d, entry)

        path = _ledger_path(d)
        with open(path, "r") as f:
            parsed = json.loads(f.readline())

        required_keys = {"ts", "tool", "tokens_in", "tokens_out", "cost_usd", "model", "session_id"}
        assert required_keys.issubset(set(parsed.keys())), f"Missing keys: {required_keys - set(parsed.keys())}"
        assert parsed["ts"] == "2026-03-01T12:00:00Z"
        assert parsed["model"] == "claude-opus-4"
        assert parsed["session_id"] == "sess-xyz"
