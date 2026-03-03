"""Tests for round-robin credential distribution in team_router.py (Task 1.9)."""
from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure imports work
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HOOKS_DIR = os.path.join(_ROOT, "hooks")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from runtime.team_router import _fnv1a_hash, get_active_credential, on_rate_limit


def _make_store(provider="openai", num_keys=3, active_index=0):
    """Helper to create a fake credential store dict."""
    keys = []
    for i in range(num_keys):
        keys.append({
            "key": f"sk-test-key-{i}",
            "label": f"key-{i}",
            "added": "2026-01-01T00:00:00+00:00",
            "last_used": None,
            "usage_count": 0,
        })
    return {
        "version": 1,
        "providers": {
            provider: {
                "keys": keys,
                "active_index": active_index,
                "rotation_policy": "round-robin",
            }
        },
    }


# =============================================================================
# FNV-1a Hash Tests
# =============================================================================


class TestFnv1aHash:
    """Tests for FNV-1a 32-bit hash function."""

    def test_deterministic_same_input(self):
        """Same input always produces same hash."""
        assert _fnv1a_hash("session-abc") == _fnv1a_hash("session-abc")

    def test_different_inputs_differ(self):
        """Different inputs produce different hashes."""
        assert _fnv1a_hash("session-1") != _fnv1a_hash("session-2")

    def test_returns_int(self):
        """Hash returns an integer."""
        assert isinstance(_fnv1a_hash("test"), int)

    def test_32bit_range(self):
        """Hash stays within 32-bit unsigned range."""
        for data in ["a", "hello", "session-12345", "", "x" * 1000]:
            h = _fnv1a_hash(data)
            assert 0 <= h <= 0xFFFFFFFF

    def test_empty_string(self):
        """Empty string produces a valid hash (the FNV offset basis)."""
        h = _fnv1a_hash("")
        assert h == 2166136261  # FNV-1a offset basis for 32-bit


# =============================================================================
# get_active_credential Tests
# =============================================================================


class TestGetActiveCredential:
    """Tests for get_active_credential()."""

    @patch.dict(os.environ, {"OAL_ROUND_ROBIN_ENABLED": "0"}, clear=False)
    def test_feature_flag_disabled_returns_none(self):
        """Returns None when ROUND_ROBIN flag is disabled."""
        result = get_active_credential("openai")
        assert result is None

    @patch.dict(os.environ, {"OAL_ROUND_ROBIN_ENABLED": "1"}, clear=False)
    def test_no_passphrase_returns_none(self):
        """Returns None when OAL_CREDENTIAL_PASSPHRASE is not set."""
        os.environ.pop("OAL_CREDENTIAL_PASSPHRASE", None)
        result = get_active_credential("openai")
        assert result is None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_returns_active_key(self, mock_load, mock_save):
        """Returns the active key for the provider."""
        mock_load.return_value = _make_store("openai", num_keys=3, active_index=0)
        result = get_active_credential("openai")
        assert result == "sk-test-key-0"

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_increments_usage_count(self, mock_load, mock_save):
        """Increments usage_count on the selected key."""
        store = _make_store("openai", num_keys=3, active_index=0)
        mock_load.return_value = store
        get_active_credential("openai")

        assert mock_save.called
        saved_store = mock_save.call_args[0][0]
        assert saved_store["providers"]["openai"]["keys"][0]["usage_count"] == 1
        assert saved_store["providers"]["openai"]["keys"][0]["last_used"] is not None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_advances_index_without_session(self, mock_load, mock_save):
        """Advances active_index for next call when no session_id."""
        store = _make_store("openai", num_keys=3, active_index=0)
        mock_load.return_value = store
        get_active_credential("openai")

        saved_store = mock_save.call_args[0][0]
        assert saved_store["providers"]["openai"]["active_index"] == 1

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_wraps_around_at_end(self, mock_load, mock_save):
        """Index wraps around to 0 when at last key."""
        store = _make_store("openai", num_keys=3, active_index=2)
        mock_load.return_value = store
        result = get_active_credential("openai")
        assert result == "sk-test-key-2"

        saved_store = mock_save.call_args[0][0]
        assert saved_store["providers"]["openai"]["active_index"] == 0

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_session_id_deterministic(self, mock_load, mock_save):
        """Session ID produces deterministic key selection via FNV-1a."""
        store1 = _make_store("openai", num_keys=3)
        store2 = _make_store("openai", num_keys=3)

        mock_load.return_value = store1
        r1 = get_active_credential("openai", session_id="stable-session-42")

        mock_load.return_value = store2
        r2 = get_active_credential("openai", session_id="stable-session-42")

        assert r1 == r2
        assert r1 is not None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_session_id_does_not_advance_index(self, mock_load, mock_save):
        """Session-based selection does not advance active_index."""
        store = _make_store("openai", num_keys=3, active_index=0)
        mock_load.return_value = store
        get_active_credential("openai", session_id="my-session")

        saved_store = mock_save.call_args[0][0]
        # active_index should remain 0 (session-based doesn't advance)
        assert saved_store["providers"]["openai"]["active_index"] == 0

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_unknown_provider_returns_none(self, mock_load, mock_save):
        """Returns None for unknown provider."""
        mock_load.return_value = _make_store("openai")
        result = get_active_credential("anthropic")
        assert result is None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.load_store", side_effect=ValueError("bad passphrase"))
    def test_store_load_error_returns_none(self, mock_load):
        """Returns None gracefully when store fails to load."""
        result = get_active_credential("openai")
        assert result is None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_empty_store_returns_none(self, mock_load, mock_save):
        """Returns None when store has no providers."""
        mock_load.return_value = {"version": 1, "providers": {}}
        result = get_active_credential("openai")
        assert result is None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_clamped_invalid_active_index(self, mock_load, mock_save):
        """Clamps invalid active_index to 0."""
        store = _make_store("openai", num_keys=3, active_index=99)
        mock_load.return_value = store
        result = get_active_credential("openai")
        assert result == "sk-test-key-0"


