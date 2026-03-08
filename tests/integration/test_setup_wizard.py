"""Integration tests for hooks/setup_wizard.py — full pipeline tests.

Tests the complete setup wizard flow: detect CLIs -> auth -> configure MCP -> preferences.
Uses mocked providers (no real CLI installations) but real file I/O for config output.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

# Add hooks and project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "hooks"))
sys.path.insert(0, str(_PROJECT_ROOT))

from hooks import _common
import runtime.cli_provider
from hooks import setup_wizard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_provider(
    name: str,
    detected: bool = True,
    auth_ok: bool | None = True,
    auth_msg: str = "ok",
) -> Mock:
    """Create a mock CLIProvider with given detect/auth behaviour."""
    p = Mock()
    p.get_name.return_value = name
    p.detect.return_value = detected
    p.check_auth.return_value = (auth_ok, auth_msg)
    return p


@pytest.fixture(autouse=True)
def _clear_feature_cache():
    """Clear feature flag cache before and after each test."""
    _common._FEATURE_CACHE.clear()
    yield
    _common._FEATURE_CACHE.clear()


@pytest.fixture()
def _patch_cli_writers():
    """Mock all non-Claude MCP config writers (they write to HOME dirs)."""
    with patch("hooks.setup_wizard.write_codex_mcp_config"), \
         patch("hooks.setup_wizard.write_codex_mcp_stdio_config"), \
         patch("hooks.setup_wizard.write_gemini_mcp_config"), \
         patch("hooks.setup_wizard.write_gemini_mcp_stdio_config"), \
         patch("hooks.setup_wizard.write_kimi_mcp_stdio_config"), \
         patch("hooks.setup_wizard.write_kimi_mcp_config"):
        yield


# ---------------------------------------------------------------------------
# 1. Full wizard flow
# ---------------------------------------------------------------------------

class TestFullWizardFlow:
    """Integration: full wizard detect -> auth -> configure -> preferences."""

    def test_full_wizard_flow(self, tmp_path, monkeypatch, _patch_cli_writers):
        """Full wizard produces status=complete with all pipeline keys."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        providers = {
            "codex": _mock_provider("codex", detected=True, auth_ok=True),
            "gemini": _mock_provider("gemini", detected=False),
        }

        with patch.dict(
            runtime.cli_provider._PROVIDER_REGISTRY, providers, clear=True,
        ):
            result = setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        assert result["status"] == "complete"
        assert "clis_detected" in result
        assert "mcp_configured" in result
        assert "preferences" in result
        assert "auth_status" in result
        assert "adoption" in result

    def test_wizard_creates_output_files(self, tmp_path, monkeypatch, _patch_cli_writers):
        """Full wizard creates .mcp.json and cli-config.yaml on disk."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        with patch.dict(
            runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True,
        ):
            setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        # Claude MCP config written by the real writer
        assert (tmp_path / ".mcp.json").exists()

        # Preferences YAML written by the real writer
        assert (tmp_path / ".omg" / "state" / "cli-config.yaml").exists()
        assert (tmp_path / ".omg" / "state" / "adoption-report.json").exists()


# ---------------------------------------------------------------------------
# 2. CLI detection integration
# ---------------------------------------------------------------------------

class TestDetectClisIntegration:
    """Integration: detect_clis with mocked providers, verify output shape."""

    def test_detect_clis_returns_all_providers(self):
        """detect_clis returns an entry for every registered provider."""
        providers = {
            "codex": _mock_provider("codex", detected=True, auth_ok=True),
            "gemini": _mock_provider("gemini", detected=True, auth_ok=True),
            "kimi": _mock_provider("kimi", detected=True, auth_ok=False, auth_msg="no token"),
        }

        with patch.dict(
            runtime.cli_provider._PROVIDER_REGISTRY, providers, clear=True,
        ):
            result = setup_wizard.detect_clis()

        assert isinstance(result, dict)
        assert len(result) == 3
        assert "opencode" not in result
        for cli_name in result:
            assert "detected" in result[cli_name]
            assert "auth_ok" in result[cli_name]
            assert "message" in result[cli_name]

    def test_detect_clis_correct_per_provider_values(self):
        """detect_clis reports correct detected/auth values per provider."""
        providers = {
            "codex": _mock_provider("codex", detected=True, auth_ok=True, auth_msg="ready"),
            "gemini": _mock_provider("gemini", detected=False),
        }

        with patch.dict(
            runtime.cli_provider._PROVIDER_REGISTRY, providers, clear=True,
        ):
            result = setup_wizard.detect_clis()

        assert result["codex"]["detected"] is True
        assert result["codex"]["auth_ok"] is True
        assert result["gemini"]["detected"] is False
        # Not detected -> auth is never checked -> auth_ok stays None
        assert result["gemini"]["auth_ok"] is None


# ---------------------------------------------------------------------------
# 3. MCP config writing integration
# ---------------------------------------------------------------------------

class TestConfigureMcpIntegration:
    """Integration: configure_mcp writes real Claude config, mocks others."""

    def test_configure_mcp_writes_claude_config(self, tmp_path, _patch_cli_writers):
        """configure_mcp writes .mcp.json with mcpServers entry."""
        detected = {"codex": {"detected": True, "auth_ok": True}}

        result = setup_wizard.configure_mcp(str(tmp_path), detected)

        assert result["status"] == "ok"
        assert "codex" in result["configured"]

        # Verify .mcp.json was written by the real Claude writer
        mcp_json = tmp_path / ".mcp.json"
        assert mcp_json.exists()
        data = json.loads(mcp_json.read_text())
        assert "mcpServers" in data
        assert "omg-memory" not in data["mcpServers"]
        assert "omg-control" in data["mcpServers"]

    def test_configure_mcp_claude_content_correct(self, tmp_path, _patch_cli_writers):
        """Claude .mcp.json has correct server type and URL."""
        setup_wizard.configure_mcp(
            str(tmp_path),
            {},
            server_url="http://127.0.0.1:8765/mcp",
            server_name="omg-memory",
            preset="interop",
        )

        mcp_json = tmp_path / ".mcp.json"
        data = json.loads(mcp_json.read_text())
        server_cfg = data["mcpServers"]["omg-memory"]
        assert server_cfg["type"] == "http"
        assert server_cfg["url"] == "http://127.0.0.1:8765/mcp"

    def test_configure_mcp_skips_undetected(self, tmp_path):
        """configure_mcp skips config writer for undetected CLIs."""
        detected = {
            "codex": {"detected": False, "auth_ok": None},
            "gemini": {"detected": True, "auth_ok": True},
        }

        with patch("hooks.setup_wizard.write_codex_mcp_config") as mock_codex, \
             patch("hooks.setup_wizard.write_codex_mcp_stdio_config"), \
             patch("hooks.setup_wizard.write_gemini_mcp_config") as mock_gemini, \
             patch("hooks.setup_wizard.write_gemini_mcp_stdio_config") as mock_gemini_stdio, \
             patch("hooks.setup_wizard.write_kimi_mcp_stdio_config"), \
             patch("hooks.setup_wizard.write_kimi_mcp_config"), \
             patch("hooks.setup_wizard.write_claude_mcp_config"):
            result = setup_wizard.configure_mcp(str(tmp_path), detected)

        assert "codex" not in result["configured"]
        assert "gemini" in result["configured"]
        mock_codex.assert_not_called()
        mock_gemini.assert_not_called()
        written_server_names = [call.kwargs["server_name"] for call in mock_gemini_stdio.call_args_list]
        assert written_server_names == ["filesystem", "omg-control"]

    def test_configure_mcp_persists_selected_mcp_preferences(self, tmp_path, monkeypatch, _patch_cli_writers):
        """Selected MCPs should be persisted in the saved preferences."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                preset="safe",
                selected_mcps=["filesystem", "context7", "grep_app", "websearch"],
            )

        data = yaml.safe_load((tmp_path / ".omg" / "state" / "cli-config.yaml").read_text())
        assert result["preferences"]["config"]["selected_mcps"] == ["filesystem", "context7", "grep-app", "websearch"]
        assert data["selected_mcps"] == ["filesystem", "context7", "grep-app", "websearch"]

    def test_run_setup_wizard_persists_browser_capability(self, tmp_path, monkeypatch, _patch_cli_writers):
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                preset="safe",
                browser_enabled=True,
            )

        data = yaml.safe_load((tmp_path / ".omg" / "state" / "cli-config.yaml").read_text())
        assert result["preferences"]["config"]["browser_capability"]["enabled"] is True
        assert data["browser_capability"]["enabled"] is True


