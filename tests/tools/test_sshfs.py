#!/usr/bin/env python3
"""Tests for SSHFS mount management in tools/ssh_manager.py."""

import json
import os
import sys
from unittest.mock import patch

import pytest

# Ensure tools/ is importable
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from tools.ssh_manager import (
    _mounts,
    auto_mount_from_config,
    cleanup_mounts,
    get_mounts,
    mount_sshfs,
    unmount_sshfs,
)


@pytest.fixture(autouse=True)
def _clear_mounts():
    """Clear mount registry before and after each test."""
    _mounts.clear()
    yield
    _mounts.clear()


# =============================================================================
# TestMountSshfs — spec generation and registry
# =============================================================================


class TestMountSshfs:
    """Tests for mount_sshfs()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_returns_mount_spec(self):
        """mount_sshfs() returns a valid mount spec dict."""
        result = mount_sshfs("server.com", "/home/user", "/mnt/remote")
        assert result["success"] is True
        assert result["host"] == "server.com"
        assert result["remote_path"] == "/home/user"
        assert result["mounted"] is True
        assert result["mount_id"] == "server.com:/home/user"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_registers_in_mounts(self):
        """mount_sshfs() adds mount to module-level _mounts."""
        assert len(_mounts) == 0
        mount_sshfs("server.com", "/data", "/mnt/data")
        assert len(_mounts) == 1
        abs_path = os.path.abspath("/mnt/data")
        assert abs_path in _mounts

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_with_user_and_key(self):
        """mount_sshfs() includes user and expanded key_path."""
        result = mount_sshfs(
            "server.com", "/data", "/mnt/data",
            user="alice", key_path="~/.ssh/id_rsa", port=2222,
        )
        assert result["user"] == "alice"
        assert result["port"] == 2222
        assert "key_path" in result
        assert "~" not in result["key_path"]  # expanded

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_disabled_returns_error(self):
        """mount_sshfs() returns error when flag disabled."""
        result = mount_sshfs("server.com", "/data", "/mnt/data")
        assert result["success"] is False
        assert "disabled" in result["error"]

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_empty_host_returns_error(self):
        """mount_sshfs() rejects empty host."""
        result = mount_sshfs("", "/data", "/mnt/data")
        assert result["success"] is False
        assert "Host" in result["error"]

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_empty_remote_path_returns_error(self):
        """mount_sshfs() rejects empty remote_path."""
        result = mount_sshfs("server.com", "", "/mnt/data")
        assert result["success"] is False
        assert "Remote path" in result["error"]

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_empty_local_path_returns_error(self):
        """mount_sshfs() rejects empty local_path."""
        result = mount_sshfs("server.com", "/data", "")
        assert result["success"] is False
        assert "Local path" in result["error"]


# =============================================================================
# TestUnmountSshfs — remove from registry
# =============================================================================


class TestUnmountSshfs:
    """Tests for unmount_sshfs()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_unmount_existing(self):
        """unmount_sshfs() removes a registered mount."""
        mount_sshfs("server.com", "/data", "/mnt/data")
        assert len(_mounts) == 1
        result = unmount_sshfs("/mnt/data")
        assert result["success"] is True
        assert result["mounted"] is False
        assert result["mount_id"] == "server.com:/data"
        assert len(_mounts) == 0

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_unmount_nonexistent(self):
        """unmount_sshfs() returns error for unknown mount."""
        result = unmount_sshfs("/mnt/nonexistent")
        assert result["success"] is False
        assert "No mount found" in result["error"]

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_unmount_disabled(self):
        """unmount_sshfs() returns error when flag disabled."""
        result = unmount_sshfs("/mnt/data")
        assert result["success"] is False
        assert "disabled" in result["error"]


# =============================================================================
# TestGetMounts — list active mounts
# =============================================================================


