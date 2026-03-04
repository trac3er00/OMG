#!/usr/bin/env python3
"""
Tests for tools/browser_stealth.py

Tests 14 stealth plugin definitions, StealthManager lifecycle
(get_plugins, get_plugin, apply_plugins, is_consented),
feature flag gating, and consent enforcement.
"""

import json
import os
import sys
import tempfile
from unittest.mock import patch

import pytest

# Enable both feature flags for tests
os.environ["OMG_BROWSER_ENABLED"] = "true"
os.environ["OMG_BROWSER_STEALTH_ENABLED"] = "true"

# Add tools directory to path
tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

import browser_stealth
from browser_stealth import STEALTH_PLUGINS, StealthManager, _PLUGIN_INDEX


# --- Fixtures ---

@pytest.fixture
def tmp_project(tmp_path):
    """Create a temp project dir with .omg/state/ structure."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def consented_project(tmp_project):
    """Project dir with consent granted."""
    consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
    consent_path.write_text(json.dumps({"consented": True}))
    return tmp_project


@pytest.fixture
def unconsented_project(tmp_project):
    """Project dir without consent (no consent file)."""
    return tmp_project


@pytest.fixture
def manager_consented(consented_project):
    """StealthManager with consent granted."""
    return StealthManager(project_dir=str(consented_project))


@pytest.fixture
def manager_unconsented(unconsented_project):
    """StealthManager without consent."""
    return StealthManager(project_dir=str(unconsented_project))


# A mock session object for apply_plugins
class _MockSession:
    session_id = "test123"
    current_url = "https://example.com"


@pytest.fixture
def mock_session():
    return _MockSession()


# =============================================================================
# TestPluginDefinitions — verify all 14 plugins exist with correct fields
# =============================================================================


class TestPluginDefinitions:
    """Verify 14 stealth plugin definitions."""

    def test_exactly_14_plugins_defined(self):
        """STEALTH_PLUGINS contains exactly 14 definitions."""
        assert len(STEALTH_PLUGINS) == 14

    def test_all_plugins_have_required_fields(self):
        """Each plugin has name, description, and js_snippet."""
        required = {"name", "description", "js_snippet"}
        for plugin in STEALTH_PLUGINS:
            assert required.issubset(plugin.keys()), (
                f"Plugin {plugin.get('name', '?')} missing fields: "
                f"{required - plugin.keys()}"
            )

    def test_all_plugin_names_unique(self):
        """All plugin names are unique."""
        names = [p["name"] for p in STEALTH_PLUGINS]
        assert len(names) == len(set(names))

    def test_plugin_index_matches(self):
        """_PLUGIN_INDEX has all 14 plugins keyed by name."""
        assert len(_PLUGIN_INDEX) == 14
        for plugin in STEALTH_PLUGINS:
            assert plugin["name"] in _PLUGIN_INDEX
            assert _PLUGIN_INDEX[plugin["name"]] is plugin

    @pytest.mark.parametrize("expected_name", [
        "toString_tampering",
        "webgl_fingerprint",
        "audio_context",
        "screen_dimensions",
        "font_enumeration",
        "plugin_mime_types",
        "hardware_concurrency",
        "codec_availability",
        "iframe_detection",
        "locale_spoofing",
        "worker_detection",
        "canvas_fingerprint",
        "battery_status",
        "media_devices",
    ])
    def test_specific_plugin_exists(self, expected_name):
        """Each of the 14 required plugins exists by name."""
        assert expected_name in _PLUGIN_INDEX
        plugin = _PLUGIN_INDEX[expected_name]
        assert isinstance(plugin["js_snippet"], str)
        assert len(plugin["js_snippet"]) > 10  # non-trivial snippet
        assert len(plugin["description"]) > 5


# =============================================================================
# TestStealthManagerGetPlugins — get_plugins and get_plugin
# =============================================================================


class TestStealthManagerGetPlugins:
    """Tests for get_plugins() and get_plugin()."""

    def test_get_plugins_returns_all_14(self, manager_consented):
        """get_plugins returns all 14 plugins when enabled."""
        plugins = manager_consented.get_plugins()
        assert len(plugins) == 14

    def test_get_plugins_returns_copies(self, manager_consented):
        """get_plugins returns a new list (not the module-level list)."""
        plugins = manager_consented.get_plugins()
        assert plugins is not STEALTH_PLUGINS

    def test_get_plugins_empty_when_disabled(self, manager_consented):
        """get_plugins returns empty list when stealth flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_STEALTH_ENABLED": "false"}):
            plugins = manager_consented.get_plugins()
            assert plugins == []

    def test_get_plugins_empty_when_browser_disabled(self, manager_consented):
        """get_plugins returns empty list when browser flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            plugins = manager_consented.get_plugins()
            assert plugins == []

    def test_get_plugin_by_name(self, manager_consented):
        """get_plugin returns correct plugin dict by name."""
        plugin = manager_consented.get_plugin("canvas_fingerprint")
        assert plugin is not None
        assert plugin["name"] == "canvas_fingerprint"
        assert "js_snippet" in plugin

    def test_get_plugin_nonexistent_returns_none(self, manager_consented):
        """get_plugin returns None for unknown plugin name."""
        plugin = manager_consented.get_plugin("nonexistent_plugin")
        assert plugin is None

    def test_get_plugin_none_when_disabled(self, manager_consented):
        """get_plugin returns None when stealth flag is disabled."""
        with patch.dict(os.environ, {"OMG_BROWSER_STEALTH_ENABLED": "false"}):
            plugin = manager_consented.get_plugin("canvas_fingerprint")
            assert plugin is None


# =============================================================================
# TestConsent — is_consented checks
# =============================================================================


class TestConsent:
    """Tests for consent checking."""

    def test_consented_returns_true(self, consented_project):
        """is_consented returns True when consent file has consented: true."""
        manager = StealthManager(project_dir=str(consented_project))
        assert manager.is_consented() is True

    def test_unconsented_returns_false(self, unconsented_project):
        """is_consented returns False when consent file is missing."""
        manager = StealthManager(project_dir=str(unconsented_project))
        assert manager.is_consented() is False

    def test_false_consent_returns_false(self, tmp_project):
        """is_consented returns False when consent file has consented: false."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({"consented": False}))
        manager = StealthManager(project_dir=str(tmp_project))
        assert manager.is_consented() is False

    def test_malformed_consent_returns_false(self, tmp_project):
        """is_consented returns False on malformed JSON."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text("not valid json {{{")
        manager = StealthManager(project_dir=str(tmp_project))
        assert manager.is_consented() is False

    def test_empty_consent_returns_false(self, tmp_project):
        """is_consented returns False when consent file is empty dict."""
        consent_path = tmp_project / ".omg" / "state" / "browser_consent.json"
        consent_path.write_text(json.dumps({}))
        manager = StealthManager(project_dir=str(tmp_project))
        assert manager.is_consented() is False


# =============================================================================
# TestApplyPlugins — plugin application with consent enforcement
# =============================================================================


class TestApplyPlugins:
    """Tests for apply_plugins()."""

    def test_apply_all_plugins_with_consent(self, manager_consented, mock_session):
        """apply_plugins applies all 14 plugins when consented."""
        result = manager_consented.apply_plugins(mock_session)
        assert result["success"] is True
        assert len(result["applied"]) == 14
        assert result["error"] is None
        assert result["requires_consent"] is False
        assert "snippets" in result
        assert len(result["snippets"]) == 14

    def test_apply_specific_plugins(self, manager_consented, mock_session):
        """apply_plugins applies only named plugins."""
        result = manager_consented.apply_plugins(
            mock_session, plugin_names=["canvas_fingerprint", "locale_spoofing"]
        )
        assert result["success"] is True
        assert result["applied"] == ["canvas_fingerprint", "locale_spoofing"]
        assert len(result["snippets"]) == 2

    def test_apply_fails_without_consent(self, manager_unconsented, mock_session):
        """apply_plugins fails with requires_consent=True when no consent."""
        result = manager_unconsented.apply_plugins(mock_session)
        assert result["success"] is False
        assert result["requires_consent"] is True
        assert "consent" in result["error"].lower()
        assert result["applied"] == []

    def test_apply_fails_when_disabled(self, manager_consented, mock_session):
        """apply_plugins returns disabled response when flag is off."""
        with patch.dict(os.environ, {"OMG_BROWSER_STEALTH_ENABLED": "false"}):
            result = manager_consented.apply_plugins(mock_session)
            assert result["success"] is False
            assert "disabled" in result["error"].lower()

    def test_apply_unknown_plugin_returns_error(self, manager_consented, mock_session):
        """apply_plugins returns error for unknown plugin name."""
        result = manager_consented.apply_plugins(
            mock_session, plugin_names=["nonexistent_plugin"]
        )
        assert result["success"] is False
        assert "Unknown plugin" in result["error"]

    def test_apply_empty_list_returns_empty(self, manager_consented, mock_session):
        """apply_plugins with empty list applies nothing."""
        result = manager_consented.apply_plugins(mock_session, plugin_names=[])
        assert result["success"] is True
        assert result["applied"] == []
        assert result["snippets"] == []

    def test_apply_preserves_snippet_content(self, manager_consented, mock_session):
        """apply_plugins returns actual JS snippets, not empty strings."""
        result = manager_consented.apply_plugins(
            mock_session, plugin_names=["hardware_concurrency"]
        )
        assert result["success"] is True
        assert len(result["snippets"]) == 1
        assert "hardwareConcurrency" in result["snippets"][0]


# =============================================================================
# TestFeatureFlagGating — double flag enforcement
# =============================================================================


class TestFeatureFlagGating:
    """Tests for dual feature flag requirement."""

    def test_stealth_requires_both_flags(self, manager_consented, mock_session):
        """Stealth requires both BROWSER_ENABLED and BROWSER_STEALTH_ENABLED."""
        # Both on → works
        result = manager_consented.apply_plugins(mock_session)
        assert result["success"] is True

    def test_browser_off_blocks_stealth(self, manager_consented, mock_session):
        """Disabling browser flag blocks stealth even with stealth flag on."""
        with patch.dict(os.environ, {"OMG_BROWSER_ENABLED": "false"}):
            result = manager_consented.apply_plugins(mock_session)
            assert result["success"] is False

    def test_stealth_off_blocks_apply(self, manager_consented, mock_session):
        """Disabling stealth flag blocks apply even with browser on."""
        with patch.dict(os.environ, {"OMG_BROWSER_STEALTH_ENABLED": "false"}):
            result = manager_consented.apply_plugins(mock_session)
            assert result["success"] is False
