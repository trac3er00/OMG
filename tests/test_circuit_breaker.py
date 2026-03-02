#!/usr/bin/env python3
"""Baseline regression tests for hooks/circuit-breaker.py.

Tests via subprocess to match real Claude Code invocation.
All hooks MUST exit 0 regardless of input (crash isolation invariant).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "circuit-breaker.py"


def _run(payload: dict, project_dir: str | Path) -> subprocess.CompletedProcess[str]:
    """Run circuit-breaker.py with given payload and project dir."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)},
        timeout=15,
    )


def _read_tracker(project: Path) -> dict:
    """Read failure-tracker.json from project dir."""
    tracker_path = project / ".oal" / "state" / "ledger" / "failure-tracker.json"
    if not tracker_path.exists():
        return {}
    return json.loads(tracker_path.read_text())


def _write_tracker(project: Path, data: dict) -> None:
    """Write failure-tracker.json to project dir."""
    tracker_path = project / ".oal" / "state" / "ledger" / "failure-tracker.json"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(data, indent=2))


# ━━━ 1. Valid failure input → creates/updates failure-tracker.json ━━━

def test_bash_failure_creates_tracker(tmp_path):
    """A Bash tool with non-zero exit code should create a failure entry."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "Test failed"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    assert any("npm test" in k for k in tracker), f"Expected 'npm test' pattern in tracker keys: {list(tracker.keys())}"
    entry = next(v for k, v in tracker.items() if "npm test" in k)
    assert entry["count"] == 1
    assert "Test failed" in entry["errors"]


def test_write_failure_creates_tracker(tmp_path):
    """A Write tool with success=false should create a failure entry."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "src/app.py"},
        "tool_response": {"success": False},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    assert any("Write" in k for k in tracker), f"Expected Write pattern in tracker: {list(tracker.keys())}"


# ━━━ 2. Invalid JSON → exit 0 (crash isolation) ━━━

def test_invalid_json_exits_zero(tmp_path):
    """Invalid JSON input must exit 0 — crash isolation invariant."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not valid json {{{{",
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        timeout=15,
    )
    assert proc.returncode == 0, f"Expected exit 0 on invalid JSON, got {proc.returncode}. stderr: {proc.stderr}"


def test_empty_input_exits_zero(tmp_path):
    """Empty stdin must exit 0."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        timeout=15,
    )
    assert proc.returncode == 0


# ━━━ 3. Pattern normalization ━━━

def test_npm_run_test_normalized_to_npm_test(tmp_path):
    """'npm run test' and 'npm test' should be treated as the same pattern.

    The hook strips 'run' from command words, so both should map to 'Bash:npm test'.
    """
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    # First failure: 'npm run test'
    payload1 = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm run test"},
        "tool_response": {"exitCode": 1, "stderr": "err1"},
    }
    proc1 = _run(payload1, tmp_path)
    assert proc1.returncode == 0

    # Second failure: 'npm test'
    payload2 = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "err2"},
    }
    proc2 = _run(payload2, tmp_path)
    assert proc2.returncode == 0

    tracker = _read_tracker(tmp_path)
    # Both should map to the same pattern key, so count should be 2 (not two separate entries)
    npm_entries = {k: v for k, v in tracker.items() if "npm" in k and "test" in k}
    total_count = sum(v.get("count", 0) for v in npm_entries.values())
    assert total_count == 2, f"Expected combined count of 2 for normalized npm test pattern. Got entries: {npm_entries}"


def test_pnpm_normalized_to_npm(tmp_path):
    """pnpm commands should be normalized to npm equivalents."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pnpm test"},
        "tool_response": {"exitCode": 1, "stderr": "pnpm fail"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    # pnpm should be normalized to npm
    keys = list(tracker.keys())
    assert any("npm" in k for k in keys), f"Expected 'pnpm' to be normalized to 'npm'. Keys: {keys}"


# ━━━ 4. Success clears failure count ━━━

def test_success_clears_failure_count(tmp_path):
    """A successful tool execution should clear the matching failure pattern."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    # Pre-seed tracker with a failure
    from datetime import datetime, timezone
    _write_tracker(tmp_path, {
        "Bash:npm test": {
            "count": 2,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["err1", "err2"],
        }
    })

    # Now send a success for the same command
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 0},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    assert "Bash:npm test" not in tracker, f"Expected 'Bash:npm test' to be cleared. Tracker: {tracker}"


