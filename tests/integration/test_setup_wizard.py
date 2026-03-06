"""Integration tests for hooks/setup_wizard.py using the current provider bootstrap flow."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "hooks"))
sys.path.insert(0, str(_PROJECT_ROOT))

import _common
import runtime.cli_provider
import setup_wizard


def _mock_provider(
    name: str,
    *,
    detected: bool = True,
    auth_ok: bool | None = True,
    auth_msg: str = "ok",
) -> Mock:
    provider = Mock()
    provider.get_name.return_value = name
    provider.detect.return_value = detected
    provider.check_auth.return_value = (auth_ok, auth_msg)
    provider.get_config_path.return_value = str(Path.home() / f".{name}" / "config")
    provider.invoke.return_value = {"model": f"{name}-cli", "output": "ok", "exit_code": 0}
    provider.invoke_tmux.return_value = {"model": f"{name}-cli", "output": "ok", "exit_code": 0}
    return provider


@pytest.fixture(autouse=True)
def _clear_feature_cache():
    _common._FEATURE_CACHE.clear()
    yield
    _common._FEATURE_CACHE.clear()


def test_detect_clis_returns_registered_providers():
    providers = {
        "codex": _mock_provider("codex", detected=True, auth_ok=True, auth_msg="ready"),
        "gemini": _mock_provider("gemini", detected=False),
        "kimi": _mock_provider("kimi", detected=True, auth_ok=None, auth_msg="manual"),
    }

    with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, providers, clear=True):
        result = setup_wizard.detect_clis()

    assert set(result) == {"codex", "gemini", "kimi"}
    assert result["codex"]["auth_ok"] is True
    assert result["gemini"]["detected"] is False
    assert result["kimi"]["auth_ok"] is None


def test_configure_mcp_bootstraps_detected_providers(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    detected = {
        "codex": {"detected": True},
        "gemini": {"detected": False},
        "kimi": {"detected": True},
    }

    result = setup_wizard.configure_mcp(str(tmp_path), detected)

    assert result["status"] == "ok"
    assert set(result["configured"]) == {"codex", "kimi"}
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / ".codex" / "config.toml").exists()
    assert (tmp_path / ".kimi" / "mcp.json").exists()


def test_run_setup_wizard_includes_bootstrap_and_status(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OMG_SETUP_ENABLED", "1")

    providers = {
        "codex": _mock_provider("codex", detected=True, auth_ok=True, auth_msg="ready"),
        "gemini": _mock_provider("gemini", detected=True, auth_ok=None, auth_msg="manual"),
        "kimi": _mock_provider("kimi", detected=False, auth_ok=None, auth_msg=""),
    }

    with patch.dict(runtime.cli_provider._PROVIDER_REGISTRY, providers, clear=True):
        result = setup_wizard.run_setup_wizard(str(tmp_path), non_interactive=True)

    assert result["status"] == "complete"
    assert result["provider_bootstrap"]["schema"] == "ProviderBootstrapResult"
    assert result["provider_status"]["schema"] == "ProviderStatusMatrix"
    assert (tmp_path / ".omg" / "state" / "cli-config.yaml").exists()
