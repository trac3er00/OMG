#!/usr/bin/env python3
"""
Tests for session_snapshot.py branch/fork functionality.

Tests branch creation, listing, switching, and feature flag gating.
Uses tmp_path pytest fixture for isolation.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

# Enable both snapshot and branching features for tests
os.environ["OMG_SNAPSHOT_ENABLED"] = "true"
os.environ["OMG_BRANCHING_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from session_snapshot import (
    create_branch,
    create_snapshot,
    list_branches,
    list_snapshots,
    restore_snapshot,
    switch_branch,
)


@pytest.fixture
def mock_state_dir(tmp_path):
    """Create a mock .omg/state directory with test files."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create some test files
    (state_dir / "profile.yaml").write_text("name: test\nversion: 1.0\n")
    (state_dir / "working-memory.md").write_text("# Working Memory\n\nTest content\n")
    (state_dir / "handoff.md").write_text("# Handoff\n\nTest handoff\n")

    # Create ledger subdirectory with files
    ledger_dir = state_dir / "ledger"
    ledger_dir.mkdir(exist_ok=True)
    (ledger_dir / "hook-errors.jsonl").write_text(
        '{"ts": "2026-03-02T00:00:00", "hook": "test"}\n'
    )

    return str(state_dir)


class TestCreateBranch:
    """Tests for create_branch function."""

    def test_create_branch_basic(self, mock_state_dir):
        """Test basic branch creation from current state."""
        result = create_branch("experiment", state_dir=mock_state_dir)

        assert result["name"] == "experiment"
        assert "snapshot_id" in result
        assert "created_at" in result
        assert result["status"] == "active"

    def test_create_branch_writes_metadata_file(self, mock_state_dir):
        """Test that branch metadata is written to branches directory."""
        create_branch("my-branch", state_dir=mock_state_dir)

        branch_path = os.path.join(mock_state_dir, "branches", "my-branch.json")
        assert os.path.exists(branch_path)

        with open(branch_path, "r") as f:
            metadata = json.load(f)
        assert metadata["name"] == "my-branch"
        assert metadata["status"] == "active"

    def test_create_branch_creates_snapshot(self, mock_state_dir):
        """Test that branch creation auto-creates a snapshot."""
        result = create_branch("test-snap", state_dir=mock_state_dir)
        snapshot_id = result["snapshot_id"]

        # Verify snapshot tar.gz exists
        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")
        assert os.path.exists(tar_path)

    def test_create_branch_from_snapshot(self, mock_state_dir):
        """Test creating branch from an existing snapshot."""
        # Create initial snapshot
        snap = create_snapshot(name="baseline", state_dir=mock_state_dir)
        snap_id = snap["id"]

        # Modify state
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        Path(profile_path).write_text("modified: true\n")

        # Create branch from old snapshot
        result = create_branch(
            "from-baseline", from_snapshot_id=snap_id, state_dir=mock_state_dir
        )

        assert result["name"] == "from-baseline"
        assert result["snapshot_id"] == snap_id

        # Verify state was restored from snapshot
        content = Path(profile_path).read_text()
        assert "modified" not in content

    def test_create_branch_from_nonexistent_snapshot(self, mock_state_dir):
        """Test creating branch from non-existent snapshot returns error."""
        result = create_branch(
            "bad-ref", from_snapshot_id="nonexistent_id", state_dir=mock_state_dir
        )

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_create_branch_invalid_name_empty(self, mock_state_dir):
        """Test that empty branch name returns error."""
        result = create_branch("", state_dir=mock_state_dir)
        assert "error" in result

    def test_create_branch_invalid_name_slash(self, mock_state_dir):
        """Test that branch name with slash returns error."""
        result = create_branch("feature/auth", state_dir=mock_state_dir)
        assert "error" in result

    def test_create_branch_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Test that branch creation returns skipped when flag is disabled."""
        monkeypatch.setenv("OMG_BRANCHING_ENABLED", "false")
        result = create_branch("test", state_dir=mock_state_dir)
        assert result.get("skipped") is True

    def test_create_branch_tracks_parent(self, mock_state_dir):
        """Test that parent_branch is tracked correctly."""
        # Create first branch (no parent)
        result1 = create_branch("main-branch", state_dir=mock_state_dir)
        assert result1["parent_branch"] is None

        # Create second branch (parent should be main-branch)
        result2 = create_branch("child-branch", state_dir=mock_state_dir)
        assert result2["parent_branch"] == "main-branch"

    def test_create_branch_updates_current_branch(self, mock_state_dir):
        """Test that creating a branch updates current_branch.json."""
        create_branch("active-branch", state_dir=mock_state_dir)

        current_path = os.path.join(mock_state_dir, "current_branch.json")
        assert os.path.exists(current_path)

        with open(current_path, "r") as f:
            current = json.load(f)
        assert current["name"] == "active-branch"
        assert "switched_at" in current

    def test_create_branch_metadata_fields(self, mock_state_dir):
        """Test that branch metadata contains all required fields."""
        result = create_branch("full-meta", state_dir=mock_state_dir)

        required_fields = [
            "name",
            "snapshot_id",
            "created_at",
            "parent_branch",
            "status",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"


class TestListBranches:
    """Tests for list_branches function."""

    def test_list_empty_branches(self, mock_state_dir):
        """Test listing when no branches exist."""
        branches = list_branches(state_dir=mock_state_dir)
        assert branches == []

    def test_list_single_branch(self, mock_state_dir):
        """Test listing with one branch."""
        create_branch("solo", state_dir=mock_state_dir)
        branches = list_branches(state_dir=mock_state_dir)

        assert len(branches) == 1
        assert branches[0]["name"] == "solo"

    def test_list_multiple_branches(self, mock_state_dir):
        """Test listing with multiple branches."""
        create_branch("branch-a", state_dir=mock_state_dir)
        create_branch("branch-b", state_dir=mock_state_dir)
        create_branch("branch-c", state_dir=mock_state_dir)

        branches = list_branches(state_dir=mock_state_dir)
        assert len(branches) == 3

    def test_list_sorted_by_created_at(self, mock_state_dir):
        """Test that branches are sorted by created_at descending."""
        create_branch("first", state_dir=mock_state_dir)
        time.sleep(0.05)
        create_branch("second", state_dir=mock_state_dir)
        time.sleep(0.05)
        create_branch("third", state_dir=mock_state_dir)

        branches = list_branches(state_dir=mock_state_dir)

        # Should be newest first
        assert branches[0]["name"] == "third"
        assert branches[1]["name"] == "second"
        assert branches[2]["name"] == "first"

    def test_list_nonexistent_branches_dir(self, tmp_path):
        """Test listing when branches directory doesn't exist."""
        state_dir = str(tmp_path / ".omg" / "state")
        branches = list_branches(state_dir=state_dir)
        assert branches == []

    def test_list_skips_invalid_json(self, mock_state_dir):
        """Test that invalid JSON files are skipped gracefully."""
        # Create branches dir with bad file
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)
        bad_path = os.path.join(branches_dir, "bad.json")
        with open(bad_path, "w") as f:
            f.write("not valid json{{{")

        branches = list_branches(state_dir=mock_state_dir)
        assert branches == []