# ━━━ 5. Missing state files → graceful degradation (exit 0) ━━━

def test_missing_state_dir_exits_zero(tmp_path):
    """If .oal/state/ledger/ doesn't exist, hook should still exit 0."""
    # tmp_path is empty — no .oal structure at all
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "fail"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0


def test_corrupted_tracker_exits_zero(tmp_path):
    """If failure-tracker.json contains garbage, hook should exit 0."""
    tracker_path = tmp_path / ".oal" / "state" / "ledger" / "failure-tracker.json"
    tracker_path.parent.mkdir(parents=True)
    tracker_path.write_text("this is not json!!!")

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "fail"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    # Should have overwritten with valid data
    tracker = _read_tracker(tmp_path)
    assert isinstance(tracker, dict)


# ━━━ 6. Warning/escalation messages at thresholds ━━━

def test_count_3_emits_warning(tmp_path):
    """After 3 failures for the same pattern, stderr should contain a warning."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    from datetime import datetime, timezone
    _write_tracker(tmp_path, {
        "Bash:npm test": {
            "count": 2,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["err1", "err2"],
        }
    })

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "err3"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0
    assert "CIRCUIT BREAKER WARNING" in proc.stderr


def test_count_5_emits_escalation(tmp_path):
    """After 5 failures, stderr should contain escalation instructions."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    from datetime import datetime, timezone
    _write_tracker(tmp_path, {
        "Bash:npm test": {
            "count": 4,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["e1", "e2", "e3"],
        }
    })

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "err5"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0
    assert "ESCALATE NOW" in proc.stderr
    assert "/OAL:escalate" in proc.stderr


# ━━━ 7. Non-failure input → no tracker mutation ━━━

def test_success_with_no_prior_failures_is_noop(tmp_path):
    """Successful Bash with no prior failures should not create tracker entries."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "tool_response": {"exitCode": 0},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    assert tracker == {} or not tracker


# ━━━ 8. Error deduplication ━━━

def test_duplicate_errors_not_stored_twice(tmp_path):
    """Same error message in consecutive failures should be deduplicated."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 1, "stderr": "same error"},
    }

    # Run twice with identical error
    _run(payload, tmp_path)
    _run(payload, tmp_path)

    tracker = _read_tracker(tmp_path)
    entry = next(v for k, v in tracker.items() if "npm" in k)
    # Should have count=2 but only 1 unique error stored
    assert entry["count"] == 2
    assert entry["errors"].count("same error") == 1


# ━━━ 9. Python -m normalization ━━━

