#!/usr/bin/env python3
"""Tests for tools/ssh_manager.py — SSH Connection Manager."""

import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Ensure tools/ is importable
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from tools import ssh_manager
from tools.ssh_manager import (
    SSHConnection,
    SSHPolicyManager,
    connect,
    detect_os,
    detect_shell,
    disconnect,
    discover_hosts,
    get_connections,
    _connections,
    _pool_key,
    _is_enabled,
)


@pytest.fixture(autouse=True)
def _clear_pool():
    """Clear connection pool before and after each test."""
    _connections.clear()
    yield
    _connections.clear()


@pytest.fixture(autouse=True)
def _auto_approve_policy(tmp_path, monkeypatch):
    """Patch module-level SSH policy to auto-approve all hosts for legacy tests."""
    state_file = str(tmp_path / "ssh_approved_hosts.json")
    permissive = SSHPolicyManager(state_path=state_file)
    # Override requires_approval to always allow
    permissive.requires_approval = lambda host, port=22: {"requires_approval": False, "reason": "test auto-approve"}
    monkeypatch.setattr("tools.ssh_manager._ssh_policy", permissive)


# =============================================================================
# TestSSHConnection — dataclass fields and from_dict
# =============================================================================


class TestSSHConnection:
    """Tests for SSHConnection dataclass."""

    def test_fields_defaults(self):
        """SSHConnection has correct defaults."""
        conn = SSHConnection(host="example.com")
        assert conn.host == "example.com"
        assert conn.port == 22
        assert conn.user == ""
        assert conn.key_path is None
        assert conn.password is None
        assert conn.shell == "bash"
        assert conn.os_type == "linux"

    def test_from_dict(self):
        """SSHConnection.from_dict creates object from dictionary."""
        data = {
            "host": "server.example.com",
            "port": 2222,
            "user": "ubuntu",
            "key_path": "~/.ssh/id_rsa",
            "shell": "zsh",
            "os_type": "macos",
        }
        conn = SSHConnection.from_dict(data)
        assert conn.host == "server.example.com"
        assert conn.port == 2222
        assert conn.user == "ubuntu"
        assert conn.key_path == "~/.ssh/id_rsa"
        assert conn.shell == "zsh"
        assert conn.os_type == "macos"

    def test_to_dict_never_exposes_password(self):
        """to_dict replaces password with password_set indicator."""
        conn = SSHConnection(host="x.com", password="secret123")
        d = conn.to_dict()
        assert "password" not in d
        assert d["password_set"] is True

    def test_to_dict_no_password(self):
        """to_dict shows password_set=False when no password."""
        conn = SSHConnection(host="x.com")
        d = conn.to_dict()
        assert d["password_set"] is False


# =============================================================================
# TestDiscoverHosts — reads ssh.json, .ssh.json, missing file
# =============================================================================


class TestDiscoverHosts:
    """Tests for discover_hosts()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_reads_ssh_json(self, tmp_path):
        """Discovers hosts from ssh.json file."""
        config = {
            "hosts": [
                {"host": "server1.com", "port": 22, "user": "alice"},
                {"host": "server2.com", "port": 2222, "user": "bob", "key_path": "~/.ssh/id_rsa"},
            ]
        }
        config_file = tmp_path / "ssh.json"
        config_file.write_text(json.dumps(config))

        hosts = discover_hosts(str(tmp_path))
        assert len(hosts) == 2
        assert hosts[0].host == "server1.com"
        assert hosts[0].user == "alice"
        assert hosts[1].host == "server2.com"
        assert hosts[1].port == 2222
        # key_path should be expanded
        assert hosts[1].key_path is not None

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_reads_dot_ssh_json(self, tmp_path):
        """Discovers hosts from .ssh.json when ssh.json is absent."""
        config = {
            "hosts": [
                {"host": "hidden-server.com", "user": "root"},
            ]
        }
        config_file = tmp_path / ".ssh.json"
        config_file.write_text(json.dumps(config))

        hosts = discover_hosts(str(tmp_path))
        assert len(hosts) == 1
        assert hosts[0].host == "hidden-server.com"
        assert hosts[0].user == "root"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_handles_missing_file(self, tmp_path):
        """Returns empty list when no config file exists."""
        hosts = discover_hosts(str(tmp_path))
        assert hosts == []

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_disabled_returns_empty(self, tmp_path):
        """Returns empty list when feature flag is disabled."""
        config_file = tmp_path / "ssh.json"
        config_file.write_text(json.dumps({"hosts": [{"host": "x.com"}]}))

        hosts = discover_hosts(str(tmp_path))
        assert hosts == []


# =============================================================================
# TestConnect — returns spec, adds to pool, flag disabled
# =============================================================================


class TestConnect:
    """Tests for connect()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_returns_spec(self):
        """connect() returns connection spec dict."""
        result = connect("myhost.com", port=22, user="admin")
        assert result["success"] is True
        spec = result["result"]
        assert spec["host"] == "myhost.com"
        assert spec["port"] == 22
        assert spec["user"] == "admin"
        assert spec["connected"] is True
        assert "session_id" in spec
        assert len(spec["session_id"]) == 12

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_adds_to_pool(self):
        """connect() adds connection to the module-level pool."""
        assert len(_connections) == 0
        connect("poolhost.com", port=2222)
        assert "poolhost.com:2222" in _connections

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_disabled_returns_error(self):
        """connect() returns error when flag disabled."""
        result = connect("myhost.com")
        assert result["success"] is False
        assert "disabled" in result["error"]

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_password_never_stored(self):
        """connect() never stores actual password in spec."""
        result = connect("secure.com", password="s3cret!")
        spec = result["result"]
        assert spec["password_set"] is True
        assert "s3cret!" not in json.dumps(spec)

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_empty_host_returns_error(self):
        """connect() rejects empty host."""
        result = connect("")
        assert result["success"] is False
        assert "non-empty" in result["error"]


