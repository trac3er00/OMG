"""Tests for policy_engine allowlist support (Task 20).

TDD: These tests are written FIRST, before implementation.
"""

import os
import sys
import json
import tempfile
import textwrap

import pytest

# Ensure hooks/ is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "hooks"))

from policy_engine import (
    is_allowlisted,
    validate_allowlist_entry,
    load_allowlist,
    _log_allowlist_bypass,
    evaluate_file_access,
    OVERLY_BROAD_GLOBS,
)


# ---------------------------------------------------------------------------
# validate_allowlist_entry
# ---------------------------------------------------------------------------


class TestValidateAllowlistEntry:
    """Validation of individual allowlist entries."""

    def test_accepts_valid_entry(self):
        """Valid entry with all required fields passes validation."""
        # Should not raise
        validate_allowlist_entry({
            "path": ".env.*",
            "tools": ["Read"],
            "reason": "test env files are safe to read",
        })

    def test_rejects_missing_path(self):
        """Entry without 'path' field raises ValueError."""
        with pytest.raises(ValueError, match="path"):
            validate_allowlist_entry({
                "tools": ["Read"],
                "reason": "missing path",
            })

    def test_rejects_missing_tools(self):
        """Entry without 'tools' field raises ValueError."""
        with pytest.raises(ValueError, match="tools"):
            validate_allowlist_entry({
                "path": "*.txt",
                "reason": "missing tools",
            })

    def test_rejects_missing_reason(self):
        """Entry without 'reason' field raises ValueError."""
        with pytest.raises(ValueError, match="reason"):
            validate_allowlist_entry({
                "path": "*.txt",
                "tools": ["Read"],
            })

    def test_rejects_star_glob(self):
        """Overly broad glob '*' is rejected."""
        with pytest.raises(ValueError, match="broad"):
            validate_allowlist_entry({
                "path": "*",
                "tools": ["Read"],
                "reason": "too broad",
            })

    def test_rejects_double_star_glob(self):
        """Overly broad glob '**' is rejected."""
        with pytest.raises(ValueError, match="broad"):
            validate_allowlist_entry({
                "path": "**",
                "tools": ["Read"],
                "reason": "too broad",
            })

    def test_rejects_double_star_slash_star(self):
        """Overly broad glob '**/*' is rejected."""
        with pytest.raises(ValueError, match="broad"):
            validate_allowlist_entry({
                "path": "**/*",
                "tools": ["Read"],
                "reason": "too broad",
            })

    def test_rejects_non_dict_entry(self):
        """Non-dict entry raises ValueError."""
        with pytest.raises(ValueError, match="dict"):
            validate_allowlist_entry("not a dict")

    def test_rejects_empty_tools_list(self):
        """Empty tools list is rejected."""
        with pytest.raises(ValueError, match="tools"):
            validate_allowlist_entry({
                "path": "*.txt",
                "tools": [],
                "reason": "empty tools",
            })

    def test_rejects_tools_not_list(self):
        """Non-list tools field is rejected."""
        with pytest.raises(ValueError, match="tools"):
            validate_allowlist_entry({
                "path": "*.txt",
                "tools": "Read",
                "reason": "string not list",
            })


# ---------------------------------------------------------------------------
# is_allowlisted
# ---------------------------------------------------------------------------


class TestIsAllowlisted:
    """Matching logic for allowlist entries against path+tool."""

    def test_matches_path_and_tool(self):
        """Path matching glob AND tool in tools list returns True."""
        allowlist = [
            {"path": ".env.*", "tools": ["Read"], "reason": "test env files"},
        ]
        assert is_allowlisted(".env.test", "Read", allowlist) is True

    def test_returns_false_when_no_match(self):
        """Path not matching any entry returns False."""
        allowlist = [
            {"path": ".env.*", "tools": ["Read"], "reason": "test env files"},
        ]
        assert is_allowlisted("secret.key", "Read", allowlist) is False

    def test_rejects_wrong_tool(self):
        """Path matches but tool not in tools list returns False."""
        allowlist = [
            {"path": ".env.*", "tools": ["Read"], "reason": "test env only read"},
        ]
        assert is_allowlisted(".env.test", "Write", allowlist) is False

    def test_matches_full_path_glob(self):
        """Full path glob like 'tests/*.env' matches."""
        allowlist = [
            {"path": "tests/*.env", "tools": ["Read", "Write"], "reason": "test fixtures"},
        ]
        assert is_allowlisted("tests/staging.env", "Read", allowlist) is True

    def test_skips_invalid_entries(self):
        """Invalid entries in allowlist are silently skipped."""
        allowlist = [
            "not a dict",
            {"path": "*", "tools": ["Read"], "reason": "overly broad"},
            {"path": ".env.test", "tools": ["Read"], "reason": "valid"},
        ]
        # First two are invalid, third matches
        assert is_allowlisted(".env.test", "Read", allowlist) is True

    def test_empty_allowlist_returns_false(self):
        """Empty allowlist returns False."""
        assert is_allowlisted(".env.test", "Read", []) is False

    def test_multiple_tools_in_entry(self):
        """Entry with multiple tools matches any of them."""
        allowlist = [
            {"path": "config/*.yaml", "tools": ["Read", "Write", "Edit"], "reason": "config files"},
        ]
        assert is_allowlisted("config/app.yaml", "Edit", allowlist) is True
        assert is_allowlisted("config/app.yaml", "Read", allowlist) is True


