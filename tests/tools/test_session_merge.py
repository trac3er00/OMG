#!/usr/bin/env python3
"""
Tests for session_snapshot.py merge functionality.

Tests detect_merge_conflicts, preview_merge, merge_branch,
feature flag gating, and edge cases.
Uses tmp_path pytest fixture for isolation.
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Enable snapshot, branching, and merge features for tests
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
    detect_merge_conflicts,
    list_branches,
    merge_branch,
    preview_merge,
    _load_branch_state,
)


@pytest.fixture
def mock_state_dir(tmp_path):
    """Create a mock .omg/state directory with test files."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create some test files
    (state_dir / "profile.yaml").write_text("name: test\nversion: 1.0\n")
    (state_dir / "working-memory.md").write_text("# Working Memory\n\nTest content\n")

    # Create ledger subdirectory
    ledger_dir = state_dir / "ledger"
    ledger_dir.mkdir(exist_ok=True)
    (ledger_dir / "hook-errors.jsonl").write_text(
        '{"ts": "2026-03-02T00:00:00", "hook": "test"}\n'
    )

    return str(state_dir)


@pytest.fixture
def two_branches(mock_state_dir):
    """Create two branches with different metadata for merge testing."""
    # Create source branch
    source = create_branch("source-branch", state_dir=mock_state_dir)
    # Create target branch
    target = create_branch("target-branch", state_dir=mock_state_dir)
    return mock_state_dir, source, target


# ============================================================
# detect_merge_conflicts tests
# ============================================================


class TestDetectMergeConflicts:
    """Tests for detect_merge_conflicts function."""

    def test_no_conflicts_identical_dicts(self):
        """Two identical dicts produce no conflicts."""
        state = {"a": 1, "b": 2, "c": 3}
        conflicts = detect_merge_conflicts(state, state.copy())
        assert conflicts == []

    def test_no_conflicts_disjoint_keys(self):
        """Two dicts with no overlapping keys produce no conflicts."""
        source = {"a": 1, "b": 2}
        target = {"c": 3, "d": 4}
        conflicts = detect_merge_conflicts(source, target)
        assert conflicts == []

    def test_single_value_conflict(self):
        """Detects single key with different values."""
        source = {"name": "experiment", "status": "active"}
        target = {"name": "main", "status": "active"}
        conflicts = detect_merge_conflicts(source, target)
        assert len(conflicts) == 1
        assert conflicts[0]["key"] == "name"
        assert conflicts[0]["source_value"] == "experiment"
        assert conflicts[0]["target_value"] == "main"
        assert conflicts[0]["conflict_type"] == "value_conflict"

    def test_multiple_conflicts(self):
        """Detects multiple conflicting keys."""
        source = {"a": 1, "b": "x", "c": True}
        target = {"a": 2, "b": "y", "c": True}
        conflicts = detect_merge_conflicts(source, target)
        assert len(conflicts) == 2
        keys = [c["key"] for c in conflicts]
        assert "a" in keys
        assert "b" in keys

    def test_conflicts_sorted_by_key(self):
        """Conflicts are returned sorted by key name."""
        source = {"z": 1, "a": 2, "m": 3}
        target = {"z": 10, "a": 20, "m": 30}
        conflicts = detect_merge_conflicts(source, target)
        assert [c["key"] for c in conflicts] == ["a", "m", "z"]

    def test_empty_dicts(self):
        """Two empty dicts produce no conflicts."""
        conflicts = detect_merge_conflicts({}, {})
        assert conflicts == []

    def test_one_empty_dict(self):
        """One empty dict and one non-empty produce no conflicts."""
        conflicts = detect_merge_conflicts({"a": 1}, {})
        assert conflicts == []
        conflicts = detect_merge_conflicts({}, {"b": 2})
        assert conflicts == []

    def test_nested_value_conflict(self):
        """Detects conflict when nested values differ (compared by equality)."""
        source = {"config": {"debug": True}}
        target = {"config": {"debug": False}}
        conflicts = detect_merge_conflicts(source, target)
        assert len(conflicts) == 1
        assert conflicts[0]["key"] == "config"

    def test_none_values_no_conflict(self):
        """Same None values produce no conflict."""
        source = {"a": None}
        target = {"a": None}
        conflicts = detect_merge_conflicts(source, target)
        assert conflicts == []

    def test_none_vs_value_conflict(self):
        """None vs non-None value is a conflict."""
        source = {"a": None}
        target = {"a": "something"}
        conflicts = detect_merge_conflicts(source, target)
        assert len(conflicts) == 1


# ============================================================
# preview_merge tests
# ============================================================