# ---------------------------------------------------------------------------
# 4. Preferences writing integration
# ---------------------------------------------------------------------------

class TestSetPreferencesIntegration:
    """Integration: set_preferences creates YAML on disk."""

    def test_set_preferences_creates_yaml(self, tmp_path):
        """set_preferences creates valid YAML at correct path."""
        result = setup_wizard.set_preferences(str(tmp_path), {})

        assert result["status"] == "ok"

        config_file = tmp_path / ".omg" / "state" / "cli-config.yaml"
        assert config_file.exists()

        data = yaml.safe_load(config_file.read_text())
        assert data["version"] == "2.0.9"
        assert "cli_configs" in data
        assert len(data["cli_configs"]) == 3
        assert "opencode" not in data["cli_configs"]

    def test_set_preferences_merges_custom_prefs(self, tmp_path):
        """Custom preferences override defaults while preserving others."""
        custom = {"cli_configs": {"codex": {"subscription": "pro", "max_parallel_agents": 5}}}
        result = setup_wizard.set_preferences(str(tmp_path), custom)

        assert result["status"] == "ok"

        config_file = tmp_path / ".omg" / "state" / "cli-config.yaml"
        data = yaml.safe_load(config_file.read_text())
        assert data["cli_configs"]["codex"]["subscription"] == "pro"
        assert data["cli_configs"]["codex"]["max_parallel_agents"] == 5
        # Other CLIs keep defaults
        assert data["cli_configs"]["gemini"]["subscription"] == "free"
        assert "opencode" not in data["cli_configs"]
        assert data["preset"] == "safe"


