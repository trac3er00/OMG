"""Tests for idle-detector stop hook."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDLE_DETECTOR = ROOT / "hooks" / "idle-detector.py"


def _run_idle_detector(
    project: Path,
    *,
    enabled: bool = True,
    stdin_data: str = "{}",
) -> subprocess.CompletedProcess[str]:
    """Run idle-detector.py as a subprocess."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    if enabled:
        env["OAL_IDLE_DETECTION_ENABLED"] = "1"
    else:
        env["OAL_IDLE_DETECTION_ENABLED"] = "0"
    return subprocess.run(
        ["python3", str(IDLE_DETECTOR)],
        input=stdin_data,
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )


def _write_todo_progress(project: Path, state: dict) -> Path:
    """Write a todo_progress.json file."""
    state_dir = project / ".oal" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "todo_progress.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _write_idle_signal(project: Path, signal: dict) -> Path:
    """Write an existing idle_signal.json (to simulate prior calls)."""
    state_dir = project / ".oal" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "idle_signal.json"
    path.write_text(json.dumps(signal), encoding="utf-8")
    return path


def _read_idle_signal(project: Path) -> dict | None:
    """Read idle_signal.json if it exists."""
    path = project / ".oal" / "state" / "idle_signal.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --- Test 1: No todo file → not idle ---

def test_no_todo_file_not_idle(tmp_path: Path):
    """When no todo_progress.json exists, signal should be not-idle."""
    project = tmp_path
    (project / ".oal" / "state").mkdir(parents=True, exist_ok=True)

    proc = _run_idle_detector(project)
    assert proc.returncode == 0

    signal = _read_idle_signal(project)
    assert signal is not None
    assert signal["idle_detected"] is False
    assert signal["incomplete_count"] == 0


# --- Test 2: Empty incomplete list → not idle ---

def test_empty_incomplete_not_idle(tmp_path: Path):
    """When incomplete list is empty, signal should be not-idle."""
    project = tmp_path
    _write_todo_progress(project, {
        "incomplete": [],
        "complete": ["task A"],
        "total": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })

    proc = _run_idle_detector(project)
    assert proc.returncode == 0

    signal = _read_idle_signal(project)
    assert signal is not None
    assert signal["idle_detected"] is False
    assert signal["incomplete_count"] == 0


# --- Test 3: Non-empty incomplete, first call → not idle yet ---

def test_first_call_with_incomplete_not_idle(tmp_path: Path):
    """First call with incomplete todos should NOT signal idle (no prior call)."""
    project = tmp_path
    _write_todo_progress(project, {
        "incomplete": ["fix bug", "write tests"],
        "complete": [],
        "total": 2,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })

    proc = _run_idle_detector(project)
    assert proc.returncode == 0

    signal = _read_idle_signal(project)
    assert signal is not None
    assert signal["idle_detected"] is False
    assert signal["incomplete_count"] == 2
    assert signal["call_count"] == 1


# --- Test 4: Non-empty incomplete, second call → idle detected ---

def test_second_call_with_incomplete_idle_detected(tmp_path: Path):
    """Second call with incomplete todos SHOULD signal idle."""
    project = tmp_path
    _write_todo_progress(project, {
        "incomplete": ["fix bug", "write tests", "deploy"],
        "complete": ["setup"],
        "total": 4,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })

    # Simulate a prior call by writing existing signal with call_count=1
    _write_idle_signal(project, {
        "idle_detected": False,
        "incomplete_count": 3,
        "incomplete_items": ["fix bug", "write tests", "deploy"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "stop_hook",
        "call_count": 1,
    })

    proc = _run_idle_detector(project)
    assert proc.returncode == 0

    signal = _read_idle_signal(project)
    assert signal is not None
    assert signal["idle_detected"] is True
    assert signal["incomplete_count"] == 3
    assert signal["call_count"] == 2
    assert len(signal["incomplete_items"]) == 3


# --- Test 5: Feature flag disabled → exits without writing signal ---

def test_feature_flag_disabled_no_signal(tmp_path: Path):
    """When feature flag is disabled, hook should exit without writing signal."""
    project = tmp_path
    _write_todo_progress(project, {
        "incomplete": ["fix bug"],
        "complete": [],
        "total": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })

    proc = _run_idle_detector(project, enabled=False)
    assert proc.returncode == 0

    # Signal file should NOT be created
    signal = _read_idle_signal(project)
    assert signal is None


# --- Test 6: Signal schema validation ---

def test_signal_schema(tmp_path: Path):
    """Signal file must contain all required fields with correct types."""
    project = tmp_path
    _write_todo_progress(project, {
        "incomplete": ["task1", "task2", "task3", "task4"],
        "complete": ["done1"],
        "total": 5,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })

    # Simulate prior call
    _write_idle_signal(project, {
        "idle_detected": False,
        "incomplete_count": 4,
        "incomplete_items": ["task1", "task2", "task3"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "stop_hook",
        "call_count": 1,
    })

    proc = _run_idle_detector(project)
    assert proc.returncode == 0

    signal = _read_idle_signal(project)
    assert signal is not None

    # Required fields
    assert "idle_detected" in signal
    assert "incomplete_count" in signal
    assert "incomplete_items" in signal
    assert "timestamp" in signal
    assert "trigger" in signal
    assert "call_count" in signal

    # Type checks
    assert isinstance(signal["idle_detected"], bool)
    assert isinstance(signal["incomplete_count"], int)
    assert isinstance(signal["incomplete_items"], list)
    assert isinstance(signal["timestamp"], str)
    assert signal["trigger"] == "stop_hook"
    assert isinstance(signal["call_count"], int)

    # Truncation: only first 3 incomplete items
    assert len(signal["incomplete_items"]) == 3
    assert signal["incomplete_items"] == ["task1", "task2", "task3"]

    # Timestamp is valid ISO format
    datetime.fromisoformat(signal["timestamp"])


# --- Test 7: Always exits 0 (never blocks) ---

def test_always_exits_zero(tmp_path: Path):
    """Hook must always exit 0 regardless of state."""
    project = tmp_path

    # Case A: No todo file
    proc = _run_idle_detector(project)
    assert proc.returncode == 0
    # stdout should be empty (no block decision)
    assert proc.stdout.strip() == ""

    # Case B: With incomplete todos and prior calls
    _write_todo_progress(project, {
        "incomplete": ["bug"],
        "complete": [],
        "total": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })
    _write_idle_signal(project, {
        "idle_detected": False,
        "incomplete_count": 1,
        "incomplete_items": ["bug"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "stop_hook",
        "call_count": 5,
    })

    proc = _run_idle_detector(project)
    assert proc.returncode == 0
    # Must not emit a block decision
    assert proc.stdout.strip() == ""


# --- Test 8: Malformed todo file → graceful not-idle ---

def test_malformed_todo_file_graceful(tmp_path: Path):
    """Malformed todo_progress.json should result in not-idle, not crash."""
    project = tmp_path
    state_dir = project / ".oal" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "todo_progress.json").write_text("not valid json{{{", encoding="utf-8")

    proc = _run_idle_detector(project)
    assert proc.returncode == 0

    signal = _read_idle_signal(project)
    assert signal is not None
    assert signal["idle_detected"] is False
