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

from runtime.adoption import CANONICAL_VERSION

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
        assert data["version"] == CANONICAL_VERSION
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
        assert prefs_data["version"] == CANONICAL_VERSION
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


# ---------------------------------------------------------------------------
# Post-install validation
# ---------------------------------------------------------------------------

class TestPostInstallValidation:
    """Integration: post-install validation runs at end of wizard flow."""

    def test_wizard_includes_post_install_validation_on_success(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """Successful wizard includes post_install_validation with pass status."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "pass",
            "checks": [
                {"name": "python_version", "status": "ok", "message": "Python 3.12", "required": True},
            ],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        assert result["status"] == "complete"
        assert "post_install_validation" in result
        piv = result["post_install_validation"]
        assert piv["status"] == "pass"
        assert piv["artifact_path"]
        assert piv["blockers"] == []

    def test_wizard_fails_on_validation_blockers(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """Wizard returns validation_failed when post-install validation has blockers."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "fail",
            "checks": [
                {"name": "python_version", "status": "ok", "message": "ok", "required": True},
                {"name": "install_integrity", "status": "blocker",
                 "message": "scripts/omg.py missing", "required": True},
            ],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        assert result["status"] == "validation_failed"
        piv = result["post_install_validation"]
        assert piv["status"] == "fail"
        assert len(piv["blockers"]) == 1
        assert piv["blockers"][0]["name"] == "install_integrity"
        assert "omg.py" in piv["blockers"][0]["message"]

    def test_wizard_persists_validation_artifact_to_disk(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """Post-install validation writes a machine-readable artifact file."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "pass",
            "checks": [],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        artifact = Path(result["post_install_validation"]["artifact_path"])
        assert artifact.exists()
        data = json.loads(artifact.read_text())
        assert data["schema"] == "ValidateResult"
        assert data["status"] == "pass"

    def test_wizard_optional_warnings_do_not_fail_install(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """Optional check warnings (e.g., NotebookLM) must not fail the core install."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "pass",
            "checks": [
                {"name": "python_version", "status": "ok", "message": "ok", "required": True},
                {"name": "notebooklm", "status": "warning",
                 "message": "not configured", "required": False},
            ],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(project_dir=str(tmp_path))

        assert result["status"] == "complete"
        assert result["post_install_validation"]["status"] == "pass"
        assert result["post_install_validation"]["blockers"] == []

    def test_notebooklm_is_selectable_but_not_preset_enabled(self, tmp_path, monkeypatch, _patch_cli_writers):
        """NotebookLM should be selectable but never auto-included by any preset."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        # Verify NotebookLM is in the catalog
        catalog = setup_wizard.get_mcp_catalog()
        notebooklm_entry = next((m for m in catalog if m["id"] == "notebooklm"), None)
        assert notebooklm_entry is not None, "NotebookLM must be in MCP catalog"
        
        # Verify NotebookLM has no min_preset (opt-in only)
        assert "min_preset" not in notebooklm_entry or notebooklm_entry.get("min_preset") is None, \
            "NotebookLM must not have min_preset (opt-in only)"

        # Verify NotebookLM is NOT in any preset's defaults
        for preset in setup_wizard.PRESET_ORDER:
            defaults = setup_wizard.get_default_mcps_for_preset(preset)
            assert "notebooklm" not in defaults, \
                f"NotebookLM must not be in {preset} preset defaults"

        # Verify NotebookLM can be explicitly selected
        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                preset="safe",
                selected_mcps=["filesystem", "notebooklm"],
            )

        data = yaml.safe_load((tmp_path / ".omg" / "state" / "cli-config.yaml").read_text())
        assert "notebooklm" in result["preferences"]["config"]["selected_mcps"]
        assert "notebooklm" in data["selected_mcps"]

    def test_notebooklm_selection_shows_warning_text(self, tmp_path, monkeypatch, _patch_cli_writers):
        """NotebookLM selection must include warning text about browser automation, download size, account, and auth expiry."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        catalog = setup_wizard.get_mcp_catalog()
        notebooklm_entry = next((m for m in catalog if m["id"] == "notebooklm"), None)
        assert notebooklm_entry is not None, "NotebookLM must be in MCP catalog"

        # Verify warning text is present in the entry
        warning_text = notebooklm_entry.get("warning", "")
        assert "browser automation" in warning_text.lower(), \
            "Warning must mention browser automation"
        assert "download" in warning_text.lower() or "size" in warning_text.lower(), \
            "Warning must mention download size"
        assert "account" in warning_text.lower() or "dedicated" in warning_text.lower(), \
            "Warning must mention dedicated account guidance"
        assert "auth" in warning_text.lower() or "expiry" in warning_text.lower(), \
            "Warning must mention auth expiry"


# ---------------------------------------------------------------------------
# NotebookLM health check integration
# ---------------------------------------------------------------------------

class TestNotebookLMHealthCheck:
    """Integration: NotebookLM validation in health/reporting surfaces."""

    def test_notebooklm_health_check_runs_when_selected(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """When NotebookLM is in selected MCPs, validate must include its health check."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "pass",
            "checks": [
                {"name": "python_version", "status": "ok", "message": "ok", "required": True},
                {"name": "notebooklm", "status": "ok",
                 "message": "npx available, notebooklm-mcp callable", "required": False},
            ],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                preset="safe",
                selected_mcps=["filesystem", "notebooklm"],
            )

        assert result["status"] == "complete"
        piv = result["post_install_validation"]
        assert piv["status"] == "pass"
        assert piv["blockers"] == []

    def test_notebooklm_health_warning_does_not_block_install(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """NotebookLM warning (missing Node/npx) must not block setup wizard completion."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "pass",
            "checks": [
                {"name": "python_version", "status": "ok", "message": "ok", "required": True},
                {"name": "notebooklm", "status": "warning",
                 "message": "npx not found — install Node.js to use NotebookLM",
                 "required": False},
            ],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                preset="safe",
                selected_mcps=["filesystem", "notebooklm"],
            )

        assert result["status"] == "complete"
        piv = result["post_install_validation"]
        assert piv["status"] == "pass"
        assert piv["blockers"] == []

    def test_notebooklm_check_not_run_when_unselected(
        self, tmp_path, monkeypatch, _patch_cli_writers,
    ):
        """When NotebookLM is NOT in selected MCPs, validate must NOT include it."""
        monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

        mock_result = {
            "schema": "ValidateResult",
            "status": "pass",
            "checks": [
                {"name": "python_version", "status": "ok", "message": "ok", "required": True},
            ],
            "version": CANONICAL_VERSION,
        }

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True), \
             patch("hooks.setup_wizard._run_post_install_validate", return_value=mock_result):
            result = setup_wizard.run_setup_wizard(
                project_dir=str(tmp_path),
                preset="safe",
                selected_mcps=["filesystem"],
            )

        assert result["status"] == "complete"
        piv = result["post_install_validation"]
        check_names = [
            b["name"] for b in piv.get("blockers", [])
        ]
        assert "notebooklm" not in check_names
