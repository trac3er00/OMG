#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)


def run_session_end_capture(tmp_path: Path, session_id: str, memory_enabled: bool) -> subprocess.CompletedProcess[str]:
    hook_path = os.path.join(HOOKS_DIR, "session-end-capture.py")
    env = os.environ.copy()
    env["OMG_MEMORY_ENABLED"] = "true" if memory_enabled else "false"
    input_data = json.dumps({"session_id": session_id, "cwd": str(tmp_path)})
    return subprocess.run(
        ["python3", hook_path],
        input=input_data,
        capture_output=True,
        text=True,
        env=env,
    )


def test_memory_file_created_on_session_end(tmp_path: Path):
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    _ = ledger_dir.mkdir(parents=True)
    ledger_path = ledger_dir / "tool-ledger.jsonl"
    entries = [
        {"tool": "Read", "path": "hooks/session-end-capture.py"},
        {"tool": "Bash", "file": "tests/test_memory_capture.py"},
        {"tool": "Edit", "path": "hooks/_memory.py"},
    ]
    _ = ledger_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

    result = run_session_end_capture(tmp_path, "test-session-123456", True)

    memory_dir = tmp_path / ".omg" / "state" / "memory"
    assert result.returncode == 0
    assert memory_dir.exists()
    assert len(list(memory_dir.glob("*.md"))) >= 1


def test_memory_file_under_500_chars(tmp_path: Path):
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    _ = ledger_dir.mkdir(parents=True)
    ledger_path = ledger_dir / "tool-ledger.jsonl"
    long_name = "x" * 400
    entries = [{"tool": "Write", "path": long_name} for _ in range(10)]
    _ = ledger_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

    result = run_session_end_capture(tmp_path, "long-session-id-abcdef", True)

    memory_dir = tmp_path / ".omg" / "state" / "memory"
    memory_files = list(memory_dir.glob("*.md"))
    assert result.returncode == 0
    assert memory_files
    assert len(memory_files[0].read_text()) <= 500


def test_memory_skipped_when_flag_disabled(tmp_path: Path):
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    _ = ledger_dir.mkdir(parents=True)
    _ = (ledger_dir / "tool-ledger.jsonl").write_text('{"tool":"Read","path":"x"}\n')

    result = run_session_end_capture(tmp_path, "test-session-disabled", False)

    memory_dir = tmp_path / ".omg" / "state" / "memory"
    memory_files = list(memory_dir.glob("*.md")) if memory_dir.exists() else []
    assert result.returncode == 0
    assert memory_files == []


def test_exits_zero_always(tmp_path: Path):
    result = run_session_end_capture(tmp_path, "broken-state", True)
    assert result.returncode == 0
