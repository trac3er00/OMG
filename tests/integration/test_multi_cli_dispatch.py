"""Integration tests for current multi-provider dispatch paths."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolate_provider_registry():
    from runtime.cli_provider import _PROVIDER_REGISTRY

    snapshot = dict(_PROVIDER_REGISTRY)
    yield
    _PROVIDER_REGISTRY.clear()
    _PROVIDER_REGISTRY.update(snapshot)


def _mock_agent_registry(monkeypatch, agent_name: str, preferred_model: str, available_models: dict[str, bool]):
    fake = types.ModuleType("_agent_registry")
    fake.AGENT_REGISTRY = {
        agent_name: {
            "preferred_model": preferred_model,
            "description": "test agent",
            "task_category": "deep",
            "skills": [],
            "model_version": "test",
        }
    }
    fake.detect_available_models = lambda: available_models
    monkeypatch.setitem(sys.modules, "_agent_registry", fake)


def test_all_supported_providers_register():
    import runtime.providers.codex_provider  # noqa: F401
    import runtime.providers.gemini_provider  # noqa: F401
    import runtime.providers.kimi_provider  # noqa: F401
    from runtime.cli_provider import list_available_providers

    assert list_available_providers() == ["codex", "gemini", "kimi"]


def test_dispatch_to_model_uses_codex_provider_registry(monkeypatch):
    from runtime.cli_provider import _PROVIDER_REGISTRY
    from runtime.team_router import dispatch_to_model

    _mock_agent_registry(
        monkeypatch,
        agent_name="backend-agent",
        preferred_model="codex-cli",
        available_models={"codex-cli": True},
    )

    provider = MagicMock()
    provider.detect.return_value = True
    provider.invoke.return_value = {"model": "codex-cli", "output": "done", "exit_code": 0}
    _PROVIDER_REGISTRY["codex"] = provider

    monkeypatch.setattr("runtime.team_router._should_use_tmux", lambda: False)
    monkeypatch.setattr("runtime.team_router.ensure_memory_server", lambda: {"status": "started"})
    monkeypatch.setattr(
        "runtime.team_router.check_memory_server",
        lambda: {"running": True, "health_ok": True, "url": "http://127.0.0.1:8765/mcp"},
    )

    result = dispatch_to_model("backend-agent", "test prompt", "/tmp/project")

    assert result["model"] == "codex-cli"
    assert result["provider"] == "codex"
    assert result["host_mode"] == "claude_dispatch"
    provider.invoke.assert_called_once()


def test_dispatch_to_model_falls_back_to_claude_when_provider_missing(monkeypatch):
    from runtime.cli_provider import _PROVIDER_REGISTRY
    from runtime.team_router import dispatch_to_model

    _mock_agent_registry(
        monkeypatch,
        agent_name="runtime-agent",
        preferred_model="kimi-cli",
        available_models={"kimi-cli": True},
    )

    _PROVIDER_REGISTRY.clear()
    monkeypatch.setattr("runtime.team_router._should_use_tmux", lambda: False)

    result = dispatch_to_model("runtime-agent", "inspect runtime", "/tmp/project")

    assert result["fallback"] == "claude"
    assert result["fallback_reason"] == "provider_error"


def test_kimi_contract_builder_matches_current_cli_shape():
    from runtime.cli_provider import build_non_interactive_command

    assert build_non_interactive_command("kimi", "inspect runtime", "/tmp/project") == [
        "kimi",
        "--print",
        "--output-format",
        "text",
        "--final-message-only",
        "-w",
        "/tmp/project",
        "-p",
        "inspect runtime",
    ]