def test_python3_m_pytest_normalized_to_pytest(tmp_path):
    """'python3 -m pytest' and 'pytest' should be treated as the same pattern."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    # First failure: 'python3 -m pytest'
    payload1 = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 -m pytest tests/"},
        "tool_response": {"exitCode": 1, "stderr": "err1"},
    }
    proc1 = _run(payload1, tmp_path)
    assert proc1.returncode == 0

    # Second failure: 'pytest'
    payload2 = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/"},
        "tool_response": {"exitCode": 1, "stderr": "err2"},
    }
    proc2 = _run(payload2, tmp_path)
    assert proc2.returncode == 0

    tracker = _read_tracker(tmp_path)
    # Both should map to the same pattern key
    pytest_entries = {k: v for k, v in tracker.items() if "pytest" in k}
    total_count = sum(v.get("count", 0) for v in pytest_entries.values())
    assert total_count == 2, f"Expected combined count of 2 for normalized pytest pattern. Got entries: {pytest_entries}"


def test_python_m_pytest_normalized_to_pytest(tmp_path):
    """'python -m pytest' should normalize to 'pytest'."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest"},
        "tool_response": {"exitCode": 1, "stderr": "python fail"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    keys = list(tracker.keys())
    assert any("pytest" in k for k in keys), f"Expected 'pytest' in pattern. Keys: {keys}"


# ━━━ 10. npx/bunx normalization ━━━

def test_npx_jest_normalized_to_jest(tmp_path):
    """'npx jest' and 'jest' should be treated as the same pattern."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    # First failure: 'npx jest'
    payload1 = {
        "tool_name": "Bash",
        "tool_input": {"command": "npx jest"},
        "tool_response": {"exitCode": 1, "stderr": "err1"},
    }
    proc1 = _run(payload1, tmp_path)
    assert proc1.returncode == 0

    # Second failure: 'jest'
    payload2 = {
        "tool_name": "Bash",
        "tool_input": {"command": "jest"},
        "tool_response": {"exitCode": 1, "stderr": "err2"},
    }
    proc2 = _run(payload2, tmp_path)
    assert proc2.returncode == 0

    tracker = _read_tracker(tmp_path)
    jest_entries = {k: v for k, v in tracker.items() if "jest" in k}
    total_count = sum(v.get("count", 0) for v in jest_entries.values())
    assert total_count == 2, f"Expected combined count of 2 for normalized jest pattern. Got entries: {jest_entries}"


def test_bunx_jest_normalized_to_jest(tmp_path):
    """'bunx jest' should normalize to 'jest'."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "bunx jest --watch"},
        "tool_response": {"exitCode": 1, "stderr": "bunx fail"},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    keys = list(tracker.keys())
    assert any("jest" in k for k in keys), f"Expected 'jest' in pattern. Keys: {keys}"


# ━━━ 11. Success clears similar variants ━━━

def test_success_clears_similar_variants(tmp_path):
    """Success on 'npm test' should clear 'npm run test' and other variants."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    from datetime import datetime, timezone
    # Pre-seed tracker with multiple variants
    _write_tracker(tmp_path, {
        "Bash:npm test": {
            "count": 1,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["err1"],
        },
        "Bash:npm run test": {
            "count": 1,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["err2"],
        },
    })

    # Success on 'npm test'
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_response": {"exitCode": 0},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    # Both variants should be cleared
    assert "Bash:npm test" not in tracker, f"Expected 'Bash:npm test' to be cleared. Tracker: {tracker}"
    assert "Bash:npm run test" not in tracker, f"Expected 'Bash:npm run test' to be cleared. Tracker: {tracker}"


def test_success_clears_pytest_variants(tmp_path):
    """Success on 'pytest' should clear 'python3 -m pytest' and 'python -m pytest'."""
    (tmp_path / ".oal" / "state" / "ledger").mkdir(parents=True)

    from datetime import datetime, timezone
    # Pre-seed tracker with multiple variants
    _write_tracker(tmp_path, {
        "Bash:pytest tests/": {
            "count": 1,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["err1"],
        },
        "Bash:python3 -m pytest tests/": {
            "count": 1,
            "last_failure": datetime.now(timezone.utc).isoformat(),
            "errors": ["err2"],
        },
    })

    # Success on 'python3 -m pytest' (which normalizes to 'pytest')
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 -m pytest tests/"},
        "tool_response": {"exitCode": 0},
    }
    proc = _run(payload, tmp_path)
    assert proc.returncode == 0

    tracker = _read_tracker(tmp_path)
    # Both variants should be cleared
    assert "Bash:pytest tests/" not in tracker, f"Expected 'Bash:pytest tests/' to be cleared. Tracker: {tracker}"
    assert "Bash:python3 -m pytest tests/" not in tracker, f"Expected 'Bash:python3 -m pytest tests/' to be cleared. Tracker: {tracker}"