class TestSwitchBranch:
    """Tests for switch_branch function."""

    def test_switch_branch_success(self, mock_state_dir):
        """Test successful branch switch."""
        # Create branch
        create_branch("target", state_dir=mock_state_dir)

        # Modify state
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        original = Path(profile_path).read_text()
        Path(profile_path).write_text("switched: true\n")

        # Switch back to branch
        success = switch_branch("target", state_dir=mock_state_dir)
        assert success is True

        # State should be restored
        restored = Path(profile_path).read_text()
        assert restored == original

    def test_switch_nonexistent_branch(self, mock_state_dir):
        """Test switching to non-existent branch returns False."""
        success = switch_branch("ghost-branch", state_dir=mock_state_dir)
        assert success is False

    def test_switch_updates_current_branch(self, mock_state_dir):
        """Test that switch updates current_branch.json."""
        create_branch("branch-a", state_dir=mock_state_dir)
        create_branch("branch-b", state_dir=mock_state_dir)

        switch_branch("branch-a", state_dir=mock_state_dir)

        current_path = os.path.join(mock_state_dir, "current_branch.json")
        with open(current_path, "r") as f:
            current = json.load(f)
        assert current["name"] == "branch-a"

    def test_switch_with_invalid_metadata(self, mock_state_dir):
        """Test switching when branch metadata is corrupt returns False."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)
        bad_path = os.path.join(branches_dir, "corrupt.json")
        with open(bad_path, "w") as f:
            f.write("{{invalid json}}")

        success = switch_branch("corrupt", state_dir=mock_state_dir)
        assert success is False

    def test_switch_with_missing_snapshot_id(self, mock_state_dir):
        """Test switching when branch metadata has no snapshot_id."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)
        meta_path = os.path.join(branches_dir, "no-snap.json")
        with open(meta_path, "w") as f:
            json.dump({"name": "no-snap", "status": "active"}, f)

        success = switch_branch("no-snap", state_dir=mock_state_dir)
        assert success is False


