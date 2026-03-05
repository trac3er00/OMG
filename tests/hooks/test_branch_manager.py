"""Tests for branch_manager SessionStart hook (v2.0 — Task 10)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "hooks"
SCRIPT_PATH = HOOKS_DIR / "branch_manager.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git command in temp repo."""
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True, text=True, check=True,
    )


def _init_repo(branch: str = "main") -> Path:
    """Create a temp git repo on the given branch with an initial commit."""
    d = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-b", branch, str(d)],
                   capture_output=True, text=True, check=True)
    _git(d, "config", "user.email", "test@test.com")
    _git(d, "config", "user.name", "Test")
    (d / "README.md").write_text("init")
    _git(d, "add", ".")
    _git(d, "commit", "-m", "init")
    return d


def _run_hook(
    payload: dict[str, Any],
    project_dir: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run branch_manager.py as a subprocess."""
    full_env = os.environ.copy()
    full_env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    # Ensure feature flag is ON by default in tests
    full_env.setdefault("OMG_GIT_WORKFLOW_ENABLED", "1")
    if env:
        full_env.update(env)

    return subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(project_dir),
        env=full_env,
        check=False,
    )


def _current_branch(repo: Path) -> str:
    """Get current branch of a repo."""
    r = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip()


def _make_payload(session_id: str = "test-session-123") -> dict[str, Any]:
    return {"hook_event": "SessionStart", "session_id": session_id}


# ────────────────────────────────────────────
# Test 1: Creates feature branch when on main
# ────────────────────────────────────────────
def test_creates_feature_branch_when_on_main():
    repo = _init_repo("main")
    try:
        # Create .omg/state with a plan that has a title
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "_plan.md").write_text("# Fix login validation bug\n\nDetails here.\n")

        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0, f"Hook must exit 0. stderr: {proc.stderr}"
        assert proc.stdout.strip() == "", "SessionStart side-effect hook must not emit stdout"

        branch = _current_branch(repo)
        assert branch.startswith("feature/"), f"Expected feature/ branch, got: {branch}"
        assert "fix-login-validation-bug" in branch
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 2: Creates feature branch when on master
# ────────────────────────────────────────────
def test_creates_feature_branch_when_on_master():
    repo = _init_repo("master")
    try:
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "_checklist.md").write_text("- [ ] Refactor database queries\n- [ ] Add tests\n")

        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0
        branch = _current_branch(repo)
        assert branch.startswith("feature/"), f"Expected feature/ branch, got: {branch}"
        assert "refactor-database-queries" in branch
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 3: Creates feature branch when on develop
# ────────────────────────────────────────────
def test_creates_feature_branch_when_on_develop():
    repo = _init_repo("develop")
    try:
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "working-memory.md").write_text("## Entry 1\nOld task\n\n## Entry 2\nImplement caching layer\n")

        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0
        branch = _current_branch(repo)
        assert branch.startswith("feature/"), f"Expected feature/ branch, got: {branch}"
        assert "implement-caching-layer" in branch
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 4: No-op when already on feature branch
# ────────────────────────────────────────────
def test_noop_when_on_feature_branch():
    repo = _init_repo("main")
    try:
        _git(repo, "checkout", "-b", "feature/existing-work")
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "_plan.md").write_text("# Some plan\n")

        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0
        assert _current_branch(repo) == "feature/existing-work", "Branch should NOT change"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 5: No-op when no .git directory
# ────────────────────────────────────────────
def test_noop_when_no_git_directory():
    d = Path(tempfile.mkdtemp())
    try:
        omg_state = d / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "_plan.md").write_text("# A plan\n")

        proc = _run_hook(_make_payload(), d)

        assert proc.returncode == 0, "Must exit 0 even without .git"
        assert proc.stdout.strip() == "", "No stdout on no-op"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ────────────────────────────────────────────
# Test 6: Feature-gated — disabled silently exits 0
# ────────────────────────────────────────────
def test_feature_gate_disabled_exits_silently():
    repo = _init_repo("main")
    try:
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "_plan.md").write_text("# Important plan\n")

        proc = _run_hook(
            _make_payload(), repo,
            env={"OMG_GIT_WORKFLOW_ENABLED": "0"},
        )

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""
        # Branch should NOT change — still on main
        assert _current_branch(repo) == "main"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 7: Fallback to session-{timestamp} when no state files
# ────────────────────────────────────────────
def test_fallback_session_timestamp_when_no_state():
    repo = _init_repo("main")
    try:
        # No .omg/state at all — should fallback to session-{timestamp}
        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0
        branch = _current_branch(repo)
        assert branch.startswith("feature/session-"), f"Expected feature/session-*, got: {branch}"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 8: Branch name sanitization
# ────────────────────────────────────────────
def test_branch_name_sanitized():
    repo = _init_repo("main")
    try:
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        # Title with special chars, UPPERCASE, and length > 50
        (omg_state / "_plan.md").write_text(
            "# Fix: The LOGIN!! Bug @v2 (Critical) — Very Important Long Description That Exceeds Limit\n"
        )

        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0
        branch = _current_branch(repo)
        assert branch.startswith("feature/")
        name_part = branch[len("feature/"):]
        # lowercase
        assert name_part == name_part.lower(), f"Must be lowercase: {name_part}"
        # no special chars (only alphanumeric and hyphens)
        import re
        assert re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", name_part), \
            f"Invalid chars in branch name: {name_part}"
        # max 50 chars
        assert len(name_part) <= 50, f"Branch name too long ({len(name_part)}): {name_part}"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 9: Dry-run mode outputs action without executing
# ────────────────────────────────────────────
def test_dry_run_mode():
    repo = _init_repo("main")
    try:
        omg_state = repo / ".omg" / "state"
        omg_state.mkdir(parents=True)
        (omg_state / "_plan.md").write_text("# Add user profiles\n")

        proc = _run_hook(
            _make_payload(), repo,
            env={"OMG_GIT_WORKFLOW_DRY_RUN": "1"},
        )

        assert proc.returncode == 0
        # Dry-run should output what would happen to stderr
        assert "feature/" in proc.stderr, f"Dry-run should describe action in stderr: {proc.stderr}"
        assert "add-user-profiles" in proc.stderr
        # Branch should NOT actually change
        assert _current_branch(repo) == "main", "Dry-run must not create branch"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ────────────────────────────────────────────
# Test 10: No-op on arbitrary non-default branch
# ────────────────────────────────────────────
def test_noop_on_arbitrary_non_default_branch():
    repo = _init_repo("main")
    try:
        _git(repo, "checkout", "-b", "bugfix/something")

        proc = _run_hook(_make_payload(), repo)

        assert proc.returncode == 0
        assert _current_branch(repo) == "bugfix/something", "Should not switch from non-default branch"
    finally:
        shutil.rmtree(repo, ignore_errors=True)
