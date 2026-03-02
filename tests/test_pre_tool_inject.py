#!/usr/bin/env python3
"""Tests for hooks/pre-tool-inject.py.

Tests via subprocess to match real Claude Code invocation.
All hooks MUST exit 0 regardless of input (crash isolation invariant).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "pre-tool-inject.py"


def _run(payload: dict | str, project_dir: str | Path) -> subprocess.CompletedProcess[str]:
    """Run pre-tool-inject.py with given payload and project dir."""
    input_str = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=input_str,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(project_dir),
            "OAL_PLANNING_ENFORCEMENT_ENABLED": "1",
        },
        timeout=15,
    )


# ━━━ 1. Injects plan when _plan.md exists ━━━

def test_injects_plan_when_exists(tmp_path):
    """With _plan.md present, output must contain @plan-reminder."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    plan = state_dir / "_plan.md"
    plan.write_text("# My Plan\n- Step 1: Do thing\n- Step 2: Do other thing\n")

    result = _run({"tool_name": "Write"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "contextInjection" in out
    assert "@plan-reminder" in out["contextInjection"]
    assert "My Plan" in out["contextInjection"]


# ━━━ 2. No injection without _plan.md ━━━

def test_no_injection_without_plan(tmp_path):
    """Without _plan.md, output should be empty and exit 0."""
    result = _run({"tool_name": "Write"}, tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ━━━ 3. Invalid JSON input exits 0 ━━━

def test_invalid_json_exits_zero(tmp_path):
    """Invalid JSON on stdin should exit 0 gracefully (crash isolation)."""
    result = _run("not-valid-json{{{", tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ━━━ 4. Feature flag disabled → no injection ━━━

def test_feature_flag_disabled(tmp_path):
    """With planning_enforcement disabled, no injection even if _plan.md exists."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n- Step 1\n")

    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Write"}),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OAL_PLANNING_ENFORCEMENT_ENABLED": "0",
        },
        timeout=15,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ━━━ 5. Large plan file truncated to 200 chars ━━━

def test_plan_truncated_to_200_chars(tmp_path):
    """Plan content should be capped at 200 characters maximum."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    # Create a plan with 500+ chars
    long_plan = "# Big Plan\n" + ("- Step: Do something important and detailed\n" * 20)
    (state_dir / "_plan.md").write_text(long_plan)

    result = _run({"tool_name": "Bash"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    injection = out["contextInjection"]
    # "@plan-reminder: " prefix is 17 chars, so plan content ≤ 200
    plan_content = injection.replace("@plan-reminder: ", "")
    assert len(plan_content) <= 200


# ━━━ 6. Legacy .omc/_plan.md fallback ━━━

def test_legacy_omc_plan_fallback(tmp_path):
    """If _plan.md only exists under .omc/, should still inject."""
    omc_dir = tmp_path / ".omc"
    omc_dir.mkdir(parents=True)
    (omc_dir / "_plan.md").write_text("# Legacy Plan\n- Old step\n")

    result = _run({"tool_name": "Write"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "@plan-reminder" in out["contextInjection"]
    assert "Legacy Plan" in out["contextInjection"]


# ━━━ 7. Write tool gets injection (mutation tool) ━━━

def test_write_tool_gets_injection(tmp_path):
    """Write is a mutation tool — should receive plan injection."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Deploy Plan\n- Deploy to prod\n")

    result = _run({"tool_name": "Write"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "@plan-reminder" in out["contextInjection"]


# ━━━ 8. Read tool gets NO injection (read-only tool) ━━━

def test_read_tool_no_injection(tmp_path):
    """Read is a read-only tool — should NOT receive plan injection."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n- Step 1\n")

    result = _run({"tool_name": "Read"}, tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ━━━ 9. Glob tool gets NO injection (read-only tool) ━━━

def test_glob_tool_no_injection(tmp_path):
    """Glob is a read-only tool — should NOT receive plan injection."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n- Step 1\n")

    result = _run({"tool_name": "Glob"}, tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ━━━ 10. Bash tool gets injection (mutation tool) ━━━

def test_bash_tool_gets_injection(tmp_path):
    """Bash is a mutation tool — should receive plan injection."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Build Plan\n- Run build\n")

    result = _run({"tool_name": "Bash"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "@plan-reminder" in out["contextInjection"]


# ━━━ 11. Checklist progress included in injection ━━━

def test_checklist_progress_in_injection(tmp_path):
    """With checklist (2/4 done), injection should contain progress info."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Migration Plan\n")
    (state_dir / "_checklist.md").write_text(
        "- [x] First task\n"
        "- [x] Second task\n"
        "- [ ] Third task\n"
        "- [ ] Fourth task\n"
    )

    result = _run({"tool_name": "Edit"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    injection = out["contextInjection"]
    assert "@plan-reminder" in injection
    assert "2/4 done" in injection
    assert "Next: Third task" in injection


# ━━━ 12. Unknown tool gets injection (safe default) ━━━

def test_unknown_tool_gets_injection(tmp_path):
    """Unknown tool names should still receive injection (safe default)."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n- Step 1\n")

    result = _run({"tool_name": "UnknownTool"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "@plan-reminder" in out["contextInjection"]


# ━━━ 13. Missing tool_name gets injection (safe default) ━━━

def test_missing_tool_name_gets_injection(tmp_path):
    """Payload without tool_name should still receive injection."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n- Do thing\n")

    result = _run({}, tmp_path)  # No tool_name key

    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "@plan-reminder" in out["contextInjection"]


# ━━━ 14. All read-only tools skipped ━━━

def test_all_read_only_tools_skipped(tmp_path):
    """All known read-only tools should produce no injection."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n- Step 1\n")

    read_only = ['Read', 'Glob', 'Grep', 'LS', 'NotebookRead', 'WebFetch',
                 'WebSearch', 'TodoRead', 'mcp__filesystem__read_file',
                 'mcp__filesystem__list_directory']
    for tool in read_only:
        result = _run({"tool_name": tool}, tmp_path)
        assert result.returncode == 0, f"{tool} should exit 0"
        assert result.stdout.strip() == "", f"{tool} should produce no output"


# ━━━ 15. Checklist with blocked items counted correctly ━━━

def test_checklist_blocked_items(tmp_path):
    """Blocked [!] items count toward total but not done."""
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "_plan.md").write_text("# Plan\n")
    (state_dir / "_checklist.md").write_text(
        "- [x] Done task\n"
        "- [!] Blocked task\n"
        "- [ ] Pending task\n"
    )

    result = _run({"tool_name": "Write"}, tmp_path)

    assert result.returncode == 0
    out = json.loads(result.stdout)
    injection = out["contextInjection"]
    assert "1/3 done" in injection
    assert "Next: Pending task" in injection