class TestGetMounts:
    """Tests for get_mounts()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_lists_all_mounts(self):
        """get_mounts() returns all registered mounts."""
        mount_sshfs("s1.com", "/path1", "/mnt/a")
        mount_sshfs("s2.com", "/path2", "/mnt/b")
        mounts = get_mounts()
        assert len(mounts) == 2
        hosts = {m["host"] for m in mounts}
        assert "s1.com" in hosts
        assert "s2.com" in hosts

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_get_mounts_disabled(self):
        """get_mounts() returns empty list when disabled."""
        _mounts["/fake"] = {"host": "x"}
        assert get_mounts() == []


# =============================================================================
# TestCleanupMounts — clear all mounts
# =============================================================================


class TestCleanupMounts:
    """Tests for cleanup_mounts()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_cleanup_returns_count(self):
        """cleanup_mounts() returns number of mounts cleaned."""
        mount_sshfs("s1.com", "/p1", "/mnt/a")
        mount_sshfs("s2.com", "/p2", "/mnt/b")
        mount_sshfs("s3.com", "/p3", "/mnt/c")
        count = cleanup_mounts()
        assert count == 3
        assert len(_mounts) == 0

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_cleanup_empty(self):
        """cleanup_mounts() returns 0 when no mounts."""
        count = cleanup_mounts()
        assert count == 0

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_cleanup_disabled(self):
        """cleanup_mounts() returns 0 when disabled."""
        _mounts["/fake"] = {"host": "x"}
        count = cleanup_mounts()
        assert count == 0


# =============================================================================
# TestAutoMountFromConfig — reads ssh.json sshfs_mounts
# =============================================================================


class TestAutoMountFromConfig:
    """Tests for auto_mount_from_config()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_reads_sshfs_mounts(self, tmp_path):
        """auto_mount_from_config() reads sshfs_mounts from ssh.json."""
        config = {
            "sshfs_mounts": [
                {"host": "s1.com", "remote_path": "/home/user", "local_path": "/mnt/s1"},
                {"host": "s2.com", "remote_path": "/data", "local_path": "/mnt/s2", "port": 2222},
            ]
        }
        (tmp_path / "ssh.json").write_text(json.dumps(config))

        results = auto_mount_from_config(str(tmp_path))
        assert len(results) == 2
        assert results[0]["host"] == "s1.com"
        assert results[1]["host"] == "s2.com"
        assert results[1]["port"] == 2222
        assert len(_mounts) == 2

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_reads_dot_ssh_json(self, tmp_path):
        """auto_mount_from_config() reads from .ssh.json fallback."""
        config = {
            "sshfs_mounts": [
                {"host": "hidden.com", "remote_path": "/secret", "local_path": "/mnt/hidden"},
            ]
        }
        (tmp_path / ".ssh.json").write_text(json.dumps(config))

        results = auto_mount_from_config(str(tmp_path))
        assert len(results) == 1
        assert results[0]["host"] == "hidden.com"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_no_config_file(self, tmp_path):
        """auto_mount_from_config() returns empty when no config."""
        results = auto_mount_from_config(str(tmp_path))
        assert results == []

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_skips_incomplete_entries(self, tmp_path):
        """auto_mount_from_config() skips entries missing required fields."""
        config = {
            "sshfs_mounts": [
                {"host": "good.com", "remote_path": "/data", "local_path": "/mnt/good"},
                {"host": "bad.com"},  # missing remote_path and local_path
                {"remote_path": "/x", "local_path": "/y"},  # missing host
            ]
        }
        (tmp_path / "ssh.json").write_text(json.dumps(config))

        results = auto_mount_from_config(str(tmp_path))
        assert len(results) == 1
        assert results[0]["host"] == "good.com"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_disabled_returns_empty(self, tmp_path):
        """auto_mount_from_config() returns empty when flag disabled."""
        config = {
            "sshfs_mounts": [
                {"host": "s.com", "remote_path": "/d", "local_path": "/m"},
            ]
        }
        (tmp_path / "ssh.json").write_text(json.dumps(config))

        results = auto_mount_from_config(str(tmp_path))
        assert results == []

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_invalid_json_returns_empty(self, tmp_path):
        """auto_mount_from_config() handles invalid JSON gracefully."""
        (tmp_path / "ssh.json").write_text("{bad json!!!")

        results = auto_mount_from_config(str(tmp_path))
        assert results == []

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_no_sshfs_mounts_key(self, tmp_path):
        """auto_mount_from_config() returns empty when key is missing."""
        config = {"hosts": [{"host": "x.com"}]}
        (tmp_path / "ssh.json").write_text(json.dumps(config))

        results = auto_mount_from_config(str(tmp_path))
        assert results == []