# =============================================================================
# TestDetectOsShell — detect_os and detect_shell return strings
# =============================================================================


class TestDetectOsShell:
    """Tests for detect_os() and detect_shell()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_detect_os_returns_string(self):
        """detect_os() returns a valid OS string."""
        result = detect_os({"host": "myserver.com"})
        assert result in ("linux", "macos", "windows")

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_detect_os_with_metadata(self):
        """detect_os() uses os_type from connection metadata."""
        result = detect_os({"host": "mac-server", "os_type": "macos"})
        assert result == "macos"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_detect_os_heuristic_windows(self):
        """detect_os() infers windows from hostname."""
        result = detect_os({"host": "win-server-01"})
        assert result == "windows"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_detect_shell_returns_string(self):
        """detect_shell() returns a valid shell string."""
        result = detect_shell({"host": "myserver.com"})
        assert result in ("bash", "zsh", "sh", "powershell", "fish")

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_detect_shell_from_os(self):
        """detect_shell() infers shell from OS type."""
        result = detect_shell({"host": "win-box", "os_type": "windows"})
        assert result == "powershell"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_detect_shell_macos(self):
        """detect_shell() returns zsh for macos."""
        result = detect_shell({"host": "mac", "os_type": "macos"})
        assert result == "zsh"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_detect_os_disabled(self):
        """detect_os() returns 'unknown' when disabled."""
        result = detect_os({"host": "x"})
        assert result == "unknown"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_detect_shell_disabled(self):
        """detect_shell() returns 'unknown' when disabled."""
        result = detect_shell({"host": "x"})
        assert result == "unknown"


# =============================================================================
# TestGetDisconnect — list and remove connections
# =============================================================================


class TestGetDisconnect:
    """Tests for get_connections() and disconnect()."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_get_connections_lists(self):
        """get_connections() returns all pool entries."""
        connect("host1.com")
        connect("host2.com", port=2222)
        conns = get_connections()
        assert len(conns) == 2
        hosts = {c["host"] for c in conns}
        assert "host1.com" in hosts
        assert "host2.com" in hosts

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_disconnect_removes(self):
        """disconnect() removes a connection from the pool."""
        connect("removeme.com")
        assert len(_connections) == 1
        removed = disconnect("removeme.com")
        assert removed is True
        assert len(_connections) == 0

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_disconnect_nonexistent(self):
        """disconnect() returns False for non-existent connection."""
        removed = disconnect("nohost.com")
        assert removed is False

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_get_connections_disabled(self):
        """get_connections() returns empty when disabled."""
        # Manually insert to pool to test flag check
        _connections["x:22"] = {"host": "x"}
        conns = get_connections()
        assert conns == []


# =============================================================================
# TestFeatureFlag — edge cases
# =============================================================================


class TestFeatureFlag:
    """Tests for feature flag behavior."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_enabled_true(self):
        """Feature flag enabled via env var."""
        assert _is_enabled() is True

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "false"})
    def test_enabled_false(self):
        """Feature flag disabled via env var."""
        assert _is_enabled() is False

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "1"})
    def test_enabled_numeric(self):
        """Feature flag enabled via '1'."""
        assert _is_enabled() is True

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "0"})
    def test_disabled_numeric(self):
        """Feature flag disabled via '0'."""
        assert _is_enabled() is False


# =============================================================================
# TestPoolKey — internal helper
# =============================================================================


class TestPoolKey:
    """Tests for _pool_key() helper."""

    def test_default_port(self):
        """Pool key with default port."""
        assert _pool_key("host.com") == "host.com:22"

    def test_custom_port(self):
        """Pool key with custom port."""
        assert _pool_key("host.com", 2222) == "host.com:2222"


# =============================================================================
# TestCLI — basic CLI smoke tests
# =============================================================================


class TestCLI:
    """Tests for CLI entry point."""

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_discover_cli(self, tmp_path, capsys):
        """CLI --discover outputs JSON."""
        config = {"hosts": [{"host": "cli-test.com", "user": "tester"}]}
        (tmp_path / "ssh.json").write_text(json.dumps(config))

        with patch("sys.argv", ["ssh_manager.py", "--discover", "--project-dir", str(tmp_path)]):
            ssh_manager._cli_main()

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["count"] == 1
        assert output["hosts"][0]["host"] == "cli-test.com"

    @patch.dict(os.environ, {"OAL_SSH_ENABLED": "true"})
    def test_discover_dry_run(self, tmp_path, capsys):
        """CLI --discover --dry-run outputs dry run info."""
        with patch("sys.argv", ["ssh_manager.py", "--discover", "--dry-run", "--project-dir", str(tmp_path)]):
            ssh_manager._cli_main()

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["dry_run"] is True
        assert output["operation"] == "discover"
