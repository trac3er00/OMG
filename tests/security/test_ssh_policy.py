#!/usr/bin/env python3
"""
Security tests for SSH Policy Manager.

Tests SSH-specific policy checks, host approval workflow, fingerprint
verification, and connect() policy gate integration.
"""

import json
import os
import sys
import tempfile

import pytest

# Add project root to path
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.ssh_manager import (
    SSHPolicyManager,
    _check_ssh_policy,
    _ssh_policy,
    connect,
    _connections,
)


@pytest.fixture(autouse=True)
def enable_ssh(monkeypatch):
    """Enable SSH feature for all tests."""
    monkeypatch.setenv("OMG_SSH_ENABLED", "true")


@pytest.fixture
def tmp_state(tmp_path):
    """Create a SSHPolicyManager with a temp state file."""
    state_file = str(tmp_path / "ssh_approved_hosts.json")
    return SSHPolicyManager(state_path=state_file), state_file


@pytest.fixture
def policy_with_host(tmp_state):
    """SSHPolicyManager pre-loaded with one approved host."""
    mgr, state_file = tmp_state
    mgr.approve_host("server.example.com", 22, fingerprint="SHA256:abc123")
    return mgr, state_file


@pytest.fixture(autouse=True)
def patch_global_policy(tmp_path, monkeypatch):
    """Replace the module-level _ssh_policy singleton with a temp-backed one."""
    state_file = str(tmp_path / "global_ssh_approved_hosts.json")
    temp_policy = SSHPolicyManager(state_path=state_file)
    monkeypatch.setattr("tools.ssh_manager._ssh_policy", temp_policy)
    yield temp_policy
    # Clean up connection pool
    _connections.clear()


# =============================================================================
# SSHPolicyManager — Core host approval tests
# =============================================================================


class TestSSHPolicyManagerApproval:
    """Tests for host approval, revocation, and listing."""

    def test_unapproved_host_returns_false(self, tmp_state):
        """Unapproved host is not in the list."""
        mgr, _ = tmp_state
        assert mgr.is_host_approved("unknown.host.com") is False

    def test_approve_host_basic(self, tmp_state):
        """Approving a host makes it appear in approved list."""
        mgr, _ = tmp_state
        result = mgr.approve_host("myserver.com", 22)
        assert result is True
        assert mgr.is_host_approved("myserver.com", 22) is True

    def test_approve_host_with_fingerprint(self, tmp_state):
        """Approving with fingerprint stores it correctly."""
        mgr, state_file = tmp_state
        mgr.approve_host("secure.host", 22, fingerprint="SHA256:deadbeef")
        hosts = mgr.get_approved_hosts()
        assert len(hosts) == 1
        assert hosts[0]["fingerprint"] == "SHA256:deadbeef"
        assert hosts[0]["host"] == "secure.host"

    def test_approve_host_custom_port(self, tmp_state):
        """Host approval respects port number."""
        mgr, _ = tmp_state
        mgr.approve_host("server.com", 2222)
        assert mgr.is_host_approved("server.com", 2222) is True
        assert mgr.is_host_approved("server.com", 22) is False

    def test_revoke_host(self, policy_with_host):
        """Revoking a host removes it from the approved list."""
        mgr, _ = policy_with_host
        assert mgr.is_host_approved("server.example.com") is True
        result = mgr.revoke_host("server.example.com", 22)
        assert result is True
        assert mgr.is_host_approved("server.example.com") is False

    def test_revoke_nonexistent_host(self, tmp_state):
        """Revoking a host that doesn't exist returns False."""
        mgr, _ = tmp_state
        result = mgr.revoke_host("ghost.host.com")
        assert result is False

    def test_get_approved_hosts_empty(self, tmp_state):
        """Empty state returns empty list."""
        mgr, _ = tmp_state
        assert mgr.get_approved_hosts() == []

    def test_get_approved_hosts_multiple(self, tmp_state):
        """Multiple approved hosts returned correctly."""
        mgr, _ = tmp_state
        mgr.approve_host("host1.com", 22)
        mgr.approve_host("host2.com", 2222)
        mgr.approve_host("host3.com", 22, fingerprint="SHA256:abc")
        hosts = mgr.get_approved_hosts()
        assert len(hosts) == 3
        host_names = [h["host"] for h in hosts]
        assert "host1.com" in host_names
        assert "host2.com" in host_names
        assert "host3.com" in host_names

    def test_approve_duplicate_host_is_idempotent(self, tmp_state):
        """Approving the same host twice doesn't duplicate."""
        mgr, _ = tmp_state
        mgr.approve_host("dup.host.com", 22)
        mgr.approve_host("dup.host.com", 22)
        hosts = mgr.get_approved_hosts()
        assert len(hosts) == 1

    def test_approve_empty_host_fails(self, tmp_state):
        """Approving empty host returns False."""
        mgr, _ = tmp_state
        assert mgr.approve_host("") is False
        assert mgr.approve_host(None) is False


# =============================================================================
# SSHPolicyManager — requires_approval
# =============================================================================


