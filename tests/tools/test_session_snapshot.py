#!/usr/bin/env python3
"""
Tests for session_snapshot.py

Tests snapshot creation, listing, restoration, and deletion.
Tests branch creation, listing, switching, and forking.
Tests merge preview and merge execution with conflict detection.
Uses tmp_path pytest fixture for isolation.
"""

import json
import os
import sys
import tarfile
from pathlib import Path

import pytest

# Enable snapshot feature for tests
os.environ["OMG_SNAPSHOT_ENABLED"] = "true"
os.environ["OMG_BRANCHING_ENABLED"] = "true"
os.environ["OMG_MERGE_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from session_snapshot import (
    create_branch,
    create_snapshot,
    delete_snapshot,
    detect_merge_conflicts,
    fork_branch,
    get_status,
    list_branches,
    list_snapshots,
    merge_branch,
    merge_preview,
    preview_merge,
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
    (ledger_dir / "hook-errors.jsonl").write_text('{"ts": "2026-03-02T00:00:00", "hook": "test"}\n')

    return str(state_dir)


@pytest.fixture
def mock_state_with_sensitive(tmp_path):
    """Create a mock state directory with sensitive files."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create regular files
    (state_dir / "profile.yaml").write_text("name: test\n")

    # Create sensitive files that should be excluded
    (state_dir / "credentials.enc").write_text("encrypted_data_here")
    (state_dir / "credentials.meta").write_text('{"version": 1}')

    return str(state_dir)


# ─── Snapshot Tests ───────────────────────────────────────────────────


class TestCreateSnapshot:
    """Tests for create_snapshot function."""

    def test_create_snapshot_basic(self, mock_state_dir):
        """Test basic snapshot creation."""
        result = create_snapshot(state_dir=mock_state_dir)

        assert "id" in result
        assert "created_at" in result
        assert "files_count" in result
        assert "compressed_size" in result
        assert result["files_count"] > 0
        assert result["compressed_size"] > 0

    def test_create_snapshot_with_name(self, mock_state_dir):
        """Test snapshot creation with custom name."""
        result = create_snapshot(name="baseline", state_dir=mock_state_dir)

        assert "baseline" in result["id"]
        assert result["name"] == "baseline"

    def test_snapshot_file_created(self, mock_state_dir):
        """Test that snapshot tar.gz file is created."""
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")

        assert os.path.exists(tar_path)
        assert tarfile.is_tarfile(tar_path)

    def test_snapshot_metadata_created(self, mock_state_dir):
        """Test that snapshot metadata JSON is created."""
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        meta_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")

        assert os.path.exists(meta_path)
        with open(meta_path, "r") as f:
            metadata = json.load(f)
        assert metadata["id"] == snapshot_id

    def test_snapshot_excludes_snapshots_dir(self, mock_state_dir):
        """Test that snapshots directory is not included in snapshot."""
        # Create first snapshot
        result1 = create_snapshot(state_dir=mock_state_dir)

        # Create second snapshot
        result2 = create_snapshot(state_dir=mock_state_dir)

        # Extract second snapshot and verify it doesn't contain first snapshot
        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{result2['id']}.tar.gz")

        with tarfile.open(tar_path, "r:gz") as tar:
            names = tar.getnames()
            # Should not contain any files from snapshots directory
            assert not any("snapshots" in name for name in names)

    def test_snapshot_excludes_sensitive_files(self, mock_state_with_sensitive):
        """Test that sensitive files are excluded from snapshot."""
        result = create_snapshot(state_dir=mock_state_with_sensitive)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_with_sensitive, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")

        with tarfile.open(tar_path, "r:gz") as tar:
            names = tar.getnames()
            # Should not contain credentials files
            assert not any("credentials.enc" in name for name in names)
            assert not any("credentials.meta" in name for name in names)

    def test_snapshot_includes_regular_files(self, mock_state_dir):
        """Test that regular files are included in snapshot."""
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")

        with tarfile.open(tar_path, "r:gz") as tar:
            names = tar.getnames()
            # Should contain expected files
            assert any("profile.yaml" in name for name in names)
            assert any("working-memory.md" in name for name in names)

    def test_snapshot_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Test that snapshot returns skipped when feature flag is disabled."""
        monkeypatch.setenv("OMG_SNAPSHOT_ENABLED", "false")
        result = create_snapshot(state_dir=mock_state_dir)
        assert result.get("skipped") is True


class TestListSnapshots:
    """Tests for list_snapshots function."""

    def test_list_empty_snapshots(self, mock_state_dir):
        """Test listing when no snapshots exist."""
        snapshots = list_snapshots(state_dir=mock_state_dir)
        assert snapshots == []

    def test_list_single_snapshot(self, mock_state_dir):
        """Test listing with one snapshot."""
        create_snapshot(state_dir=mock_state_dir)
        snapshots = list_snapshots(state_dir=mock_state_dir)

        assert len(snapshots) == 1
        assert "id" in snapshots[0]
        assert "created_at" in snapshots[0]

    def test_list_multiple_snapshots(self, mock_state_dir):
        """Test listing with multiple snapshots."""
        create_snapshot(name="snap1", state_dir=mock_state_dir)
        create_snapshot(name="snap2", state_dir=mock_state_dir)
        create_snapshot(name="snap3", state_dir=mock_state_dir)

        snapshots = list_snapshots(state_dir=mock_state_dir)
        assert len(snapshots) == 3

    def test_list_sorted_by_created_at(self, mock_state_dir):
        """Test that snapshots are sorted by created_at descending."""
        import time

        snap1 = create_snapshot(name="first", state_dir=mock_state_dir)
        time.sleep(0.1)
        snap2 = create_snapshot(name="second", state_dir=mock_state_dir)
        time.sleep(0.1)
        snap3 = create_snapshot(name="third", state_dir=mock_state_dir)

        snapshots = list_snapshots(state_dir=mock_state_dir)

        # Should be in reverse order (newest first)
        assert snapshots[0]["name"] == "third"
        assert snapshots[1]["name"] == "second"
        assert snapshots[2]["name"] == "first"

    def test_list_nonexistent_snapshots_dir(self, tmp_path):
        """Test listing when snapshots directory doesn't exist."""
        state_dir = str(tmp_path / ".omg" / "state")
        snapshots = list_snapshots(state_dir=state_dir)
        assert snapshots == []


class TestRestoreSnapshot:
    """Tests for restore_snapshot function."""

    def test_restore_snapshot_success(self, mock_state_dir):
        """Test successful snapshot restoration."""
        # Create snapshot
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        # Modify a file to verify restoration
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        original_content = Path(profile_path).read_text()
        Path(profile_path).write_text("modified: true\n")

        # Restore snapshot
        success = restore_snapshot(snapshot_id, state_dir=mock_state_dir)

        assert success is True
        # Verify file was restored
        restored_content = Path(profile_path).read_text()
        assert restored_content == original_content

    def test_restore_nonexistent_snapshot(self, mock_state_dir):
        """Test restoration of non-existent snapshot."""
        success = restore_snapshot("nonexistent_id", state_dir=mock_state_dir)
        assert success is False

    def test_restore_creates_files(self, mock_state_dir):
        """Test that restore creates missing files."""
        # Create snapshot
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        # Delete a file
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        os.remove(profile_path)
        assert not os.path.exists(profile_path)

        # Restore snapshot
        restore_snapshot(snapshot_id, state_dir=mock_state_dir)

        # Verify file was restored
        assert os.path.exists(profile_path)

    def test_restore_recreates_directories(self, mock_state_dir):
        """Test that restore recreates directory structure."""
        # Create snapshot
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        # Delete ledger directory
        ledger_dir = os.path.join(mock_state_dir, "ledger")
        import shutil
        shutil.rmtree(ledger_dir)
        assert not os.path.exists(ledger_dir)

        # Restore snapshot
        restore_snapshot(snapshot_id, state_dir=mock_state_dir)

        # Verify directory was restored
        assert os.path.exists(ledger_dir)
        assert os.path.exists(os.path.join(ledger_dir, "hook-errors.jsonl"))


class TestDeleteSnapshot:
    """Tests for delete_snapshot function."""

    def test_delete_snapshot_success(self, mock_state_dir):
        """Test successful snapshot deletion."""
        # Create snapshot
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")
        meta_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")

        assert os.path.exists(tar_path)
        assert os.path.exists(meta_path)

        # Delete snapshot
        success = delete_snapshot(snapshot_id, state_dir=mock_state_dir)

        assert success is True
        assert not os.path.exists(tar_path)
        assert not os.path.exists(meta_path)

    def test_delete_nonexistent_snapshot(self, mock_state_dir):
        """Test deletion of non-existent snapshot."""
        success = delete_snapshot("nonexistent_id", state_dir=mock_state_dir)
        assert success is False

    def test_delete_removes_both_files(self, mock_state_dir):
        """Test that delete removes both tar and metadata files."""
        # Create snapshot
        result = create_snapshot(state_dir=mock_state_dir)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")
        meta_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")

        # Delete snapshot
        delete_snapshot(snapshot_id, state_dir=mock_state_dir)

        # Verify both files are deleted
        assert not os.path.exists(tar_path)
        assert not os.path.exists(meta_path)


class TestSnapshotIntegration:
    """Integration tests for snapshot workflow."""

    def test_create_list_restore_workflow(self, mock_state_dir):
        """Test complete workflow: create, list, restore."""
        # Create snapshots
        snap1 = create_snapshot(name="baseline", state_dir=mock_state_dir)
        snap2 = create_snapshot(name="modified", state_dir=mock_state_dir)

        # List snapshots
        snapshots = list_snapshots(state_dir=mock_state_dir)
        assert len(snapshots) == 2

        # Modify state
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        Path(profile_path).write_text("modified: true\n")

        # Restore first snapshot
        restore_snapshot(snap1["id"], state_dir=mock_state_dir)

        # Verify restoration
        content = Path(profile_path).read_text()
        assert "modified: true" not in content

    def test_create_delete_list_workflow(self, mock_state_dir):
        """Test workflow: create, delete, list."""
        # Create snapshots
        snap1 = create_snapshot(name="snap1", state_dir=mock_state_dir)
        snap2 = create_snapshot(name="snap2", state_dir=mock_state_dir)

        # List
        snapshots = list_snapshots(state_dir=mock_state_dir)
        assert len(snapshots) == 2

        # Delete first
        delete_snapshot(snap1["id"], state_dir=mock_state_dir)

        # List again
        snapshots = list_snapshots(state_dir=mock_state_dir)
        assert len(snapshots) == 1
        assert snapshots[0]["name"] == "snap2"

    def test_multiple_snapshots_independent(self, mock_state_dir):
        """Test that multiple snapshots are independent."""
        # Create first snapshot
        snap1 = create_snapshot(name="snap1", state_dir=mock_state_dir)

        # Modify state
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        Path(profile_path).write_text("modified_v1: true\n")

        # Create second snapshot
        snap2 = create_snapshot(name="snap2", state_dir=mock_state_dir)

        # Restore first snapshot
        restore_snapshot(snap1["id"], state_dir=mock_state_dir)
        content1 = Path(profile_path).read_text()

        # Restore second snapshot
        restore_snapshot(snap2["id"], state_dir=mock_state_dir)
        content2 = Path(profile_path).read_text()

        # Contents should be different
        assert content1 != content2
        assert "modified_v1" not in content1
        assert "modified_v1" in content2


class TestSnapshotMetadata:
    """Tests for snapshot metadata."""

    def test_metadata_contains_required_fields(self, mock_state_dir):
        """Test that metadata contains all required fields."""
        result = create_snapshot(name="test", state_dir=mock_state_dir)

        required_fields = ["id", "name", "created_at", "files_count", "compressed_size", "state_dir"]
        for field in required_fields:
            assert field in result

    def test_metadata_values_correct(self, mock_state_dir):
        """Test that metadata values are correct."""
        result = create_snapshot(name="test", state_dir=mock_state_dir)

        assert result["name"] == "test"
        assert result["files_count"] > 0
        assert result["compressed_size"] > 0
        assert result["state_dir"] == mock_state_dir
        assert "test" in result["id"]

    def test_metadata_persisted_correctly(self, mock_state_dir):
        """Test that metadata is persisted correctly."""
        result = create_snapshot(name="test", state_dir=mock_state_dir)
        snapshot_id = result["id"]

        snapshots_dir = os.path.join(mock_state_dir, "snapshots")
        meta_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")

        with open(meta_path, "r") as f:
            persisted = json.load(f)

        assert persisted["id"] == result["id"]
        assert persisted["name"] == result["name"]
        assert persisted["files_count"] == result["files_count"]


# ─── Branch Tests ─────────────────────────────────────────────────────


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
        """Test that branch metadata file is written."""
        create_branch("test-branch", state_dir=mock_state_dir)

        branch_path = os.path.join(mock_state_dir, "branches", "test-branch.json")
        assert os.path.exists(branch_path)

        with open(branch_path, "r") as f:
            meta = json.load(f)
        assert meta["name"] == "test-branch"
        assert meta["status"] == "active"

    def test_create_branch_updates_current_branch(self, mock_state_dir):
        """Test that current_branch.json is updated."""
        create_branch("my-branch", state_dir=mock_state_dir)

        current_path = os.path.join(mock_state_dir, "current_branch.json")
        assert os.path.exists(current_path)

        with open(current_path, "r") as f:
            current = json.load(f)
        assert current["name"] == "my-branch"

    def test_create_branch_from_snapshot(self, mock_state_dir):
        """Test branch creation from a specific snapshot."""
        # Create snapshot first
        snap = create_snapshot(name="base", state_dir=mock_state_dir)
        snapshot_id = snap["id"]

        result = create_branch("from-snap", from_snapshot_id=snapshot_id, state_dir=mock_state_dir)

        assert result["name"] == "from-snap"
        assert result["snapshot_id"] == snapshot_id

    def test_create_branch_from_nonexistent_snapshot(self, mock_state_dir):
        """Test branch creation from non-existent snapshot returns error."""
        result = create_branch("bad", from_snapshot_id="nonexistent", state_dir=mock_state_dir)
        assert "error" in result

    def test_create_branch_invalid_name_empty(self, mock_state_dir):
        """Test that empty branch name is rejected."""
        result = create_branch("", state_dir=mock_state_dir)
        assert "error" in result

    def test_create_branch_invalid_name_slash(self, mock_state_dir):
        """Test that branch name with slash is rejected."""
        result = create_branch("foo/bar", state_dir=mock_state_dir)
        assert "error" in result

    def test_create_branch_records_parent(self, mock_state_dir):
        """Test that parent branch is recorded when switching."""
        # Create parent branch
        create_branch("parent", state_dir=mock_state_dir)

        # Create child branch (parent is now current)
        result = create_branch("child", state_dir=mock_state_dir)
        assert result["parent_branch"] == "parent"

    def test_create_branch_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Test that branch returns skipped when feature flag is disabled."""
        monkeypatch.setenv("OMG_BRANCHING_ENABLED", "false")
        result = create_branch("test", state_dir=mock_state_dir)
        assert result.get("skipped") is True


class TestListBranches:
    """Tests for list_branches function."""

    def test_list_branches_empty(self, mock_state_dir):
        """Test listing when no branches exist."""
        branches = list_branches(state_dir=mock_state_dir)
        assert branches == []

    def test_list_branches_single(self, mock_state_dir):
        """Test listing with one branch."""
        create_branch("main", state_dir=mock_state_dir)
        branches = list_branches(state_dir=mock_state_dir)

        assert len(branches) == 1
        assert branches[0]["name"] == "main"

    def test_list_branches_multiple(self, mock_state_dir):
        """Test listing with multiple branches."""
        import time
        create_branch("main", state_dir=mock_state_dir)
        time.sleep(0.05)
        create_branch("dev", state_dir=mock_state_dir)
        time.sleep(0.05)
        create_branch("feature", state_dir=mock_state_dir)

        branches = list_branches(state_dir=mock_state_dir)
        assert len(branches) == 3

    def test_list_branches_sorted_newest_first(self, mock_state_dir):
        """Test that branches are sorted newest first."""
        import time
        create_branch("first", state_dir=mock_state_dir)
        time.sleep(0.05)
        create_branch("second", state_dir=mock_state_dir)
        time.sleep(0.05)
        create_branch("third", state_dir=mock_state_dir)

        branches = list_branches(state_dir=mock_state_dir)
        assert branches[0]["name"] == "third"
        assert branches[2]["name"] == "first"

    def test_list_branches_nonexistent_dir(self, tmp_path):
        """Test listing when branches dir doesn't exist."""
        state_dir = str(tmp_path / "nonexistent" / "state")
        branches = list_branches(state_dir=state_dir)
        assert branches == []


class TestSwitchBranch:
    """Tests for switch_branch function."""

    def test_switch_branch_success(self, mock_state_dir):
        """Test switching to an existing branch."""
        # Create two branches
        create_branch("main", state_dir=mock_state_dir)

        # Modify state
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        Path(profile_path).write_text("branch: dev\n")
        create_branch("dev", state_dir=mock_state_dir)

        # Switch back to main
        success = switch_branch("main", state_dir=mock_state_dir)
        assert success is True

        # current_branch should be updated
        current_path = os.path.join(mock_state_dir, "current_branch.json")
        with open(current_path, "r") as f:
            current = json.load(f)
        assert current["name"] == "main"

    def test_switch_branch_nonexistent(self, mock_state_dir):
        """Test switching to nonexistent branch returns False."""
        success = switch_branch("nonexistent", state_dir=mock_state_dir)
        assert success is False

    def test_switch_branch_restores_state(self, mock_state_dir):
        """Test that switching restores the branch's snapshot state."""
        # Create branch from initial state
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        original_content = Path(profile_path).read_text()
        create_branch("baseline", state_dir=mock_state_dir)

        # Modify state and create another branch
        Path(profile_path).write_text("changed: true\n")
        create_branch("modified", state_dir=mock_state_dir)

        # Switch back to baseline — should restore original content
        switch_branch("baseline", state_dir=mock_state_dir)
        restored = Path(profile_path).read_text()
        assert restored == original_content


# ─── Fork Tests ───────────────────────────────────────────────────────


class TestForkBranch:
    """Tests for fork_branch function."""

    def test_fork_branch_success(self, mock_state_dir):
        """Test forking from a named snapshot."""
        # Create a snapshot
        snap = create_snapshot(name="checkpoint", state_dir=mock_state_dir)

        # Fork from it
        result = fork_branch(from_snapshot_id=snap["id"], name="alt-path", state_dir=mock_state_dir)

        assert result["name"] == "alt-path"
        assert result["snapshot_id"] == snap["id"]
        assert result["status"] == "active"

    def test_fork_branch_missing_snapshot(self, mock_state_dir):
        """Test forking from a nonexistent snapshot returns error."""
        result = fork_branch(from_snapshot_id="nonexistent", name="bad-fork", state_dir=mock_state_dir)
        assert "error" in result

    def test_fork_branch_requires_snapshot(self, mock_state_dir):
        """Test that fork_branch requires a snapshot ID."""
        result = fork_branch(from_snapshot_id="", name="no-source", state_dir=mock_state_dir)
        assert "error" in result

    def test_fork_branch_requires_name(self, mock_state_dir):
        """Test that fork_branch requires a branch name."""
        snap = create_snapshot(name="checkpoint", state_dir=mock_state_dir)
        result = fork_branch(from_snapshot_id=snap["id"], name="", state_dir=mock_state_dir)
        assert "error" in result

    def test_fork_branch_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Test that fork returns skipped when branching flag disabled."""
        monkeypatch.setenv("OMG_BRANCHING_ENABLED", "false")
        result = fork_branch(from_snapshot_id="any", name="test", state_dir=mock_state_dir)
        assert result.get("skipped") is True

    def test_fork_creates_branch_metadata(self, mock_state_dir):
        """Test that fork creates proper branch metadata file."""
        snap = create_snapshot(name="base", state_dir=mock_state_dir)
        fork_branch(from_snapshot_id=snap["id"], name="forked", state_dir=mock_state_dir)

        branch_path = os.path.join(mock_state_dir, "branches", "forked.json")
        assert os.path.exists(branch_path)

        with open(branch_path, "r") as f:
            meta = json.load(f)
        assert meta["name"] == "forked"
        assert meta["snapshot_id"] == snap["id"]


# ─── Merge Conflict Detection Tests ──────────────────────────────────


class TestDetectMergeConflicts:
    """Tests for detect_merge_conflicts function."""

    def test_no_conflicts_identical(self):
        """Test no conflicts when states are identical."""
        state = {"name": "main", "status": "active", "snapshot_id": "abc"}
        conflicts = detect_merge_conflicts(state, state.copy())
        assert conflicts == []

    def test_no_conflicts_disjoint_keys(self):
        """Test no conflicts when states have disjoint keys."""
        source = {"extra_key": "value"}
        target = {"other_key": "other"}
        conflicts = detect_merge_conflicts(source, target)
        assert conflicts == []

    def test_conflict_detected(self):
        """Test that conflicting values are detected."""
        source = {"snapshot_id": "snap-A", "name": "dev"}
        target = {"snapshot_id": "snap-B", "name": "dev"}
        conflicts = detect_merge_conflicts(source, target)

        assert len(conflicts) == 1
        assert conflicts[0]["key"] == "snapshot_id"
        assert conflicts[0]["source_value"] == "snap-A"
        assert conflicts[0]["target_value"] == "snap-B"
        assert conflicts[0]["conflict_type"] == "value_conflict"

    def test_multiple_conflicts(self):
        """Test multiple conflicting keys."""
        source = {"a": 1, "b": 2, "c": 3}
        target = {"a": 10, "b": 20, "c": 3}
        conflicts = detect_merge_conflicts(source, target)

        assert len(conflicts) == 2
        conflict_keys = [c["key"] for c in conflicts]
        assert "a" in conflict_keys
        assert "b" in conflict_keys

    def test_same_values_no_conflict(self):
        """Test that same values on shared keys produce no conflict."""
        source = {"shared": "same", "only_source": 1}
        target = {"shared": "same", "only_target": 2}
        conflicts = detect_merge_conflicts(source, target)
        assert conflicts == []


# ─── Merge Preview Tests ─────────────────────────────────────────────


class TestMergePreview:
    """Tests for merge_preview / preview_merge function."""

    def test_merge_preview_alias(self):
        """Test that merge_preview is the same function as preview_merge."""
        assert merge_preview is preview_merge

    def test_preview_no_conflicts(self, mock_state_dir):
        """Test preview with no conflicts."""
        # Create two branches with non-conflicting metadata
        create_branch("main", state_dir=mock_state_dir)

        import time
        time.sleep(0.05)
        create_branch("feature", state_dir=mock_state_dir)

        result = merge_preview("feature", target_branch="main", state_dir=mock_state_dir)

        assert result.get("preview") is True
        assert result["source"] == "feature"
        assert result["target"] == "main"
        assert isinstance(result["conflicts"], list)

    def test_preview_with_conflicts(self, mock_state_dir):
        """Test preview detects conflicts between branches."""
        # Create two branches — they'll have different snapshot_ids and created_at
        create_branch("main", state_dir=mock_state_dir)

        import time
        time.sleep(0.05)
        create_branch("dev", state_dir=mock_state_dir)

        result = merge_preview("dev", target_branch="main", state_dir=mock_state_dir)

        assert result.get("preview") is True
        # Both branches will have different snapshot_id and created_at → conflicts
        assert isinstance(result["conflicts"], list)

    def test_preview_source_not_found(self, mock_state_dir):
        """Test preview with missing source branch."""
        create_branch("main", state_dir=mock_state_dir)
        result = merge_preview("nonexistent", target_branch="main", state_dir=mock_state_dir)
        assert "error" in result

    def test_preview_target_not_found(self, mock_state_dir):
        """Test preview with missing target branch."""
        create_branch("dev", state_dir=mock_state_dir)
        result = merge_preview("dev", target_branch="nonexistent", state_dir=mock_state_dir)
        assert "error" in result

    def test_preview_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Test preview returns skipped when merge flag disabled."""
        monkeypatch.setenv("OMG_MERGE_ENABLED", "false")
        result = merge_preview("a", target_branch="b", state_dir=mock_state_dir)
        assert result.get("skipped") is True


# ─── Merge Branch Tests ──────────────────────────────────────────────


class TestMergeBranch:
    """Tests for merge_branch function."""

    def test_merge_no_conflicts(self, mock_state_dir):
        """Test merge succeeds when branches have identical shared keys."""
        # Create a branch, manually write non-conflicting metadata
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        source_meta = {"name": "feature", "status": "active", "extra": "new-value"}
        target_meta = {"name": "main", "status": "active"}

        with open(os.path.join(branches_dir, "feature.json"), "w") as f:
            json.dump(source_meta, f)
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump(target_meta, f)

        result = merge_branch("feature", target_branch="main", state_dir=mock_state_dir)

        assert result["merged"] is True
        assert result["conflicts"] == []

    def test_merge_aborts_on_conflicts(self, mock_state_dir):
        """Test merge is aborted when conflicts exist."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        source_meta = {"name": "feature", "status": "active", "priority": "high"}
        target_meta = {"name": "main", "status": "active", "priority": "low"}

        with open(os.path.join(branches_dir, "feature.json"), "w") as f:
            json.dump(source_meta, f)
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump(target_meta, f)

        result = merge_branch("feature", target_branch="main", state_dir=mock_state_dir)

        assert result["merged"] is False
        assert len(result["conflicts"]) > 0

    def test_merge_marks_source_as_merged(self, mock_state_dir):
        """Test that source branch is marked as merged after successful merge."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        source_meta = {"name": "feature", "status": "active", "extra": "data"}
        target_meta = {"name": "main", "status": "active"}

        with open(os.path.join(branches_dir, "feature.json"), "w") as f:
            json.dump(source_meta, f)
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump(target_meta, f)

        merge_branch("feature", target_branch="main", state_dir=mock_state_dir)

        # Verify source is marked merged
        with open(os.path.join(branches_dir, "feature.json"), "r") as f:
            source_after = json.load(f)
        assert source_after["status"] == "merged"
        assert source_after["merged_into"] == "main"

    def test_merge_updates_current_branch(self, mock_state_dir):
        """Test that current_branch is updated to target after merge."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        source_meta = {"name": "feature", "status": "active", "extra": "data"}
        target_meta = {"name": "main", "status": "active"}

        with open(os.path.join(branches_dir, "feature.json"), "w") as f:
            json.dump(source_meta, f)
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump(target_meta, f)

        merge_branch("feature", target_branch="main", state_dir=mock_state_dir)

        current_path = os.path.join(mock_state_dir, "current_branch.json")
        with open(current_path, "r") as f:
            current = json.load(f)
        assert current["name"] == "main"

    def test_merge_missing_source(self, mock_state_dir):
        """Test merge with missing source branch."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        target_meta = {"name": "main", "status": "active"}
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump(target_meta, f)

        result = merge_branch("nonexistent", target_branch="main", state_dir=mock_state_dir)
        assert "error" in result

    def test_merge_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Test merge returns skipped when feature flag disabled."""
        monkeypatch.setenv("OMG_MERGE_ENABLED", "false")
        result = merge_branch("a", target_branch="b", state_dir=mock_state_dir)
        assert result.get("skipped") is True


# ─── Full Lifecycle Integration Tests ─────────────────────────────────


class TestBranchLifecycle:
    """Integration tests for the full branch lifecycle."""

    def test_branch_switch_lifecycle(self, mock_state_dir):
        """Test: create branch → modify → create another → switch back."""
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        original = Path(profile_path).read_text()

        # Create baseline branch
        create_branch("baseline", state_dir=mock_state_dir)

        # Modify and create experiment
        Path(profile_path).write_text("experiment: true\n")
        create_branch("experiment", state_dir=mock_state_dir)

        # Switch back to baseline
        switch_branch("baseline", state_dir=mock_state_dir)
        assert Path(profile_path).read_text() == original

    def test_fork_and_switch_lifecycle(self, mock_state_dir):
        """Test: snapshot → fork → switch back."""
        profile_path = os.path.join(mock_state_dir, "profile.yaml")
        original = Path(profile_path).read_text()

        # Create a snapshot checkpoint
        snap = create_snapshot(name="v1", state_dir=mock_state_dir)

        # Modify state
        Path(profile_path).write_text("v2: true\n")

        # Fork from the v1 checkpoint
        fork_result = fork_branch(from_snapshot_id=snap["id"], name="alt", state_dir=mock_state_dir)
        assert fork_result["name"] == "alt"

        # After fork, state should be restored to v1
        assert Path(profile_path).read_text() == original

    def test_merge_lifecycle(self, mock_state_dir):
        """Test: create branches → preview → merge."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        # Set up non-conflicting branches
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump({"name": "main", "status": "active"}, f)
        with open(os.path.join(branches_dir, "feature.json"), "w") as f:
            json.dump({"name": "feature", "status": "active", "feature_data": "new"}, f)

        # Preview
        preview = merge_preview("feature", target_branch="main", state_dir=mock_state_dir)
        assert preview["preview"] is True
        assert preview["conflicts"] == []

        # Merge
        result = merge_branch("feature", target_branch="main", state_dir=mock_state_dir)
        assert result["merged"] is True

        # Verify target has merged data
        with open(os.path.join(branches_dir, "main.json"), "r") as f:
            merged = json.load(f)
        assert merged["feature_data"] == "new"
        assert merged["name"] == "main"  # target name preserved


# ─── CLI Tests ────────────────────────────────────────────────────────


class TestCLI:
    """Tests for CLI entry point."""

    def test_help_exits_zero(self):
        """Test that --help exits with code 0."""
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(tools_dir, "session_snapshot.py"), "--help"],
            capture_output=True, text=True
        )
        assert result.returncode == 0

    def test_no_args_exits_nonzero(self):
        """Test that no arguments exits with non-zero."""
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(tools_dir, "session_snapshot.py")],
            capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_import_works(self):
        """Test that module can be imported."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", "from tools import session_snapshot; print('ok')"],
            capture_output=True, text=True,
            cwd=os.path.join(tools_dir, ".."),
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

class TestStatus:
    """Tests for get_status function and --status CLI."""

    def test_get_status_basic(self, mock_state_dir):
        """Test get_status returns current branch and snapshot count."""
        # Initially no branch, no snapshots
        status = get_status(state_dir=mock_state_dir)
        assert status["current_branch"] is None
        assert status["snapshot_count"] == 0

        # Create a snapshot
        create_snapshot(state_dir=mock_state_dir)
        status = get_status(state_dir=mock_state_dir)
        assert status["snapshot_count"] == 1

        # Create a branch
        create_branch("test-branch", state_dir=mock_state_dir)
        status = get_status(state_dir=mock_state_dir)
        assert status["current_branch"] == "test-branch"
        # create_branch also creates a snapshot
        assert status["snapshot_count"] == 2

    def test_cli_status(self, mock_state_dir):
        """Test --status CLI command."""
        import subprocess
        # Create a branch and snapshot
        create_branch("cli-branch", state_dir=mock_state_dir)
        
        # We need to set the environment variable for the subprocess
        env = os.environ.copy()
        env["OMG_SNAPSHOT_ENABLED"] = "true"
        env["OMG_BRANCHING_ENABLED"] = "true"
        env["OMG_STATE_DIR"] = mock_state_dir
        
        result = subprocess.run(
            [sys.executable, os.path.join(tools_dir, "session_snapshot.py"), "status"],
            capture_output=True, text=True, env=env
        )
        assert result.returncode == 0
        status_data = json.loads(result.stdout)
        assert status_data["current_branch"] == "cli-branch"
        assert status_data["snapshot_count"] >= 1

    def test_cli_help_exits_zero(self):
        """Test that --help exits with 0."""
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(tools_dir, "session_snapshot.py"), "--help"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "status" in result.stdout