# ---------------------------------------------------------------------------
# 5. Wizard disabled by default
# ---------------------------------------------------------------------------

class TestWizardDisabledByDefault:
    """Integration: wizard disabled when OMG_SETUP_ENABLED is not set."""

    def test_wizard_disabled_by_default(self, monkeypatch):
        """Wizard returns disabled status when feature flag is off."""
        monkeypatch.delenv("OMG_SETUP_ENABLED", raising=False)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/tmp/omg-disabled-feature-test")
        _common._FEATURE_CACHE.clear()

        result = setup_wizard.run_setup_wizard(project_dir="/tmp/omg-disabled-feature-test")

        assert result["status"] == "disabled"
        assert "OMG_SETUP_ENABLED" in result["message"]


# ---------------------------------------------------------------------------
# 6. Non-interactive mode
# ---------------------------------------------------------------------------

class TestWizardNonInteractiveMode:
    """Integration: wizard runs in non-interactive mode without prompts."""

    def test_wizard_non_interactive_mode(self, tmp_path, monkeypatch, _patch_cli_writers):
        """Wizard in non_interactive mode completes successfully."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        with patch.dict(
            runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True,
        ):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path), non_interactive=True,
            )

        assert result["status"] == "complete"
        assert result["adoption"]["selected_mode"] == "omg-only"
        assert result["preferences"]["config"]["preset"] == "balanced"
        assert result["setup_mode"]["selected"] == "focused"


# ---------------------------------------------------------------------------
# 7. configure_mcp skips undetected CLIs
#    (covered above in TestConfigureMcpIntegration.test_configure_mcp_skips_undetected)
#    Adding an extra variant here for completeness.
# ---------------------------------------------------------------------------

class TestConfigureMcpSkipsUndetected:
    """Integration: configure_mcp only writes configs for detected CLIs."""

    def test_configure_mcp_only_detected_in_configured_list(self, tmp_path, _patch_cli_writers):
        """Only detected CLIs appear in the 'configured' result list."""
        detected = {
            "codex": {"detected": False, "auth_ok": None},
            "gemini": {"detected": True, "auth_ok": True},
            "kimi": {"detected": True, "auth_ok": True},
        }

        result = setup_wizard.configure_mcp(str(tmp_path), detected)

        assert "codex" not in result["configured"]
        assert "gemini" in result["configured"]
        assert "kimi" in result["configured"]


# ---------------------------------------------------------------------------
# 8. Full pipeline: detect -> configure -> preferences
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """Integration: detect -> configure -> preferences in one pass."""

    def test_full_pipeline_integration(self, tmp_path, monkeypatch, _patch_cli_writers):
        """Full pipeline: detect all -> configure MCP -> write preferences."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        providers = {
            "codex": _mock_provider("codex", detected=True, auth_ok=True),
            "gemini": _mock_provider("gemini", detected=True, auth_ok=True),
            "kimi": _mock_provider("kimi", detected=True, auth_ok=True),
        }

        with patch.dict(
            runtime.cli_provider._PROVIDER_REGISTRY, providers, clear=True,
        ):
            result = setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        # Verify pipeline completed
        assert result["status"] == "complete"

        # Verify all detected providers are present
        clis = result["clis_detected"]
        assert all(
            clis[name]["detected"]
            for name in ["codex", "gemini", "kimi"]
        )

        # Verify MCP configured for all detected CLIs
        assert result["mcp_configured"]["status"] == "ok"
        configured = result["mcp_configured"]["configured"]
        assert "codex" in configured
        assert "gemini" in configured
        assert "kimi" in configured

        # Verify Claude .mcp.json exists on disk
        mcp_json = tmp_path / ".mcp.json"
        assert mcp_json.exists()
        mcp_data = json.loads(mcp_json.read_text())
        assert "mcpServers" in mcp_data

        # Verify preferences YAML exists on disk
        config_yaml = tmp_path / ".omg" / "state" / "cli-config.yaml"
        assert config_yaml.exists()
        prefs_data = yaml.safe_load(config_yaml.read_text())
        assert prefs_data["version"] == "2.0.9"
        assert len(prefs_data["cli_configs"]) == 3
        assert "opencode" not in prefs_data["cli_configs"]

    def test_wizard_detects_existing_ecosystems_and_writes_adoption_report(
        self,
        tmp_path,
        monkeypatch,
        _patch_cli_writers,
    ):
        """Wizard should record detected OMG-adjacent ecosystems in the adoption report."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        (tmp_path / ".omc").mkdir()
        (tmp_path / ".omx").mkdir()
        (tmp_path / ".claude" / "skills" / "brainstorming").mkdir(parents=True)

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                non_interactive=True,
            )

        assert result["status"] == "complete"
        assert result["adoption"]["detected_ecosystems"] == ["omc", "omx", "superpowers"]
        assert result["adoption"]["recommended_mode"] == "omg-only"
        assert result["adoption"]["selected_mode"] == "omg-only"

        adoption_report = json.loads(
            (tmp_path / ".omg" / "state" / "adoption-report.json").read_text(encoding="utf-8")
        )
        assert adoption_report["detected_ecosystems"] == ["omc", "omx", "superpowers"]
        assert adoption_report["selected_mode"] == "omg-only"
