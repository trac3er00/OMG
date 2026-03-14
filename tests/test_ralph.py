import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run_dispatcher(tmp_path: Path, payload: dict[str, Any], extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_RALPH_LOOP_ENABLED"] = "1"
    # Disable planning enforcement by default to isolate ralph tests
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )


def _write_ralph_state(tmp_path: Path, state: dict[str, Any]) -> Path:
    path = tmp_path / ".omg" / "state" / "ralph-loop.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def test_ralph_blocks_when_active(tmp_path: Path):
    _ = _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 0,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "fix all tests" in output["reason"]


def test_ralph_increments_iteration(tmp_path: Path):
    path = _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 0,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["iteration"] == 1


def test_ralph_stops_at_max(tmp_path: Path):
    path = _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 50,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    assert "\"decision\"" not in result.stdout
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["active"] is False


def test_ralph_inactive_allows_completion(tmp_path: Path):
    _ = _write_ralph_state(
        tmp_path,
        {
            "active": False,
            "iteration": 1,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    assert result.stdout == ""


def test_ralph_missing_file_allows_completion(tmp_path: Path):
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    assert result.stdout == ""


def test_ralph_block_reason_includes_progress(tmp_path: Path):
    """Reason includes checklist progress when checklist_path is set."""
    # Create checklist with 2/4 done
    checklist = tmp_path / ".omg" / "state" / "_checklist.md"
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(
        "- [x] task one\n"
        "- [x] task two\n"
        "- [ ] task three\n"
        "- [ ] task four\n",
        encoding="utf-8",
    )
    _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 2,
            "max_iterations": 50,
            "original_prompt": "finish all tasks",
            "checklist_path": ".omg/state/_checklist.md",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "Progress: 2/4" in output["reason"]


def test_ralph_block_reason_includes_original_prompt(tmp_path: Path):
    """Reason includes the original_prompt text."""
    _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 5,
            "max_iterations": 50,
            "original_prompt": "refactor the auth module",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "refactor the auth module" in output["reason"]


def test_ralph_block_reason_includes_stop_instruction(tmp_path: Path):
    """Reason includes the /OMG:ralph-stop escape hatch instruction."""
    _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 1,
            "max_iterations": 50,
            "original_prompt": "deploy feature",
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "/OMG:ralph-stop" in output["reason"]


def test_ralph_commands_exist():
    """Command files for ralph-start and ralph-stop exist."""
    assert (ROOT / "commands" / "OMG:ralph-start.md").exists()
    assert (ROOT / "commands" / "OMG:ralph-stop.md").exists()


def test_ralph_expires_after_timeout(tmp_path: Path):
    """Ralph state expires after default timeout (configurable via OMG_RALPH_TIMEOUT_MINUTES)."""
    from datetime import datetime, timedelta, timezone
    
    # Create state with started_at = 31 minutes ago
    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=31)).isoformat()
    
    _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 5,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
            "started_at": started_at,
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    # Should not block (expired)
    assert result.stdout == ""


def test_ralph_active_within_timeout(tmp_path: Path):
    """Ralph state remains active within default timeout window."""
    from datetime import datetime, timedelta, timezone
    
    # Create state with started_at = 5 minutes ago
    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=5)).isoformat()
    
    _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 5,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
            "started_at": started_at,
        },
    )
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    # Should block (still active)
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "fix all tests" in output["reason"]


def test_ralph_timeout_configurable(tmp_path: Path):
    """Ralph timeout is configurable via OMG_RALPH_TIMEOUT_MINUTES env var."""
    from datetime import datetime, timedelta, timezone
    
    # Create state with started_at = 15 minutes ago
    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=15)).isoformat()
    
    _write_ralph_state(
        tmp_path,
        {
            "active": True,
            "iteration": 5,
            "max_iterations": 50,
            "original_prompt": "fix all tests",
            "started_at": started_at,
        },
    )
    # Set timeout to 10 minutes (should expire)
    result = _run_dispatcher(
        tmp_path,
        {"stop_hook_active": False},
        extra_env={"OMG_RALPH_TIMEOUT_MINUTES": "10"},
    )
    assert result.returncode == 0
    # Should not block (expired with 10-min timeout)
    assert result.stdout == ""


def test_ralph_invalid_timeout_fallback(tmp_path: Path):
    """Non-numeric OMG_RALPH_TIMEOUT_MINUTES falls back to default, no crash."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=5)).isoformat()

    _write_ralph_state(tmp_path, {
        "active": True, "iteration": 0, "max_iterations": 50,
        "original_prompt": "fix tests",
        "started_at": started_at,
    })

    # Non-numeric timeout: should fall back to default (10 minutes)
    result = _run_dispatcher(
        tmp_path, {"stop_hook_active": False},
        extra_env={"OMG_RALPH_TIMEOUT_MINUTES": "not_a_number"},
    )
    assert result.returncode == 0
    # Within default 10-minute timeout (5 < 10) -> should block
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "fix tests" in output["reason"]


def test_ralph_empty_timeout_fallback(tmp_path: Path):
    """Empty OMG_RALPH_TIMEOUT_MINUTES falls back to default."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=5)).isoformat()

    _write_ralph_state(tmp_path, {
        "active": True, "iteration": 0, "max_iterations": 50,
        "original_prompt": "fix tests",
        "started_at": started_at,
    })

    result = _run_dispatcher(
        tmp_path, {"stop_hook_active": False},
        extra_env={"OMG_RALPH_TIMEOUT_MINUTES": ""},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "fix tests" in output["reason"]


def test_invalid_timeout_env(tmp_path: Path):
    """Regression guard: non-numeric OMG_RALPH_TIMEOUT_MINUTES falls back to default (no crash).

    Named for QA scenario `-k invalid_timeout_env`.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(minutes=5)).isoformat()

    _write_ralph_state(tmp_path, {
        "active": True, "iteration": 0, "max_iterations": 50,
        "original_prompt": "fix tests",
        "started_at": started_at,
    })

    # Non-numeric value: dispatcher must fall back to 10-minute default, not crash
    result = _run_dispatcher(
        tmp_path, {"stop_hook_active": False},
        extra_env={"OMG_RALPH_TIMEOUT_MINUTES": "INVALID_VALUE"},
    )
    assert result.returncode == 0, f"Dispatcher crashed on invalid timeout: {result.stderr}"
    # Within default 10-minute timeout (5 < 10) -> should still block
    output = json.loads(result.stdout)
    assert output["decision"] == "block", "Expected block with fallback default timeout"
