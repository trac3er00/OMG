"""Tests for session-start.py standalone state behavior."""


def test_session_start_uses_omg_state_paths():
    """SessionStart should point to .omg canonical paths."""
    with open("hooks/session-start.py") as f:
        content = f.read()

    assert ".omg/state" in content
    assert "resolve_state_file" in content
    assert "resolve_state_dir" in content
    assert "OMC_STATE_DIR" not in content

def test_handoff_filename_contract():
    """Verify session-start reads handoff.md (not OMG:handoff.md)."""
    with open("hooks/session-start.py") as f:
        content = f.read()

    # Should look for handoff.md
    assert '"handoff.md"' in content
    # Should NOT look for OMG:handoff.md
    assert "OMG:handoff.md" not in content

def test_context_budget_uses_constant():
    """§Doc1: Budget should use BUDGET_SESSION_TOTAL constant (2000 chars)."""
    with open("hooks/session-start.py") as f:
        content = f.read()
    # Task 4 replaced magic number with named constant from _budget.py
    assert "from _budget import BUDGET_SESSION_TOTAL" in content or "BUDGET_SESSION_TOTAL" in content
    assert "MAX_CONTEXT_CHARS = 1500" not in content  # old magic number gone

def test_handoff_staleness_check():
    """§Doc1: Stale handoffs (>48h) should be skipped."""
    with open("hooks/session-start.py") as f:
        content = f.read()
    assert "age_hours" in content
    assert "handoff_fresh" in content
    assert "< 48" in content

def test_non_discoverable_principle():
    """§Doc1: Profile injection should skip discoverable info."""
    with open("hooks/session-start.py") as f:
        content = f.read()
    assert "conventions" in content


def test_session_start_does_not_advertise_legacy_omc_aliases_by_default():
    with open("hooks/session-start.py") as f:
        content = f.read()
    assert "OMG_INCLUDE_LEGACY_ALIASES" in content
    assert "omg-teams" not in content.split("OMG_INCLUDE_LEGACY_ALIASES", 1)[0]


# ━━━ Subprocess-based runtime behavior tests ━━━
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "hooks" / "session-start.py"


def _run_session_start(project_dir, payload=None):
    """Run session-start.py with given project dir."""
    if payload is None:
        payload = {}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)},
        timeout=15,
    )