class TestRequiresApproval:
    """Tests for the requires_approval() method."""

    def test_unapproved_requires_approval(self, tmp_state):
        """Unapproved host requires approval."""
        mgr, _ = tmp_state
        result = mgr.requires_approval("new.host.com")
        assert result["requires_approval"] is True
        assert "not in the approved" in result["reason"]

    def test_approved_does_not_require_approval(self, policy_with_host):
        """Approved host does not require approval."""
        mgr, _ = policy_with_host
        result = mgr.requires_approval("server.example.com", 22)
        assert result["requires_approval"] is False

    def test_empty_host_requires_approval(self, tmp_state):
        """Empty host requires approval."""
        mgr, _ = tmp_state
        result = mgr.requires_approval("")
        assert result["requires_approval"] is True


# =============================================================================
# Fingerprint verification
# =============================================================================


class TestFingerprintVerification:
    """Tests for fingerprint comparison."""

    def test_matching_fingerprints(self, tmp_state):
        """Identical fingerprints return True."""
        mgr, _ = tmp_state
        assert mgr.verify_fingerprint("host", "SHA256:abc", "SHA256:abc") is True

    def test_mismatched_fingerprints(self, tmp_state):
        """Different fingerprints return False."""
        mgr, _ = tmp_state
        assert mgr.verify_fingerprint("host", "SHA256:abc", "SHA256:xyz") is False

    def test_empty_fingerprint(self, tmp_state):
        """Empty fingerprints return False."""
        mgr, _ = tmp_state
        assert mgr.verify_fingerprint("host", "", "SHA256:abc") is False
        assert mgr.verify_fingerprint("host", "SHA256:abc", "") is False

    def test_whitespace_trimmed(self, tmp_state):
        """Fingerprints with surrounding whitespace still match."""
        mgr, _ = tmp_state
        assert mgr.verify_fingerprint("host", "SHA256:abc ", " SHA256:abc") is True


# =============================================================================
# _check_ssh_policy() — module-level policy check
# =============================================================================


class TestCheckSSHPolicy:
    """Tests for the _check_ssh_policy function."""

    def test_unapproved_host_denied(self, patch_global_policy):
        """Unapproved host is denied by policy check."""
        result = _check_ssh_policy("evil.host.com", 22)
        assert result["allowed"] is False
        assert "not in the approved" in result["reason"]

    def test_approved_host_allowed(self, patch_global_policy):
        """Approved host is allowed by policy check."""
        patch_global_policy.approve_host("good.host.com", 22)
        result = _check_ssh_policy("good.host.com", 22)
        assert result["allowed"] is True

    def test_empty_host_denied(self):
        """Empty host is denied."""
        result = _check_ssh_policy("", 22)
        assert result["allowed"] is False


# =============================================================================
# connect() — policy gate integration
# =============================================================================


class TestConnectPolicyGate:
    """Tests for connect() with SSH policy gate."""

    def test_connect_unapproved_host_blocked(self, patch_global_policy):
        """connect() to unapproved host returns requires_approval error."""
        result = connect("unapproved.host.com", 22)
        assert result["success"] is False
        assert result["requires_approval"] is True
        assert "not approved" in result["error"].lower()

    def test_connect_approved_host_succeeds(self, patch_global_policy):
        """connect() to approved host succeeds."""
        patch_global_policy.approve_host("approved.host.com", 22)
        result = connect("approved.host.com", 22, user="testuser")
        assert result["success"] is True
        assert result["result"]["host"] == "approved.host.com"
        assert result["result"]["user"] == "testuser"

    def test_connect_approve_then_connect_workflow(self, patch_global_policy):
        """Full workflow: blocked → approve → connect succeeds."""
        # Step 1: Connection blocked
        r1 = connect("workflow.host.com", 22)
        assert r1["success"] is False
        assert r1["requires_approval"] is True

        # Step 2: Approve the host
        patch_global_policy.approve_host("workflow.host.com", 22)

        # Step 3: Connection succeeds
        r2 = connect("workflow.host.com", 22)
        assert r2["success"] is True

    def test_connect_revoke_then_blocked(self, patch_global_policy):
        """After revoking a host, connect is blocked again."""
        patch_global_policy.approve_host("temp.host.com", 22)
        r1 = connect("temp.host.com", 22)
        assert r1["success"] is True

        patch_global_policy.revoke_host("temp.host.com", 22)
        # Clear connection pool so we can reconnect
        _connections.clear()
        r2 = connect("temp.host.com", 22)
        assert r2["success"] is False
        assert r2["requires_approval"] is True


# =============================================================================
# State file persistence
# =============================================================================


class TestStatePersistence:
    """Tests for JSON state file read/write."""

    def test_state_file_created_on_approve(self, tmp_state):
        """State file is created when first host is approved."""
        mgr, state_file = tmp_state
        assert not os.path.exists(state_file)
        mgr.approve_host("new.host.com")
        assert os.path.exists(state_file)

    def test_state_file_valid_json(self, tmp_state):
        """State file contains valid JSON with expected structure."""
        mgr, state_file = tmp_state
        mgr.approve_host("json.host.com", 22, fingerprint="SHA256:test")
        with open(state_file, "r") as f:
            data = json.load(f)
        assert "hosts" in data
        assert len(data["hosts"]) == 1
        assert data["hosts"][0]["host"] == "json.host.com"
        assert data["hosts"][0]["fingerprint"] == "SHA256:test"
        assert "approved_at" in data["hosts"][0]

    def test_corrupt_state_file_handled(self, tmp_state):
        """Corrupt state file returns empty list gracefully."""
        mgr, state_file = tmp_state
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            f.write("not valid json {{{")
        assert mgr.get_approved_hosts() == []
        assert mgr.is_host_approved("any.host") is False