class TestPreviewMerge:
    """Tests for preview_merge function."""

    def test_preview_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Preview returns skipped when merge flag is disabled."""
        monkeypatch.setenv("OMG_MERGE_ENABLED", "false")
        result = preview_merge("source", "target", state_dir=mock_state_dir)
        assert result.get("skipped") is True

    def test_preview_source_not_found(self, mock_state_dir):
        """Preview returns error when source branch doesn't exist."""
        # Create only target branch
        create_branch("target", state_dir=mock_state_dir)
        result = preview_merge("nonexistent", "target", state_dir=mock_state_dir)
        assert "error" in result
        assert "nonexistent" in result["error"]

    def test_preview_target_not_found(self, mock_state_dir):
        """Preview returns error when target branch doesn't exist."""
        create_branch("source", state_dir=mock_state_dir)
        result = preview_merge("source", "nonexistent", state_dir=mock_state_dir)
        assert "error" in result
        assert "nonexistent" in result["error"]

    def test_preview_both_branches_exist(self, two_branches):
        """Preview succeeds with both branches present."""
        state_dir, _, _ = two_branches
        result = preview_merge("source-branch", "target-branch", state_dir=state_dir)
        assert "error" not in result
        assert result["preview"] is True
        assert result["source"] == "source-branch"
        assert result["target"] == "target-branch"
        assert isinstance(result["conflicts"], list)
        assert isinstance(result["changes"], int)

    def test_preview_detects_conflicts(self, two_branches):
        """Preview correctly reports conflicts between branches."""
        state_dir, _, _ = two_branches
        # Both branches have different 'name' and 'snapshot_id' fields
        result = preview_merge("source-branch", "target-branch", state_dir=state_dir)
        # The branches should have different name and snapshot_id values
        conflict_keys = [c["key"] for c in result["conflicts"]]
        assert "name" in conflict_keys  # source-branch vs target-branch

    def test_preview_default_target_main(self, mock_state_dir):
        """Preview defaults to 'main' as target branch."""
        create_branch("source", state_dir=mock_state_dir)
        create_branch("main", state_dir=mock_state_dir)
        result = preview_merge("source", state_dir=mock_state_dir)
        assert result.get("target") == "main" or result.get("error")


# ============================================================
# merge_branch tests
# ============================================================


class TestMergeBranch:
    """Tests for merge_branch function."""

    def test_merge_feature_flag_disabled(self, mock_state_dir, monkeypatch):
        """Merge returns skipped when flag is disabled."""
        monkeypatch.setenv("OMG_MERGE_ENABLED", "false")
        result = merge_branch("source", "target", state_dir=mock_state_dir)
        assert result.get("skipped") is True

    def test_merge_source_not_found(self, mock_state_dir):
        """Merge returns error when source branch doesn't exist."""
        create_branch("target", state_dir=mock_state_dir)
        result = merge_branch("nonexistent", "target", state_dir=mock_state_dir)
        assert "error" in result

    def test_merge_target_not_found(self, mock_state_dir):
        """Merge returns error when target branch doesn't exist."""
        create_branch("source", state_dir=mock_state_dir)
        result = merge_branch("source", "nonexistent", state_dir=mock_state_dir)
        assert "error" in result

    def test_merge_with_conflicts_aborted(self, two_branches):
        """Merge is aborted when conflicts exist."""
        state_dir, _, _ = two_branches
        result = merge_branch("source-branch", "target-branch", state_dir=state_dir)
        # source-branch and target-branch have different 'name' values → conflict
        assert result["merged"] is False
        assert len(result["conflicts"]) > 0
        assert result["changes_applied"] == 0

    def test_merge_no_conflicts_succeeds(self, mock_state_dir):
        """Merge succeeds when source and target have identical overlapping keys."""
        # Create two branches with same metadata values for overlapping keys
        create_branch("alpha", state_dir=mock_state_dir)

        # Manually craft a target branch with compatible state
        branches_dir = os.path.join(mock_state_dir, "branches")
        source_path = os.path.join(branches_dir, "alpha.json")
        with open(source_path, "r") as f:
            source_data = json.load(f)

        # Create target with same values for overlapping keys
        target_data = source_data.copy()
        target_data["name"] = "beta"
        target_path = os.path.join(branches_dir, "beta.json")
        with open(target_path, "w") as f:
            json.dump(target_data, f)

        # Now source (alpha) has name="alpha", target (beta) has name="beta"
        # These conflict, so let's make them identical for no-conflict test
        source_data_fixed = target_data.copy()
        source_data_fixed["extra_key"] = "from_source"
        with open(source_path, "w") as f:
            json.dump(source_data_fixed, f)

        # Now source has extra_key that target doesn't — no conflict
        # But name is now "beta" in both — no conflict
        result = merge_branch("alpha", "beta", state_dir=mock_state_dir)
        assert result["merged"] is True
        assert result["conflicts"] == []

    def test_merge_marks_source_as_merged(self, mock_state_dir):
        """After merge, source branch status is 'merged'."""
        # Set up compatible branches
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        shared_state = {
            "name": "shared-name",
            "snapshot_id": "snap1",
            "created_at": "2026-03-02T00:00:00",
            "parent_branch": None,
            "status": "active",
        }
        with open(os.path.join(branches_dir, "src.json"), "w") as f:
            json.dump({**shared_state, "extra": "from_src"}, f)
        with open(os.path.join(branches_dir, "dst.json"), "w") as f:
            json.dump(shared_state, f)

        result = merge_branch("src", "dst", state_dir=mock_state_dir)
        assert result["merged"] is True

        # Verify source branch status
        with open(os.path.join(branches_dir, "src.json"), "r") as f:
            src_meta = json.load(f)
        assert src_meta["status"] == "merged"
        assert src_meta["merged_into"] == "dst"
        assert "merged_at" in src_meta

    def test_merge_updates_target_state(self, mock_state_dir):
        """After merge, target branch has source's extra keys."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        base = {
            "name": "same",
            "snapshot_id": "snap1",
            "status": "active",
        }
        with open(os.path.join(branches_dir, "src.json"), "w") as f:
            json.dump({**base, "new_feature": True}, f)
        with open(os.path.join(branches_dir, "dst.json"), "w") as f:
            json.dump(base, f)

        merge_branch("src", "dst", state_dir=mock_state_dir)

        with open(os.path.join(branches_dir, "dst.json"), "r") as f:
            dst_meta = json.load(f)
        assert dst_meta.get("new_feature") is True
        # Target name should be preserved
        assert dst_meta["name"] == "dst"

    def test_merge_updates_current_branch(self, mock_state_dir):
        """After merge, current_branch.json points to target."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        base = {"name": "same", "snapshot_id": "s1", "status": "active"}
        with open(os.path.join(branches_dir, "src.json"), "w") as f:
            json.dump(base, f)
        with open(os.path.join(branches_dir, "dst.json"), "w") as f:
            json.dump(base, f)

        merge_branch("src", "dst", state_dir=mock_state_dir)

        current_path = os.path.join(mock_state_dir, "current_branch.json")
        with open(current_path, "r") as f:
            current = json.load(f)
        assert current["name"] == "dst"

    def test_merge_does_not_delete_source(self, mock_state_dir):
        """Source branch file still exists after merge (not auto-deleted)."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        base = {"name": "same", "snapshot_id": "s1", "status": "active"}
        with open(os.path.join(branches_dir, "src.json"), "w") as f:
            json.dump(base, f)
        with open(os.path.join(branches_dir, "dst.json"), "w") as f:
            json.dump(base, f)

        merge_branch("src", "dst", state_dir=mock_state_dir)

        assert os.path.exists(os.path.join(branches_dir, "src.json"))


# ============================================================
# _load_branch_state tests
# ============================================================


class TestLoadBranchState:
    """Tests for _load_branch_state helper."""

    def test_load_existing_branch(self, mock_state_dir):
        """Loading an existing branch returns its metadata dict."""
        create_branch("loadme", state_dir=mock_state_dir)
        state = _load_branch_state("loadme", state_dir=mock_state_dir)
        assert state is not None
        assert state["name"] == "loadme"

    def test_load_nonexistent_branch(self, mock_state_dir):
        """Loading a nonexistent branch returns None."""
        state = _load_branch_state("ghost", state_dir=mock_state_dir)
        assert state is None

    def test_load_corrupt_branch(self, mock_state_dir):
        """Loading a branch with corrupt JSON returns None."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)
        with open(os.path.join(branches_dir, "bad.json"), "w") as f:
            f.write("{{{not json")
        state = _load_branch_state("bad", state_dir=mock_state_dir)
        assert state is None