def test_session_start_invalid_json_exits_zero(tmp_path):
    """Invalid JSON input must exit 0 — crash isolation invariant."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not valid json",
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        timeout=15,
    )
    assert proc.returncode == 0


def test_session_start_profile_injection(tmp_path):
    """With a profile.yaml, session-start should inject @project context."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "profile.yaml").write_text(
        'name: TestProject\nstack: Python+FastAPI\nconventions:\n  naming: snake_case\n  test_cmd: pytest\n'
    )

    proc = _run_session_start(tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        data = json.loads(proc.stdout)
        ctx = data.get("contextInjection", "")
        assert "@project" in ctx
        assert "TestProject" in ctx


def test_session_start_missing_state_dir_exits_zero(tmp_path):
    """With no .omg directory at all, session-start should still exit 0."""
    proc = _run_session_start(tmp_path)
    assert proc.returncode == 0


def test_session_start_working_memory_injection(tmp_path):
    """With working-memory.md, session-start should inject WORKING MEMORY."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "working-memory.md").write_text(
        "## Current Task\nImplementing auth middleware\n## Next\nAdd JWT validation\n"
    )

    proc = _run_session_start(tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        data = json.loads(proc.stdout)
        ctx = data.get("contextInjection", "")
        assert "WORKING MEMORY" in ctx


# ━━━ Memory injection tests ━━━


def test_memory_injected_when_files_exist(tmp_path):
    """With memory dir + files + flag enabled, @recent-memory: should appear."""
    state_dir = tmp_path / ".omg" / "state"
    memory_dir = state_dir / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "2026-02-28-test.md").write_text("Fixed auth bug")

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_MEMORY_ENABLED": "true"}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({}),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip(), "Expected contextInjection output"
    data = json.loads(proc.stdout)
    ctx = data.get("contextInjection", "")
    assert "@recent-memory:" in ctx
    assert "Fixed auth bug" in ctx


def test_memory_not_injected_when_no_dir(tmp_path):
    """Without .omg/state/memory/, no @recent-memory: should appear."""
    # No memory dir created — just an empty project dir
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_MEMORY_ENABLED": "true"}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({}),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    output = proc.stdout.strip()
    if output:
        data = json.loads(output)
        ctx = data.get("contextInjection", "")
        assert "@recent-memory:" not in ctx


def test_memory_not_injected_when_flag_disabled(tmp_path):
    """With memory dir but flag disabled, no @recent-memory: should appear."""
    state_dir = tmp_path / ".omg" / "state"
    memory_dir = state_dir / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "2026-02-28-test.md").write_text("Fixed auth bug")

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_MEMORY_ENABLED": "false"}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({}),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    output = proc.stdout.strip()
    if output:
        data = json.loads(output)
        ctx = data.get("contextInjection", "")
        assert "@recent-memory:" not in ctx


def test_session_start_total_output_under_2000(tmp_path):
    """Even with all sections + memory, total output must stay under 2000 chars."""
    state_dir = tmp_path / ".omg" / "state"
    memory_dir = state_dir / "memory"
    memory_dir.mkdir(parents=True)
    (state_dir / "profile.yaml").write_text(
        'name: TestProject\nstack: Python+FastAPI\nconventions:\n  naming: snake_case\n'
    )
    (state_dir / "working-memory.md").write_text("## Current Task\nDoing stuff\n")
    (memory_dir / "2026-02-28-test.md").write_text("Fixed auth bug")

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_MEMORY_ENABLED": "true"}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({}),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    if proc.stdout.strip():
        data = json.loads(proc.stdout)
        ctx = data.get("contextInjection", "")
        assert len(ctx) <= 2000, f"Output too large: {len(ctx)} chars"


# ━━━ Idle detection tests ━━━


def test_idle_session_caps_output_at_200_chars(tmp_path):
    """Idle session (no plan, no handoff, no memory) caps output at BUDGET_SESSION_IDLE (200)."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    # Profile + large working memory, but NO plan/handoff/memory → idle
    (state_dir / "profile.yaml").write_text(
        'name: TestProject\nstack: Python+FastAPI\nconventions:\n  naming: snake_case\n  test_cmd: pytest\n'
    )
    (state_dir / "working-memory.md").write_text(
        "## Current Task\n" + "Implementing a very long task description " * 15 + "\n"
    )

    proc = _run_session_start(tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        data = json.loads(proc.stdout)
        ctx = data.get("contextInjection", "")
        assert len(ctx) <= 200, f"Idle session output too large: {len(ctx)} chars (max 200)"


def test_active_session_with_plan_allows_full_budget(tmp_path):
    """Active session (with _plan.md) uses full budget, output can exceed 200 chars."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "profile.yaml").write_text(
        'name: TestProject\nstack: Python+FastAPI\nconventions:\n  naming: snake_case\n  test_cmd: pytest\n'
    )
    (state_dir / "working-memory.md").write_text(
        "## Current Task\n" + "Implementing a very long task description " * 15 + "\n"
    )
    # _plan.md makes the session "active" → no idle cap
    (state_dir / "_plan.md").write_text(
        "# Implementation Plan\n## Phase 1\nBuild auth module\n## Phase 2\nAdd tests\n"
    )

    proc = _run_session_start(tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        data = json.loads(proc.stdout)
        ctx = data.get("contextInjection", "")
        assert len(ctx) > 200, f"Active session should exceed idle cap, got {len(ctx)} chars"
        assert len(ctx) <= 2000, f"Active session should respect full budget, got {len(ctx)} chars"


def test_active_session_with_memory_not_idle(tmp_path):
    """Session with memory files (but no plan/handoff) is NOT idle."""
    state_dir = tmp_path / ".omg" / "state"
    memory_dir = state_dir / "memory"
    memory_dir.mkdir(parents=True)
    (state_dir / "profile.yaml").write_text(
        'name: TestProject\nstack: Python+FastAPI\nconventions:\n  naming: snake_case\n  test_cmd: pytest\n'
    )
    (state_dir / "working-memory.md").write_text(
        "## Current Task\n" + "Implementing a very long task description " * 15 + "\n"
    )
    (memory_dir / "2026-02-28-note.md").write_text("Fixed auth bug")

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_MEMORY_ENABLED": "true"}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({}),
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    if proc.stdout.strip():
        data = json.loads(proc.stdout)
        ctx = data.get("contextInjection", "")
        # Memory files make session active → full budget
        assert len(ctx) > 200, f"Session with memory should not be idle-capped, got {len(ctx)} chars"