# ---------------------------------------------------------------------------
# load_allowlist
# ---------------------------------------------------------------------------


class TestLoadAllowlist:
    """Loading allowlist from .omg/policy.yaml."""

    def test_returns_empty_when_no_file(self):
        """Returns empty list when policy.yaml doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_allowlist(tmpdir)
            assert result == []

    def test_returns_empty_when_no_allowlist_section(self):
        """Returns empty list when policy.yaml exists but has no allowlist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            omg_dir = os.path.join(tmpdir, ".omg")
            os.makedirs(omg_dir)
            policy_path = os.path.join(omg_dir, "policy.yaml")
            with open(policy_path, "w") as f:
                f.write("blocked_files:\n  - .env\n")
            result = load_allowlist(tmpdir)
            assert result == []

    def test_loads_valid_allowlist(self):
        """Loads allowlist entries from policy.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            omg_dir = os.path.join(tmpdir, ".omg")
            os.makedirs(omg_dir)
            policy_path = os.path.join(omg_dir, "policy.yaml")
            with open(policy_path, "w") as f:
                f.write(textwrap.dedent("""\
                    allowlist:
                      - path: ".env.test"
                        tools:
                          - Read
                        reason: "test env files"
                      - path: "tests/*.fixture"
                        tools:
                          - Read
                          - Write
                        reason: "test fixtures"
                """))
            result = load_allowlist(tmpdir)
            assert len(result) == 2
            assert result[0]["path"] == ".env.test"
            assert result[0]["tools"] == ["Read"]
            assert result[1]["path"] == "tests/*.fixture"

    def test_filters_out_invalid_entries(self):
        """Invalid entries (overly broad globs) are filtered out during load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            omg_dir = os.path.join(tmpdir, ".omg")
            os.makedirs(omg_dir)
            policy_path = os.path.join(omg_dir, "policy.yaml")
            with open(policy_path, "w") as f:
                f.write(textwrap.dedent("""\
                    allowlist:
                      - path: "*"
                        tools:
                          - Read
                        reason: "too broad - should be filtered"
                      - path: ".env.test"
                        tools:
                          - Read
                        reason: "valid entry"
                """))
            result = load_allowlist(tmpdir)
            assert len(result) == 1
            assert result[0]["path"] == ".env.test"


# ---------------------------------------------------------------------------
# Integration: allowlist cannot override secret-file deny
# ---------------------------------------------------------------------------


class TestAllowlistDoesNotOverrideSecretDeny:
    """Integration test: secret files remain denied even when allowlisted."""

    def test_allowlisted_secret_path_stays_denied(self):
        """A denied file (.env.test) must stay denied even when allowlisted."""
        # Without allowlist: .env.test is denied
        decision_no_allowlist = evaluate_file_access("Read", ".env.test")
        assert decision_no_allowlist.action == "deny"

        # With allowlist: .env.test must still be denied
        allowlist = [
            {"path": ".env.test", "tools": ["Read"], "reason": "test env safe"},
        ]
        decision_with_allowlist = evaluate_file_access(
            "Read", ".env.test", allowlist=allowlist
        )
        assert decision_with_allowlist.action == "deny"
        assert "Allowlisted" not in decision_with_allowlist.reason

    def test_allowlist_does_not_override_for_wrong_tool(self):
        """Allowlist for Read does not override deny for Write."""
        allowlist = [
            {"path": ".env.test", "tools": ["Read"], "reason": "read only"},
        ]
        decision = evaluate_file_access("Write", ".env.test", allowlist=allowlist)
        assert decision.action == "deny"


# ---------------------------------------------------------------------------
# Stub for T21 audit logging
# ---------------------------------------------------------------------------


class TestLogAllowlistBypassStub:
    """Verify the logging stub exists for T21."""

    def test_stub_callable(self):
        """_log_allowlist_bypass is callable and doesn't raise."""
        # Should not raise
        _log_allowlist_bypass("/some/path", "Read", "test reason")

    def test_stub_returns_none(self):
        """Stub returns None (no-op for now)."""
        result = _log_allowlist_bypass("/path", "Read", "reason")
        assert result is None


# ---------------------------------------------------------------------------
# OVERLY_BROAD_GLOBS constant
# ---------------------------------------------------------------------------


class TestOverlyBroadGlobs:
    """Verify the set of rejected globs."""

    def test_contains_expected_patterns(self):
        """All documented overly broad patterns are in the set."""
        assert "*" in OVERLY_BROAD_GLOBS
        assert "**" in OVERLY_BROAD_GLOBS
        assert "**/*" in OVERLY_BROAD_GLOBS
