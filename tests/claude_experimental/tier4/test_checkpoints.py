"""Tests for claude_experimental.integration.checkpoints — CheckpointManager."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _enable_integration(monkeypatch):
    """Enable the ADVANCED_INTEGRATION feature flag for all tests."""
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")


@pytest.fixture
def manager(tmp_path):
    """CheckpointManager using tmp_path as state_dir."""
    from claude_experimental.integration.checkpoints import CheckpointManager

    return CheckpointManager(base_dir=str(tmp_path))


@pytest.mark.experimental
class TestCheckpointLifecycle:
    """Create → list → resume lifecycle tests."""

    def test_create_returns_uuid(self, manager):
        """create_checkpoint() returns a UUID string."""
        cid = manager.create_checkpoint(
            checkpoint_type="DECISION",
            description="Choose deployment target",
            options=["staging", "production"],
        )
        assert isinstance(cid, str)
        assert len(cid) == 36  # UUID format

    def test_get_checkpoint_returns_data(self, manager):
        """get_checkpoint() returns complete checkpoint dict."""
        cid = manager.create_checkpoint(
            checkpoint_type="VERIFICATION",
            description="Verify test results",
        )
        data = manager.get_checkpoint(cid)
        assert data["checkpoint_id"] == cid
        assert data["type"] == "VERIFICATION"
        assert data["description"] == "Verify test results"
        assert data["status"] == "pending"
        assert data["decision"] is None

    def test_list_pending_includes_new_checkpoint(self, manager):
        """list_pending() returns newly created checkpoints."""
        cid = manager.create_checkpoint(
            checkpoint_type="CLARIFICATION",
            description="Clarify requirements",
        )
        pending = manager.list_pending()
        assert len(pending) == 1
        assert pending[0]["checkpoint_id"] == cid

    def test_resume_resolves_checkpoint(self, manager):
        """resume_checkpoint() transitions pending → resolved."""
        cid = manager.create_checkpoint(
            checkpoint_type="DECISION",
            description="Choose target",
            options=["A", "B"],
        )
        result = manager.resume_checkpoint(cid, decision="A")
        assert result is True

        data = manager.get_checkpoint(cid)
        assert data["status"] == "resolved"
        assert data["decision"] == "A"

    def test_resume_resolved_returns_false(self, manager):
        """Resuming an already-resolved checkpoint returns False."""
        cid = manager.create_checkpoint(
            checkpoint_type="DECISION",
            description="Choose",
            options=["X"],
        )
        manager.resume_checkpoint(cid, decision="X")
        result = manager.resume_checkpoint(cid, decision="Y")
        assert result is False

    def test_resolved_checkpoint_excluded_from_pending(self, manager):
        """Resolved checkpoints don't appear in list_pending()."""
        cid = manager.create_checkpoint(
            checkpoint_type="VERIFICATION",
            description="Verify",
        )
        manager.resume_checkpoint(cid, decision="ok")
        pending = manager.list_pending()
        assert len(pending) == 0


@pytest.mark.experimental
class TestCheckpointExpiry:
    """Expired checkpoint cleanup tests."""

    def test_expired_checkpoint_auto_transitions(self, tmp_path):
        """get_checkpoint() auto-transitions expired checkpoints."""
        from claude_experimental.integration.checkpoints import CheckpointManager

        mgr = CheckpointManager(base_dir=str(tmp_path))
        cid = mgr.create_checkpoint(
            checkpoint_type="DECISION",
            description="Expired test",
            timeout_seconds=1,
        )
        # Wait for expiry
        time.sleep(1.5)

        data = mgr.get_checkpoint(cid)
        assert data["status"] == "expired"

    def test_cleanup_expired_removes_files(self, tmp_path):
        """cleanup_expired() deletes expired checkpoint files."""
        from claude_experimental.integration.checkpoints import CheckpointManager

        mgr = CheckpointManager(base_dir=str(tmp_path))
        cid = mgr.create_checkpoint(
            checkpoint_type="VERIFICATION",
            description="Will expire",
            timeout_seconds=1,
        )
        time.sleep(1.5)

        removed = mgr.cleanup_expired()
        assert removed == 1

        with pytest.raises(KeyError):
            mgr.get_checkpoint(cid)


@pytest.mark.experimental
class TestCheckpointEdgeCases:
    """Edge case tests."""

    def test_invalid_checkpoint_type_raises(self, manager):
        """Invalid checkpoint_type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid checkpoint type"):
            manager.create_checkpoint(
                checkpoint_type="INVALID",
                description="Bad type",
            )

    def test_nonexistent_checkpoint_raises_key_error(self, manager):
        """Getting a nonexistent checkpoint raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            manager.get_checkpoint("nonexistent-id")

    def test_disabled_flag_raises_runtime_error(self, monkeypatch, tmp_path):
        """CheckpointManager operations raise RuntimeError when flag is off."""
        from claude_experimental.integration.checkpoints import CheckpointManager

        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "0")
        mgr = CheckpointManager(base_dir=str(tmp_path))

        with pytest.raises(RuntimeError, match="disabled"):
            mgr.create_checkpoint(
                checkpoint_type="DECISION",
                description="Should fail",
            )
