"""Tests for hooks/setup_wizard.py — OMG setup wizard skeleton + CLI detection."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add hooks to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hooks"))


class TestIsSetupEnabled:
    """Tests for is_setup_enabled() feature flag."""

    def test_disabled_by_default(self):
        """Setup wizard should be disabled when no env var or settings are set."""
        import setup_wizard

        # Ensure env var is not set
        env = os.environ.copy()
        env.pop("OMG_SETUP_ENABLED", None)

        with patch.dict(os.environ, env, clear=True):
            # Clear feature flag cache
            import _common
            _common._FEATURE_CACHE.clear()

            result = setup_wizard.is_setup_enabled()
            assert result is False

    def test_enabled_via_env_var(self):
        """Setup wizard should be enabled when OMG_SETUP_ENABLED=1."""
        import setup_wizard
        import _common

        _common._FEATURE_CACHE.clear()

        with patch.dict(os.environ, {"OMG_SETUP_ENABLED": "1"}):
            result = setup_wizard.is_setup_enabled()
            assert result is True

    def test_disabled_via_env_var_zero(self):
        """Setup wizard should be disabled when OMG_SETUP_ENABLED=0."""
        import setup_wizard
        import _common

        _common._FEATURE_CACHE.clear()

        with patch.dict(os.environ, {"OMG_SETUP_ENABLED": "0"}):
            result = setup_wizard.is_setup_enabled()
            assert result is False


class TestRunSetupWizard:
    """Tests for run_setup_wizard() skeleton."""

    def test_returns_disabled_when_feature_off(self):
        """Wizard should return disabled status when feature flag is off."""
        import setup_wizard
        import _common

        _common._FEATURE_CACHE.clear()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OMG_SETUP_ENABLED", None)

            with tempfile.TemporaryDirectory() as tmpdir:
                result = setup_wizard.run_setup_wizard(tmpdir)

            assert result["status"] == "disabled"
            assert "OMG_SETUP_ENABLED" in result["message"]

    def test_returns_dict_with_expected_keys_when_enabled(self):
        """Wizard should return dict with all expected step keys."""
        import setup_wizard
        import _common

        _common._FEATURE_CACHE.clear()

        with patch.dict(os.environ, {"OMG_SETUP_ENABLED": "1"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = setup_wizard.run_setup_wizard(tmpdir)

        assert isinstance(result, dict)
        assert "status" in result
        assert "clis_detected" in result
        assert "auth_status" in result
        assert "mcp_configured" in result
        assert "preferences" in result
        assert "adoption" in result

    def test_non_interactive_mode(self):
        """Wizard should accept non_interactive flag."""
        import setup_wizard
        import _common

        _common._FEATURE_CACHE.clear()

        with patch.dict(os.environ, {"OMG_SETUP_ENABLED": "1"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = setup_wizard.run_setup_wizard(tmpdir, non_interactive=True)

        assert isinstance(result, dict)
        assert result["status"] == "complete"
        assert result["adoption"]["selected_mode"] == "omg-only"
        assert result["preferences"]["config"]["preset"] == "balanced"


class TestWizardStubs:
    """Tests for individual wizard step stubs."""

    def test_detect_clis_returns_dict(self):
        """detect_clis() should return a dict (real detection via registry)."""
        import setup_wizard
        import runtime.cli_provider
        from unittest.mock import patch

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True):
            result = setup_wizard.detect_clis()
        assert isinstance(result, dict)

    def test_check_auth_returns_pending(self):
        """check_auth() stub should return pending status."""
        import setup_wizard

        result = setup_wizard.check_auth()
        assert isinstance(result, dict)
        assert result["status"] == "pending"

    def test_configure_mcp_returns_ok_status(self):
        """configure_mcp() should return status=ok."""
        import setup_wizard

        result = setup_wizard.configure_mcp(
            project_dir="/tmp/test",
            detected_clis={}
        )
        assert isinstance(result, dict)
        assert result["status"] == "ok"

    def test_set_preferences_returns_ok(self):
        """set_preferences() should return ok status."""
        import setup_wizard

        with tempfile.TemporaryDirectory() as tmpdir:
            result = setup_wizard.set_preferences(tmpdir, {})
        assert isinstance(result, dict)
        assert result["status"] == "ok"


class TestDetectClis:
    """Tests for detect_clis() real CLI detection using provider registry."""

    @staticmethod
    def _mock_provider(name: str, detected: bool = True, auth_ok: bool | None = True, auth_msg: str = "ok") -> Mock:
        """Create a mock CLIProvider with given detect/auth behavior."""
        p = Mock()
        p.get_name.return_value = name
        p.detect.return_value = detected
        p.check_auth.return_value = (auth_ok, auth_msg)
        return p

    def test_returns_entry_per_registered_provider(self):
        """detect_clis should return dict with one entry per registered provider."""
        import setup_wizard
        import runtime.cli_provider

        mock_a = self._mock_provider("alpha")
        mock_b = self._mock_provider("beta")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"alpha": mock_a, "beta": mock_b}, clear=True):
            result = setup_wizard.detect_clis()

        assert "alpha" in result
        assert "beta" in result
        assert len(result) == 2

    def test_detected_and_authenticated(self):
        """Detected + authenticated provider reports detected=True, auth_ok=True."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("codex", detected=True, auth_ok=True, auth_msg="authenticated")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"codex": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["codex"]["detected"] is True
        assert result["codex"]["auth_ok"] is True
        assert result["codex"]["message"] == "authenticated"

    def test_detected_not_authenticated(self):
        """Detected but not authenticated reports auth_ok=False."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("gemini", detected=True, auth_ok=False, auth_msg="not logged in")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"gemini": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["gemini"]["detected"] is True
        assert result["gemini"]["auth_ok"] is False
        assert "not logged in" in result["gemini"]["message"]

    def test_not_detected_shows_install_hint_for_codex(self):
        """Undetected codex provider should include npm install hint."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("codex", detected=False)

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"codex": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["codex"]["detected"] is False
        assert "npm install -g @openai/codex" in result["codex"]["message"]

    def test_not_detected_shows_install_hint_for_gemini(self):
        """Undetected gemini provider should include npm install hint."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("gemini", detected=False)

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"gemini": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["gemini"]["detected"] is False
        assert "npm install -g @google/gemini-cli" in result["gemini"]["message"]

    def test_detect_clis_excludes_opencode(self):
        """OpenCode should not appear in setup wizard detection results."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("codex", detected=False)

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"codex": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert "opencode" not in result
        assert result["codex"]["detected"] is False

    def test_not_detected_shows_install_hint_for_kimi(self):
        """Undetected kimi provider should include uv install hint."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("kimi", detected=False)

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"kimi": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["kimi"]["detected"] is False
        assert "uv tool install" in result["kimi"]["message"]

    def test_auth_none_status(self):
        """Provider with None auth status should report auth_ok=None."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = self._mock_provider("kimi", detected=True, auth_ok=None, auth_msg="check failed")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"kimi": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["kimi"]["detected"] is True
        assert result["kimi"]["auth_ok"] is None

    def test_detect_exception_handled_gracefully(self):
        """Exception in detect() should mark provider as not detected."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = Mock()
        mock_p.detect.side_effect = RuntimeError("binary crashed")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"bad": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["bad"]["detected"] is False

    def test_auth_exception_handled_gracefully(self):
        """Exception in check_auth() should set auth_ok=None."""
        import setup_wizard
        import runtime.cli_provider

        mock_p = Mock()
        mock_p.detect.return_value = True
        mock_p.check_auth.side_effect = RuntimeError("auth broken")

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"broken": mock_p}, clear=True):
            result = setup_wizard.detect_clis()

        assert result["broken"]["detected"] is True
        assert result["broken"]["auth_ok"] is None

    def test_empty_registry_returns_empty_dict(self):
        """No registered providers should return empty dict."""
        import setup_wizard
        import runtime.cli_provider

        with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, {}, clear=True):
            result = setup_wizard.detect_clis()

        assert result == {}

    def test_run_setup_wizard_uses_detect_clis_results(self):
        """run_setup_wizard should include real detect_clis results when enabled."""
        import setup_wizard
        import runtime.cli_provider
        import _common

        mock_p = self._mock_provider("codex", detected=True, auth_ok=True, auth_msg="ready")

        _common._FEATURE_CACHE.clear()

        with patch.dict(os.environ, {"OMG_SETUP_ENABLED": "1"}), \
             patch.dict(runtime.cli_provider._PROVIDER_REGISTRY,
                        {"codex": mock_p}, clear=True):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = setup_wizard.run_setup_wizard(tmpdir)

        assert result["status"] == "complete"
        assert "codex" in result["clis_detected"]
        assert result["clis_detected"]["codex"]["detected"] is True


class TestSetPreferences:
    """Tests for set_preferences() CLI config writer."""

    def test_set_preferences_returns_dict_with_status_ok(self):
        """set_preferences() should return dict with status='ok'."""
        import setup_wizard

        with tempfile.TemporaryDirectory() as tmpdir:
            result = setup_wizard.set_preferences(tmpdir, {})

        assert isinstance(result, dict)
        assert result["status"] == "ok"

    def test_set_preferences_returns_path_to_config_file(self):
        """set_preferences() should return path to saved config file."""
        import setup_wizard

        with tempfile.TemporaryDirectory() as tmpdir:
            result = setup_wizard.set_preferences(tmpdir, {})

        assert "path" in result
        assert result["path"].endswith("cli-config.yaml")

    def test_set_preferences_creates_state_directory(self):
        """set_preferences() should create .omg/state/ if missing."""
        import setup_wizard

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {})

            state_dir = os.path.join(tmpdir, ".omg", "state")
            assert os.path.isdir(state_dir)

    def test_set_preferences_writes_valid_yaml(self):
        """set_preferences() should write valid YAML file."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            result = setup_wizard.set_preferences(tmpdir, {})

            config_path = result["path"]
            assert os.path.isfile(config_path)

            with open(config_path) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict)

    def test_set_preferences_includes_version(self):
        """Config should include version field."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {})

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)
            assert "version" in data
            assert data["version"] == "2.0.2"

    def test_set_preferences_includes_cli_configs_key(self):
        """Config should include cli_configs key."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {})

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)
            assert "cli_configs" in data
            assert isinstance(data["cli_configs"], dict)

    def test_set_preferences_default_config_has_all_clis(self):
        """Default config should have entries for codex, gemini, and kimi only."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {})

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)

            cli_configs = data["cli_configs"]
            assert "codex" in cli_configs
            assert "gemini" in cli_configs
            assert "kimi" in cli_configs
            assert "opencode" not in cli_configs

    def test_set_preferences_default_subscription_is_free(self):
        """Default subscription tier should be 'free' for all CLIs."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {})

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)

            for cli_name, config in data["cli_configs"].items():
                assert config["subscription"] == "free", f"{cli_name} should have free subscription"

    def test_set_preferences_default_max_parallel_agents_is_one(self):
        """Default max_parallel_agents should be 1 for all CLIs."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {})

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)

            for cli_name, config in data["cli_configs"].items():
                assert config["max_parallel_agents"] == 1, f"{cli_name} should have max_parallel_agents=1"

    def test_set_preferences_accepts_custom_preferences(self):
        """set_preferences() should accept custom preferences dict."""
        import setup_wizard
        import yaml

        custom_prefs = {
            "cli_configs": {
                "codex": {"subscription": "pro", "max_parallel_agents": 3},
                "gemini": {"subscription": "free", "max_parallel_agents": 1},
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, custom_prefs)

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)

            assert data["cli_configs"]["codex"]["subscription"] == "pro"
            assert data["cli_configs"]["codex"]["max_parallel_agents"] == 3

    def test_set_preferences_returns_config_in_result(self):
        """set_preferences() should return the saved config in result['config']."""
        import setup_wizard

        with tempfile.TemporaryDirectory() as tmpdir:
            result = setup_wizard.set_preferences(tmpdir, {})

        assert "config" in result
        assert isinstance(result["config"], dict)
        assert "version" in result["config"]
        assert "cli_configs" in result["config"]
        assert "preset" in result["config"]

    def test_set_preferences_idempotent(self):
        """Calling set_preferences() twice should produce same file."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            result1 = setup_wizard.set_preferences(tmpdir, {})
            config_path = result1["path"]

            with open(config_path) as f:
                data1 = yaml.safe_load(f)

            result2 = setup_wizard.set_preferences(tmpdir, {})

            with open(config_path) as f:
                data2 = yaml.safe_load(f)

            assert data1 == data2

    def test_set_preferences_writes_requested_preset(self):
        """Preset should be persisted in cli-config.yaml."""
        import setup_wizard
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_wizard.set_preferences(tmpdir, {"preset": "labs"})

            config_path = os.path.join(tmpdir, ".omg", "state", "cli-config.yaml")
            with open(config_path) as f:
                data = yaml.safe_load(f)

        assert data["preset"] == "labs"


