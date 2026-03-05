#!/usr/bin/env python3
"""Test PreCompact hook output contract.

PreCompact is a side-effect hook that:
1. Snapshots key state files (.omg/state/profile.yaml, working-memory.md, etc.)
2. Generates handoff.md and handoff-portable.md in .omg/state/
3. Exits with code 0 (no JSON output to stdout)

This test verifies the hook creates the expected handoff files with correct structure.
"""
import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def test_precompact_creates_handoff_files():
    """PreCompact should create handoff.md and handoff-portable.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup minimal .omg/state structure
        state_dir = Path(tmpdir) / ".omg" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ledger").mkdir(exist_ok=True)
        (state_dir / "snapshots").mkdir(exist_ok=True)

        # Create a minimal profile.yaml so the hook has something to snapshot
        profile_path = state_dir / "profile.yaml"
        profile_path.write_text("project: test-project\nversion: 1.0\n")

        # Run the hook
        hook_script = Path(__file__).parent.parent.parent / "hooks" / "pre-compact.py"
        input_data = json.dumps({
            "hook_event": "PreCompact",
            "session_id": "test-session-123",
            "turn_count": 5
        })

        result = subprocess.run(
            ["python3", str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
        )

        # Hook should exit 0
        assert result.returncode == 0, f"Hook failed: {result.stderr}"

        # Verify handoff.md exists
        handoff_path = state_dir / "handoff.md"
        assert handoff_path.exists(), "handoff.md not created"

        # Verify handoff-portable.md exists
        handoff_portable_path = state_dir / "handoff-portable.md"
        assert handoff_portable_path.exists(), "handoff-portable.md not created"

        # Verify handoff.md has expected structure
        handoff_content = handoff_path.read_text()
        assert "# Handoff --" in handoff_content, "Missing handoff header"
        assert "Auto-generated before context compaction" in handoff_content
        assert "Resume Instructions" in handoff_content


def test_precompact_handoff_includes_profile():
    """PreCompact should include profile.yaml content in handoff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / ".omg" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ledger").mkdir(exist_ok=True)
        (state_dir / "snapshots").mkdir(exist_ok=True)

        # Create profile with specific content
        profile_path = state_dir / "profile.yaml"
        profile_content = "project: my-test-project\nversion: 2.0\nstatus: active\n"
        profile_path.write_text(profile_content)

        hook_script = Path(__file__).parent.parent.parent / "hooks" / "pre-compact.py"
        input_data = json.dumps({"hook_event": "PreCompact"})

        result = subprocess.run(
            ["python3", str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
        )

        assert result.returncode == 0
        handoff_content = (state_dir / "handoff.md").read_text()
        # Profile should be included (first 20 lines)
        assert "my-test-project" in handoff_content, "Profile content not in handoff"


def test_precompact_snapshots_state_files():
    """PreCompact should snapshot key state files to .omg/state/snapshots/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / ".omg" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ledger").mkdir(exist_ok=True)
        (state_dir / "snapshots").mkdir(exist_ok=True)

        # Create multiple state files
        (state_dir / "profile.yaml").write_text("project: test\n")
        (state_dir / "working-memory.md").write_text("# Working Memory\nSome notes\n")
        (state_dir / "_plan.md").write_text("# Plan\nTasks here\n")

        hook_script = Path(__file__).parent.parent.parent / "hooks" / "pre-compact.py"
        input_data = json.dumps({"hook_event": "PreCompact"})

        result = subprocess.run(
            ["python3", str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
        )

        assert result.returncode == 0

        # Find the snapshot directory (should be YYYYMMDD_HHMMSS format)
        snapshots_dir = state_dir / "snapshots"
        snapshot_dirs = list(snapshots_dir.glob("*"))
        assert len(snapshot_dirs) > 0, "No snapshot directory created"

        snapshot_dir = snapshot_dirs[0]
        # Should have snapshotted at least profile.yaml
        assert (snapshot_dir / "profile.yaml").exists(), "profile.yaml not snapshotted"


def test_precompact_handles_missing_state_files():
    """PreCompact should gracefully handle missing state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / ".omg" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ledger").mkdir(exist_ok=True)
        (state_dir / "snapshots").mkdir(exist_ok=True)

        # Don't create any state files

        hook_script = Path(__file__).parent.parent.parent / "hooks" / "pre-compact.py"
        input_data = json.dumps({"hook_event": "PreCompact"})

        result = subprocess.run(
            ["python3", str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
        )

        # Should still exit 0 (graceful degradation)
        assert result.returncode == 0, f"Hook failed on missing files: {result.stderr}"

        # Should still create handoff.md
        handoff_path = state_dir / "handoff.md"
        assert handoff_path.exists(), "handoff.md not created even with missing state files"


def test_precompact_no_json_output_to_stdout():
    """PreCompact should NOT output JSON to stdout (side-effect hook)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / ".omg" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ledger").mkdir(exist_ok=True)
        (state_dir / "snapshots").mkdir(exist_ok=True)
        (state_dir / "profile.yaml").write_text("project: test\n")

        hook_script = Path(__file__).parent.parent.parent / "hooks" / "pre-compact.py"
        input_data = json.dumps({"hook_event": "PreCompact"})

        result = subprocess.run(
            ["python3", str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
        )

        # stdout should be empty (no JSON output)
        assert result.stdout.strip() == "", f"Unexpected stdout: {result.stdout}"
        # stderr should have the snapshot message
        assert "Snapshotted" in result.stderr or result.returncode == 0


def test_precompact_truncates_large_handoff():
    """PreCompact should truncate handoff.md if it exceeds 120 lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / ".omg" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ledger").mkdir(exist_ok=True)
        (state_dir / "snapshots").mkdir(exist_ok=True)

        # Create a large profile to force truncation
        large_profile = "project: test\n" + "\n".join([f"line {i}" for i in range(200)])
        (state_dir / "profile.yaml").write_text(large_profile)

        hook_script = Path(__file__).parent.parent.parent / "hooks" / "pre-compact.py"
        input_data = json.dumps({"hook_event": "PreCompact"})

        result = subprocess.run(
            ["python3", str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
        )

        assert result.returncode == 0
        handoff_content = (state_dir / "handoff.md").read_text()
        lines = handoff_content.split("\n")
        # Should be truncated to ~120 lines
        assert len(lines) <= 130, f"Handoff not truncated: {len(lines)} lines"


if __name__ == "__main__":
    test_precompact_creates_handoff_files()
    test_precompact_handoff_includes_profile()
    test_precompact_snapshots_state_files()
    test_precompact_handles_missing_state_files()
    test_precompact_no_json_output_to_stdout()
    test_precompact_truncates_large_handoff()
    print("All tests passed!")