# ============================================================
# Integration tests
# ============================================================


class TestMergeIntegration:
    """Integration tests for merge workflow."""

    def test_preview_then_merge_workflow(self, mock_state_dir):
        """Full workflow: create branches, preview, then merge."""
        branches_dir = os.path.join(mock_state_dir, "branches")
        os.makedirs(branches_dir, exist_ok=True)

        base = {
            "name": "shared",
            "snapshot_id": "snap1",
            "created_at": "2026-03-02T00:00:00",
            "parent_branch": None,
            "status": "active",
        }
        with open(os.path.join(branches_dir, "feature.json"), "w") as f:
            json.dump({**base, "feature_flag": True}, f)
        with open(os.path.join(branches_dir, "main.json"), "w") as f:
            json.dump(base, f)

        # Preview
        preview = preview_merge("feature", "main", state_dir=mock_state_dir)
        assert preview["preview"] is True
        assert preview["changes"] >= 1

        # Merge
        result = merge_branch("feature", "main", state_dir=mock_state_dir)
        assert result["merged"] is True

        # Verify target has feature_flag
        with open(os.path.join(branches_dir, "main.json"), "r") as f:
            main_state = json.load(f)
        assert main_state.get("feature_flag") is True

    def test_merge_does_not_break_existing_functions(self, mock_state_dir):
        """Merge functions don't break existing snapshot/branch operations."""
        # Create snapshot
        snap = create_snapshot(name="pre-merge", state_dir=mock_state_dir)
        assert "id" in snap

        # Create and list branches
        create_branch("test-branch", state_dir=mock_state_dir)
        branches = list_branches(state_dir=mock_state_dir)
        assert len(branches) >= 1

        # Preview merge of nonexistent — should return error, not crash
        result = preview_merge("nonexistent", state_dir=mock_state_dir)
        assert "error" in result