class TestBranchIntegration:
    """Integration tests for branch/fork workflow."""

    def test_create_switch_workflow(self, mock_state_dir):
        """Test full create-modify-switch workflow."""
        profile_path = os.path.join(mock_state_dir, "profile.yaml")

        # Create baseline branch
        create_branch("baseline", state_dir=mock_state_dir)
        baseline_content = Path(profile_path).read_text()

        # Modify and create experiment branch
        Path(profile_path).write_text("experiment: true\n")
        create_branch("experiment", state_dir=mock_state_dir)

        # Switch back to baseline
        switch_branch("baseline", state_dir=mock_state_dir)
        assert Path(profile_path).read_text() == baseline_content

        # Switch to experiment
        switch_branch("experiment", state_dir=mock_state_dir)
        assert "experiment: true" in Path(profile_path).read_text()

    def test_fork_from_snapshot_workflow(self, mock_state_dir):
        """Test fork workflow: snapshot -> modify -> fork back."""
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        original = Path(profile_path).read_text()

        # Create checkpoint snapshot
        snap = create_snapshot(name="checkpoint", state_dir=mock_state_dir)

        # Modify state significantly
        Path(profile_path).write_text("v2: heavy changes\n")

        # Fork from checkpoint
        fork = create_branch(
            "fork-v1", from_snapshot_id=snap["id"], state_dir=mock_state_dir
        )
        assert fork["snapshot_id"] == snap["id"]

        # State should be at checkpoint, not v2
        assert Path(profile_path).read_text() == original

    def test_branch_does_not_break_snapshots(self, mock_state_dir):
        """Test that branching doesn't interfere with snapshot operations."""
        # Create branch
        create_branch("safe", state_dir=mock_state_dir)

        # Snapshot operations should still work
        snap = create_snapshot(name="after-branch", state_dir=mock_state_dir)
        assert "id" in snap
        assert snap.get("skipped") is not True

        snapshots = list_snapshots(state_dir=mock_state_dir)
        # At least 2: one from branch creation, one explicit
        assert len(snapshots) >= 2

    def test_multiple_branches_independent(self, mock_state_dir):
        """Test that multiple branches maintain independent state."""
        profile_path = os.path.join(mock_state_dir, "profile.yaml")

        # Create branch A with original state
        create_branch("branch-a", state_dir=mock_state_dir)

        # Modify and create branch B
        Path(profile_path).write_text("branch-b-state\n")
        create_branch("branch-b", state_dir=mock_state_dir)

        # Switch to A - should have original state
        switch_branch("branch-a", state_dir=mock_state_dir)
        content_a = Path(profile_path).read_text()

        # Switch to B - should have modified state
        switch_branch("branch-b", state_dir=mock_state_dir)
        content_b = Path(profile_path).read_text()

        assert content_a != content_b
        assert "branch-b-state" not in content_a
        assert "branch-b-state" in content_b
