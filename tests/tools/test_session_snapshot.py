#!/usr/bin/env python3
"""
Tests for session_snapshot.py

Tests snapshot creation, listing, restoration, and deletion.
Uses tmp_path pytest fixture for isolation.
"""

import json
import os
import sys
import tarfile
from pathlib import Path

import pytest

# Enable snapshot feature for tests
os.environ["OAL_SNAPSHOT_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from session_snapshot import (
    create_snapshot,
    delete_snapshot,
    list_snapshots,
    restore_snapshot,
)


@pytest.fixture
def mock_state_dir(tmp_path):
    """Create a mock .oal/state directory with test files."""
    state_dir = tmp_path / ".oal" / "state"
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
    state_dir = tmp_path / ".oal" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create regular files
    (state_dir / "profile.yaml").write_text("name: test\n")

    # Create sensitive files that should be excluded
    (state_dir / "credentials.enc").write_text("encrypted_data_here")
    (state_dir / "credentials.meta").write_text('{"version": 1}')

    return str(state_dir)


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
        monkeypatch.setenv("OAL_SNAPSHOT_ENABLED", "false")
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
        state_dir = str(tmp_path / ".oal" / "state")
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
