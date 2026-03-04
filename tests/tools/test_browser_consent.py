#!/usr/bin/env python3
"""
Tests for tools/browser_consent.py

Tests ConsentManager lifecycle: show_warning, record_consent, is_consented,
revoke_consent, get_consent_status, CLI, and edge cases.
"""

import json
import os
import sys
import subprocess

import pytest

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from browser_consent import (
    CONSENT_VERSION,
    ConsentManager,
    is_consented,
    _WARNING_TEXT,
)


# --- Fixtures ---


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temp project dir with .omg/state/ structure."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def manager(tmp_project):
    """ConsentManager with a fresh temp project directory."""
    return ConsentManager(project_dir=str(tmp_project))


@pytest.fixture
def consented_manager(tmp_project):
    """ConsentManager with consent already granted."""
    consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
    consent_path.write_text(json.dumps({
        "consented": True,
        "acknowledged_at": "2025-01-01T00:00:00+00:00",
        "version": "1.0",
    }))
    return ConsentManager(project_dir=str(tmp_project))


# =============================================================================
# TestShowWarning — warning text content
# =============================================================================


class TestShowWarning:
    """Tests for show_warning()."""

    def test_show_warning_returns_string(self, manager):
        """show_warning returns a non-empty string."""
        warning = manager.show_warning()
        assert isinstance(warning, str)
        assert len(warning) > 0

    def test_warning_contains_required_keywords(self, manager):
        """Warning text must contain: WARNING, Terms of Service, stealth, explicit consent."""
        warning = manager.show_warning()
        assert "WARNING" in warning
        assert "Terms of Service" in warning
        assert "stealth" in warning.lower()
        assert "explicit consent" in warning.lower()

    def test_show_warning_is_multiline(self, manager):
        """Warning text is multi-line."""
        warning = manager.show_warning()
        assert "\n" in warning
        assert len(warning.splitlines()) > 5


# =============================================================================
# TestRecordConsent — consent recording
# =============================================================================


class TestRecordConsent:
    """Tests for record_consent()."""

    def test_record_consent_creates_file(self, manager, tmp_project):
        """record_consent creates the consent file."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        assert not consent_path.exists()

        result = manager.record_consent(acknowledged=True)

        assert result is True
        assert consent_path.exists()

    def test_record_consent_writes_correct_data(self, manager, tmp_project):
        """record_consent writes consented, acknowledged_at, and version."""
        manager.record_consent(acknowledged=True)

        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        data = json.loads(consent_path.read_text())

        assert data["consented"] is True
        assert "acknowledged_at" in data
        assert data["version"] == CONSENT_VERSION

    def test_record_consent_false(self, manager, tmp_project):
        """record_consent(acknowledged=False) writes consented: false."""
        manager.record_consent(acknowledged=False)

        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        data = json.loads(consent_path.read_text())

        assert data["consented"] is False


# =============================================================================
# TestIsConsented — consent checking
# =============================================================================


class TestIsConsented:
    """Tests for is_consented()."""

    def test_no_file_returns_false(self, manager):
        """is_consented returns False when consent file does not exist."""
        assert manager.is_consented() is False

    def test_consented_true_returns_true(self, consented_manager):
        """is_consented returns True when consented is True."""
        assert consented_manager.is_consented() is True

    def test_consented_false_returns_false(self, tmp_project):
        """is_consented returns False when consented is False."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({"consented": False}))
        mgr = ConsentManager(project_dir=str(tmp_project))
        assert mgr.is_consented() is False

    def test_malformed_json_returns_false(self, tmp_project):
        """is_consented returns False on malformed JSON."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text("{{{not valid json")
        mgr = ConsentManager(project_dir=str(tmp_project))
        assert mgr.is_consented() is False

    def test_empty_dict_returns_false(self, tmp_project):
        """is_consented returns False when consent file is empty dict."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({}))
        mgr = ConsentManager(project_dir=str(tmp_project))
        assert mgr.is_consented() is False

    def test_consented_string_true_returns_false(self, tmp_project):
        """is_consented returns False when consented is string 'true' (not bool)."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({"consented": "true"}))
        mgr = ConsentManager(project_dir=str(tmp_project))
        assert mgr.is_consented() is False


# =============================================================================
# TestRevokeConsent — consent revocation
# =============================================================================


class TestRevokeConsent:
    """Tests for revoke_consent()."""

    def test_revoke_consent_sets_false(self, consented_manager, tmp_project):
        """revoke_consent sets consented to False."""
        assert consented_manager.is_consented() is True

        result = consented_manager.revoke_consent()

        assert result is True
        assert consented_manager.is_consented() is False

    def test_revoke_consent_preserves_version(self, consented_manager, tmp_project):
        """revoke_consent writes version field."""
        consented_manager.revoke_consent()

        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        data = json.loads(consent_path.read_text())
        assert data["version"] == CONSENT_VERSION
        assert "acknowledged_at" in data


# =============================================================================
# TestGetConsentStatus — full consent record
# =============================================================================


class TestGetConsentStatus:
    """Tests for get_consent_status()."""

    def test_no_file_returns_default(self, manager):
        """get_consent_status returns {consented: False} when no file."""
        status = manager.get_consent_status()
        assert status == {"consented": False}

    def test_returns_full_record(self, consented_manager):
        """get_consent_status returns the full consent record."""
        status = consented_manager.get_consent_status()
        assert status["consented"] is True
        assert "acknowledged_at" in status
        assert "version" in status


# =============================================================================
# TestModuleLevelConvenience — is_consented() function
# =============================================================================


class TestModuleLevelConvenience:
    """Tests for the module-level is_consented() function."""

    def test_module_is_consented_false(self, tmp_project):
        """Module-level is_consented returns False when no consent."""
        assert is_consented(project_dir=str(tmp_project)) is False

    def test_module_is_consented_true(self, tmp_project):
        """Module-level is_consented returns True when consented."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({"consented": True}))
        assert is_consented(project_dir=str(tmp_project)) is True


# =============================================================================
# TestCLI — CLI entry point
# =============================================================================


class TestCLI:
    """Tests for CLI --status flag."""

    def test_cli_status_no_consent(self, tmp_project):
        """CLI --status outputs consent status JSON."""
        script = os.path.join(
            os.path.dirname(__file__), "..", "..", "tools", "browser_consent.py"
        )
        result = subprocess.run(
            [sys.executable, script, "--status", "--project-dir", str(tmp_project)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["consented"] is False

    def test_cli_status_with_consent(self, tmp_project):
        """CLI --status shows consented: true after granting."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({
            "consented": True,
            "acknowledged_at": "2025-01-01T00:00:00+00:00",
            "version": "1.0",
        }))
        script = os.path.join(
            os.path.dirname(__file__), "..", "..", "tools", "browser_consent.py"
        )
        result = subprocess.run(
            [sys.executable, script, "--status", "--project-dir", str(tmp_project)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["consented"] is True
