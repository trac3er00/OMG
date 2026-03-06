"""Tests for credential key expiry & rotation schedule (Task 22).

Tests:
1. check_expiry returns empty list for empty/no-credential project
2. check_expiry identifies expired credentials (expires_at in past)
3. check_expiry identifies expiring credentials (within 14 days)
4. check_expiry marks ok credentials correctly
5. get_active_key warns on expired key (stderr) but still returns key
6. add_credential with expires_at stores the field
7. get_rotation_schedule_days returns default 90
8. check_expiry handles missing expires_at gracefully
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "hooks"

# Ensure hooks dir importable
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project_dir() -> str:
    """Create a temp dir mimicking a project with .omg/state/."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".omg", "state"), exist_ok=True)
    return d


def _add_key_with_expiry(
    provider: str,
    key: str,
    passphrase: str,
    project_dir: str,
    expires_at: str | None = None,
    label: str | None = None,
) -> None:
    """Add a credential then patch expires_at into the store."""
    from credential_store import add_credential, load_store, save_store

    add_credential(
        provider=provider,
        key=key,
        passphrase=passphrase,
        label=label,
        project_dir=project_dir,
    )
    if expires_at is not None:
        store = load_store(passphrase, project_dir)
        keys = store["providers"][provider]["keys"]
        keys[-1]["expires_at"] = expires_at
        save_store(store, passphrase, project_dir)


# ---------------------------------------------------------------------------
# Test 1: check_expiry on empty project returns empty list
# ---------------------------------------------------------------------------

class TestCheckExpiryEmpty:
    def test_empty_project_returns_empty_list(self):
        from credential_store import check_expiry

        d = tempfile.mkdtemp()
        result = check_expiry(d)
        assert isinstance(result, list)
        assert result == []


# ---------------------------------------------------------------------------
# Test 2: check_expiry identifies expired credentials
# ---------------------------------------------------------------------------

class TestCheckExpiryExpired:
    def test_expired_credential_detected(self):
        from credential_store import check_expiry

        d = _make_project_dir()
        passphrase = "test-passphrase-secure"
        past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

        _add_key_with_expiry("openai", "sk-test-expired-key123", passphrase, d, expires_at=past)

        with patch.dict(os.environ, {"OMG_CREDENTIAL_PASSPHRASE": passphrase}):
            result = check_expiry(d)

        assert len(result) >= 1
        entry = result[0]
        assert entry["name"] == "openai"
        assert entry["status"] == "expired"
        assert entry["days_remaining"] < 0


# ---------------------------------------------------------------------------
# Test 3: check_expiry identifies expiring-soon credentials
# ---------------------------------------------------------------------------

class TestCheckExpiryExpiringSoon:
    def test_expiring_within_14_days(self):
        from credential_store import check_expiry

        d = _make_project_dir()
        passphrase = "test-passphrase-secure"
        soon = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        _add_key_with_expiry("anthropic", "sk-ant-expiring123", passphrase, d, expires_at=soon)

        with patch.dict(os.environ, {"OMG_CREDENTIAL_PASSPHRASE": passphrase}):
            result = check_expiry(d)

        assert len(result) >= 1
        entry = result[0]
        assert entry["name"] == "anthropic"
        assert entry["status"] == "expiring"
        assert 0 <= entry["days_remaining"] <= 14


# ---------------------------------------------------------------------------
# Test 4: check_expiry marks ok credentials correctly
# ---------------------------------------------------------------------------

class TestCheckExpiryOk:
    def test_ok_credential(self):
        from credential_store import check_expiry

        d = _make_project_dir()
        passphrase = "test-passphrase-secure"
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()

        _add_key_with_expiry("openai", "sk-test-ok-key456789", passphrase, d, expires_at=future)

        with patch.dict(os.environ, {"OMG_CREDENTIAL_PASSPHRASE": passphrase}):
            result = check_expiry(d)

        assert len(result) >= 1
        entry = result[0]
        assert entry["name"] == "openai"
        assert entry["status"] == "ok"
        assert entry["days_remaining"] > 14


# ---------------------------------------------------------------------------
# Test 5: get_active_key warns on expired key but still returns it
# ---------------------------------------------------------------------------

class TestGetActiveKeyExpiryWarning:
    def test_expired_key_returns_with_warning(self):
        from credential_store import get_active_key

        d = _make_project_dir()
        passphrase = "test-passphrase-secure"
        past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        _add_key_with_expiry("openai", "sk-test-expired-ret", passphrase, d, expires_at=past)

        with patch.dict(os.environ, {
            "OMG_CREDENTIAL_PASSPHRASE": passphrase,
            "OMG_MULTI_CREDENTIAL_ENABLED": "1",
        }):
            stderr_capture = io.StringIO()
            old_stderr = sys.stderr
            sys.stderr = stderr_capture
            try:
                key = get_active_key("openai", project_dir=d)
            finally:
                sys.stderr = old_stderr

        # Must still return the key (advisory only, never block)
        assert key == "sk-test-expired-ret"
        # Must warn on stderr
        warning = stderr_capture.getvalue()
        assert "expir" in warning.lower(), f"Expected expiry warning, got: {warning!r}"


# ---------------------------------------------------------------------------
# Test 6: add_credential with expires_at stores the field correctly
# ---------------------------------------------------------------------------

class TestAddCredentialExpiresAt:
    def test_expires_at_stored_in_metadata(self):
        from credential_store import add_credential, load_store

        d = _make_project_dir()
        passphrase = "test-passphrase-secure"
        exp = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

        add_credential(
            provider="anthropic",
            key="sk-ant-test12345678",
            passphrase=passphrase,
            project_dir=d,
            expires_at=exp,
        )

        store = load_store(passphrase, d)
        key_entry = store["providers"]["anthropic"]["keys"][0]
        assert key_entry.get("expires_at") == exp


# ---------------------------------------------------------------------------
# Test 7: get_rotation_schedule_days returns default 90
# ---------------------------------------------------------------------------

class TestRotationScheduleDays:
    def test_default_rotation_schedule(self):
        from credential_store import get_rotation_schedule_days

        # Without any config override, should return 90
        result = get_rotation_schedule_days()
        assert result == 90


# ---------------------------------------------------------------------------
# Test 8: check_expiry handles missing expires_at gracefully
# ---------------------------------------------------------------------------

class TestCheckExpiryNoExpiresAt:
    def test_credential_without_expires_at_skipped(self):
        from credential_store import check_expiry, add_credential

        d = _make_project_dir()
        passphrase = "test-passphrase-secure"

        # Add credential WITHOUT expires_at
        add_credential(
            provider="openai",
            key="sk-test-noexpiry1234",
            passphrase=passphrase,
            project_dir=d,
        )

        with patch.dict(os.environ, {"OMG_CREDENTIAL_PASSPHRASE": passphrase}):
            result = check_expiry(d)

        # Credentials without expires_at should not appear in expiry report
        assert isinstance(result, list)
        assert len(result) == 0
