"""Live smoke coverage for supported external provider CLIs."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from runtime.provider_smoke import get_host_runtime_paths, run_provider_live_smoke
from runtime.team_router import get_host_execution_matrix


ROOT = Path(__file__).resolve().parents[2]

_NATIVE_EXPECTATIONS = {
    "codex": {"success", "mcp_unreachable", "auth_required"},
    "gemini": {"success", "missing_env", "auth_required", "service_disabled"},
    "kimi": {"success", "missing_model", "mcp_unreachable", "auth_required"},
}


def _require_provider_cli(provider: str) -> None:
    if shutil.which(provider) is None:
        pytest.skip(f"{provider} CLI is not installed on PATH")


@pytest.mark.parametrize("provider", ["codex", "gemini", "kimi"])
def test_provider_native_live_smoke(provider: str):
    _require_provider_cli(provider)

    result = run_provider_live_smoke(
        provider,
        str(ROOT),
        host_mode=f"{provider}_native",
    )

    assert result["schema"] == "ProviderSmokeResult"
    assert result["status"] == "ok"
    assert result["provider"] == provider
    assert result["host_mode"] == f"{provider}_native"
    assert result["binary_available"] is True
    assert result["smoke_status"] in _NATIVE_EXPECTATIONS[provider]
    assert "dependency_state" in result
    assert "mcp_server" in result
    assert "blocking_class" in result


@pytest.mark.parametrize("provider", ["codex", "gemini", "kimi"])
def test_claude_dispatch_live_smoke(provider: str):
    _require_provider_cli(provider)

    result = run_provider_live_smoke(
        provider,
        str(ROOT),
        host_mode="claude_dispatch",
    )

    assert result["schema"] == "ProviderSmokeResult"
    assert result["status"] == "ok"
    assert result["provider"] == provider
    assert result["host_mode"] == "claude_dispatch"
    assert result["binary_available"] is True
    assert result["smoke_status"] in _NATIVE_EXPECTATIONS[provider]
    assert result["dependency_state"] in {"ready", "startup_failed"}
    assert isinstance(result["bootstrap_state"]["host_config_exists"], bool)
    assert isinstance(result["bootstrap_state"]["project_mcp_exists"], bool)
    if result["smoke_status"] == "service_disabled":
        assert result["blocking_class"] == "service_disabled"
        assert result["retryable"] is False
        assert result["recovery_action"] == "appeal_provider_account"
        assert result["additional_recovery_actions"] == []


def test_native_omg_hosts_expose_runtime_paths():
    matrix = get_host_execution_matrix()

    for host_mode, profile in matrix.items():
        if not profile["native_omg_supported"]:
            continue

        paths = get_host_runtime_paths(host_mode, str(ROOT))

        assert paths["host_mode"] == host_mode
        assert paths["omg_entrypoint"].endswith("scripts/omg.py")
        assert Path(paths["omg_entrypoint"]).exists()
        assert paths["project_mcp"].endswith(".mcp.json")
        assert paths["bootstrap_root"].endswith(".omg")
