#!/usr/bin/env python3
"""Tests for PostToolUseFailure compression feedback hook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "hooks" / "compression_feedback.py"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_hook(project_dir: Path, payload: dict[str, Any], env: dict[str, str] | None = None):
    run_env = os.environ.copy()
    run_env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=run_env,
        cwd=str(project_dir),
        check=False,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _base_payload(ts: str, *, phrase: str = "critical-cache-key") -> dict[str, Any]:
    return {
        "tool_name": "Read",
        "tool_input": {"path": "state.log", "query": phrase},
        "tool_response": {"error": f"missing context for {phrase}"},
        "session_id": "sess-123",
        "timestamp": ts,
    }


def _enable_context_manager(project_dir: Path) -> None:
    _write_json(
        project_dir / "settings.json",
        {"_omg": {"features": {"CONTEXT_MANAGER": True}}},
    )


def test_post_compaction_failure_logged():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _enable_context_manager(project_dir)

        now = datetime.now(timezone.utc)
        _write_json(project_dir / ".omg" / "state" / "last-compaction.json", {"timestamp": _iso(now - timedelta(minutes=5))})
        (project_dir / ".omg" / "state" / "handoff.md").parent.mkdir(parents=True, exist_ok=True)
        (project_dir / ".omg" / "state" / "handoff.md").write_text("- critical-cache-key\n", encoding="utf-8")

        proc = _run_hook(project_dir, _base_payload(_iso(now)))

        assert proc.returncode == 0
        rows = _read_jsonl(project_dir / ".omg" / "state" / "compression-feedback.jsonl")
        assert len(rows) == 1
        assert rows[0]["post_compaction"] is True


def test_non_compaction_failure_not_logged():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _enable_context_manager(project_dir)

        now = datetime.now(timezone.utc)
        _write_json(project_dir / ".omg" / "state" / "last-compaction.json", {"timestamp": _iso(now - timedelta(minutes=45))})

        proc = _run_hook(project_dir, _base_payload(_iso(now)))

        assert proc.returncode == 0
        assert _read_jsonl(project_dir / ".omg" / "state" / "compression-feedback.jsonl") == []


def test_jsonl_entry_format():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _enable_context_manager(project_dir)

        now = datetime.now(timezone.utc)
        _write_json(project_dir / ".omg" / "state" / "last-compaction.json", {"timestamp": _iso(now - timedelta(minutes=10))})
        (project_dir / ".omg" / "state" / "handoff.md").parent.mkdir(parents=True, exist_ok=True)
        (project_dir / ".omg" / "state" / "handoff.md").write_text("- critical-cache-key\n", encoding="utf-8")

        proc = _run_hook(project_dir, _base_payload(_iso(now)))

        assert proc.returncode == 0
        rows = _read_jsonl(project_dir / ".omg" / "state" / "compression-feedback.jsonl")
        assert len(rows) == 1
        entry = rows[0]
        required = {
            "ts",
            "session_id",
            "tool_name",
            "failure_reason",
            "post_compaction",
            "context_snapshot",
            "promoted_items",
        }
        assert required.issubset(entry.keys())


def test_auto_promotion_threshold():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _enable_context_manager(project_dir)

        now = datetime.now(timezone.utc)
        _write_json(project_dir / ".omg" / "state" / "last-compaction.json", {"timestamp": _iso(now - timedelta(minutes=8))})
        (project_dir / ".omg" / "state" / "handoff.md").parent.mkdir(parents=True, exist_ok=True)
        (project_dir / ".omg" / "state" / "handoff.md").write_text("- critical-cache-key\n", encoding="utf-8")

        for i in range(3):
            payload = _base_payload(_iso(now + timedelta(seconds=i)), phrase="critical-cache-key")
            proc = _run_hook(project_dir, payload)
            assert proc.returncode == 0

        rows = _read_jsonl(project_dir / ".omg" / "state" / "compression-feedback.jsonl")
        assert len(rows) == 3
        assert "critical-cache-key" in rows[-1]["promoted_items"]


def test_always_keep_file_updated():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _enable_context_manager(project_dir)

        now = datetime.now(timezone.utc)
        _write_json(project_dir / ".omg" / "state" / "last-compaction.json", {"timestamp": _iso(now - timedelta(minutes=6))})
        (project_dir / ".omg" / "state" / "handoff.md").parent.mkdir(parents=True, exist_ok=True)
        (project_dir / ".omg" / "state" / "handoff.md").write_text("- critical-cache-key\n", encoding="utf-8")

        for i in range(3):
            proc = _run_hook(project_dir, _base_payload(_iso(now + timedelta(seconds=i))))
            assert proc.returncode == 0

        always_keep_path = project_dir / ".omg" / "state" / "always-keep.json"
        assert always_keep_path.exists()
        data = json.loads(always_keep_path.read_text(encoding="utf-8"))
        assert "critical-cache-key" in data.get("items", [])


def test_missing_compaction_file_no_crash():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _enable_context_manager(project_dir)

        proc = _run_hook(project_dir, _base_payload(_iso(datetime.now(timezone.utc))))

        assert proc.returncode == 0
        assert _read_jsonl(project_dir / ".omg" / "state" / "compression-feedback.jsonl") == []