class TestConfigureMcp:
    """Tests for configure_mcp() MCP server configuration."""

    def test_configure_mcp_returns_ok_status(self):
        """configure_mcp() should return status=ok."""
        import setup_wizard

        with tempfile.TemporaryDirectory() as tmpdir:
            result = setup_wizard.configure_mcp(
                project_dir=tmpdir,
                detected_clis={}
            )
        assert isinstance(result, dict)
        assert result["status"] == "ok"

    def test_configure_mcp_always_writes_claude_config(self):
        """Claude config should be written even with empty detected_clis."""
        import setup_wizard
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_claude = MagicMock()
            with patch("setup_wizard.write_claude_mcp_config", mock_claude):
                setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={}
                )
            mock_claude.assert_called_once()

    def test_configure_mcp_writes_detected_cli_configs(self):
        """Detected CLI should have its config writer called."""
        import setup_wizard
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_codex = MagicMock()
            with patch("setup_wizard.write_codex_mcp_config", mock_codex), \
                 patch("setup_wizard.write_claude_mcp_config"):
                setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={"codex": {"detected": True}}
                )
            mock_codex.assert_called_once()

    def test_configure_mcp_skips_undetected_clis(self):
        """Undetected CLI should NOT have its config writer called."""
        import setup_wizard
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_gemini = MagicMock()
            with patch("setup_wizard.write_gemini_mcp_config", mock_gemini), \
                 patch("setup_wizard.write_claude_mcp_config"):
                setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={"gemini": {"detected": False}}
                )
            mock_gemini.assert_not_called()

    def test_configure_mcp_returns_configured_list(self):
        """Result should include list of successfully configured CLIs."""
        import setup_wizard
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("setup_wizard.write_codex_mcp_config"), \
                 patch("setup_wizard.write_gemini_mcp_config"), \
                 patch("setup_wizard.write_claude_mcp_config"):
                result = setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={
                        "codex": {"detected": True},
                        "gemini": {"detected": False}
                    }
                )
        assert "configured" in result
        assert isinstance(result["configured"], list)
        assert "codex" in result["configured"]
        assert "gemini" not in result["configured"]

    def test_configure_mcp_handles_writer_error(self):
        """Writer exception should be caught and added to errors dict."""
        import setup_wizard
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            def raise_error(*args, **kwargs):
                raise RuntimeError("write failed")

            with patch("setup_wizard.write_codex_mcp_config", side_effect=raise_error), \
                 patch("setup_wizard.write_claude_mcp_config"):
                result = setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={"codex": {"detected": True}}
                )
        assert result["status"] == "ok"
        assert "errors" in result
        assert "codex" in result["errors"]
        assert "write failed" in result["errors"]["codex"]

    def test_configure_mcp_custom_server_url(self):
        """Custom server URL should be passed to writers."""
        import setup_wizard
        from unittest.mock import patch, call

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("setup_wizard.write_codex_mcp_config") as mock_codex, \
                 patch("setup_wizard.write_claude_mcp_config") as mock_claude:
                setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={"codex": {"detected": True}},
                    server_url="http://custom:9999/mcp"
                )
            # Check that custom URL was passed
            calls = mock_codex.call_args_list
            assert any("http://custom:9999/mcp" in str(call) for call in calls)

    def test_configure_mcp_custom_server_name(self):
        """Custom server name should be passed to writers."""
        import setup_wizard
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("setup_wizard.write_codex_mcp_config") as mock_codex, \
                 patch("setup_wizard.write_claude_mcp_config") as mock_claude:
                setup_wizard.configure_mcp(
                    project_dir=tmpdir,
                    detected_clis={"codex": {"detected": True}},
                    server_name="custom-server"
                )
            # Check that custom name was passed
            calls = mock_codex.call_args_list
            assert any("custom-server" in str(call) for call in calls)