# =============================================================================
# on_rate_limit Tests
# =============================================================================


class TestOnRateLimit:
    """Tests for on_rate_limit()."""

    @patch.dict(os.environ, {"OAL_ROUND_ROBIN_ENABLED": "0"}, clear=False)
    def test_disabled_returns_none(self):
        """Returns None when ROUND_ROBIN flag is disabled."""
        assert on_rate_limit("openai") is None

    @patch.dict(os.environ, {"OAL_ROUND_ROBIN_ENABLED": "1"}, clear=False)
    def test_no_passphrase_returns_none(self):
        """Returns None when passphrase not set."""
        os.environ.pop("OAL_CREDENTIAL_PASSPHRASE", None)
        assert on_rate_limit("openai") is None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_advances_to_next_key(self, mock_load, mock_save):
        """Advances to next key and returns it."""
        mock_load.return_value = _make_store("openai", num_keys=3, active_index=0)
        result = on_rate_limit("openai")
        assert result == "sk-test-key-1"

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_wraps_around(self, mock_load, mock_save):
        """Wraps around to key 0 when at last key."""
        mock_load.return_value = _make_store("openai", num_keys=3, active_index=2)
        result = on_rate_limit("openai")
        assert result == "sk-test-key-0"

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_updates_active_index_in_store(self, mock_load, mock_save):
        """Updates active_index in saved store."""
        mock_load.return_value = _make_store("openai", num_keys=3, active_index=1)
        on_rate_limit("openai")

        saved_store = mock_save.call_args[0][0]
        assert saved_store["providers"]["openai"]["active_index"] == 2

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.load_store", side_effect=OSError("no store"))
    def test_store_error_returns_none(self, mock_load):
        """Returns None gracefully on store errors."""
        assert on_rate_limit("openai") is None

    @patch.dict(os.environ, {
        "OAL_ROUND_ROBIN_ENABLED": "1",
        "OAL_CREDENTIAL_PASSPHRASE": "test-pass",
    }, clear=False)
    @patch("credential_store.save_store")
    @patch("credential_store.load_store")
    def test_unknown_provider_returns_none(self, mock_load, mock_save):
        """Returns None for unknown provider."""
        mock_load.return_value = _make_store("openai")
        assert on_rate_limit("anthropic") is None
