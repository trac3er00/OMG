"""End-to-end multi-CLI dispatch integration tests.

Exercises the full multi-CLI provider pipeline:
  registration → detection → invocation → dispatch routing → fallback.

All subprocess/CLI interactions are mocked — no real CLI installations required.
"""
from __future__ import annotations

import json
import os
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_provider_registry():
    """Save and restore the global provider registry between tests."""
    from runtime.cli_provider import _PROVIDER_REGISTRY

    snapshot = dict(_PROVIDER_REGISTRY)
    yield
    _PROVIDER_REGISTRY.clear()
    _PROVIDER_REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# 1. Provider registration pipeline
# ---------------------------------------------------------------------------


def test_all_providers_registered():
    """All 4 CLI providers register into the global registry on import."""
    import runtime.providers.codex_provider  # noqa: F401
    import runtime.providers.gemini_provider  # noqa: F401
    import runtime.providers.kimi_provider  # noqa: F401
    import runtime.providers.opencode_provider  # noqa: F401
    from runtime.cli_provider import list_available_providers

    providers = list_available_providers()
    assert "codex" in providers
    assert "gemini" in providers
    assert "opencode" in providers
    assert "kimi" in providers


def test_get_provider_returns_registered_instance():
    """get_provider() returns the correct instance by canonical name."""
    import runtime.providers.codex_provider  # noqa: F401
    from runtime.cli_provider import get_provider

    provider = get_provider("codex")
    assert provider is not None
    assert provider.get_name() == "codex"


# ---------------------------------------------------------------------------
# 2. Provider detection — CLI installed
# ---------------------------------------------------------------------------


def test_codex_detect_when_installed(monkeypatch):
    """CodexProvider.detect() → True when codex binary on PATH."""
    from runtime.providers.codex_provider import CodexProvider

    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/local/bin/codex" if x == "codex" else None,
    )
    assert CodexProvider().detect() is True


def test_gemini_detect_when_installed(monkeypatch):
    """GeminiProvider.detect() → True when gemini binary on PATH."""
    from runtime.providers.gemini_provider import GeminiProvider

    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/local/bin/gemini" if x == "gemini" else None,
    )
    assert GeminiProvider().detect() is True


def test_opencode_detect_when_installed(monkeypatch):
    """OpenCodeProvider.detect() → True when opencode binary on PATH."""
    from runtime.providers.opencode_provider import OpenCodeProvider

    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/local/bin/opencode" if x == "opencode" else None,
    )
    assert OpenCodeProvider().detect() is True


def test_kimi_detect_when_installed(monkeypatch):
    """KimiCodeProvider.detect() → True when kimi binary on PATH."""
    from runtime.providers.kimi_provider import KimiCodeProvider

    monkeypatch.setattr(
        "shutil.which",
        lambda x: "/usr/local/bin/kimi" if x == "kimi" else None,
    )
    assert KimiCodeProvider().detect() is True


# ---------------------------------------------------------------------------
# 3. Provider detection — CLI missing
# ---------------------------------------------------------------------------


def test_provider_detect_when_cli_missing(monkeypatch):
    """detect() → False for every provider when no binary on PATH."""
    from runtime.providers.codex_provider import CodexProvider
    from runtime.providers.gemini_provider import GeminiProvider
    from runtime.providers.kimi_provider import KimiCodeProvider
    from runtime.providers.opencode_provider import OpenCodeProvider

    monkeypatch.setattr("shutil.which", lambda x: None)
    assert CodexProvider().detect() is False
    assert GeminiProvider().detect() is False
    assert OpenCodeProvider().detect() is False
    assert KimiCodeProvider().detect() is False


# ---------------------------------------------------------------------------
# 4. Provider invoke — mock subprocess
# ---------------------------------------------------------------------------


def test_codex_provider_invoke_success(monkeypatch):
    """CodexProvider.invoke() returns model/output/exit_code on success."""
    from runtime.providers.codex_provider import CodexProvider

    mock_result = MagicMock(returncode=0, stdout='{"output": "hello"}', stderr="")
    monkeypatch.setattr(
        "runtime.cli_provider.subprocess.run", lambda *a, **kw: mock_result
    )
    result = CodexProvider().invoke("test prompt", "/tmp/project")
    assert result["model"] == "codex-cli"
    assert result["exit_code"] == 0
    assert "hello" in result["output"]


def test_gemini_provider_invoke_success(monkeypatch):
    """GeminiProvider.invoke() returns model/output/exit_code on success."""
    from runtime.providers.gemini_provider import GeminiProvider

    mock_result = MagicMock(returncode=0, stdout="gemini output text", stderr="")
    monkeypatch.setattr(
        "runtime.cli_provider.subprocess.run", lambda *a, **kw: mock_result
    )
    result = GeminiProvider().invoke("test prompt", "/tmp/project")
    assert result["model"] == "gemini-cli"
    assert result["exit_code"] == 0


def test_opencode_provider_invoke_success(monkeypatch):
    """OpenCodeProvider.invoke() returns model/output/exit_code on success."""
    from runtime.providers.opencode_provider import OpenCodeProvider

    mock_result = MagicMock(returncode=0, stdout="opencode output", stderr="")
    monkeypatch.setattr(
        "runtime.cli_provider.subprocess.run", lambda *a, **kw: mock_result
    )
    result = OpenCodeProvider().invoke("test prompt", "/tmp/project")
    assert result["model"] == "opencode-cli"
    assert result["exit_code"] == 0


def test_kimi_provider_invoke_success(monkeypatch):
    """KimiCodeProvider.invoke() returns model/output/exit_code on success."""
    from runtime.providers.kimi_provider import KimiCodeProvider

    mock_result = MagicMock(returncode=0, stdout="kimi output", stderr="")
    monkeypatch.setattr(
        "runtime.cli_provider.subprocess.run", lambda *a, **kw: mock_result
    )
    result = KimiCodeProvider().invoke("test prompt", "/tmp/project")
    assert result["model"] == "kimi-cli"
    assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# 5. dispatch_to_model via provider registry
# ---------------------------------------------------------------------------


def _mock_agent_registry(monkeypatch, agent_name, preferred_model, available_models):
    """Insert a fake _agent_registry module into sys.modules."""
    mock_mod = types.ModuleType("_agent_registry")
    mock_mod.AGENT_REGISTRY = {  # type: ignore[attr-defined]
        agent_name: {
            "preferred_model": preferred_model,
            "description": "test agent",
            "task_category": "deep",
            "skills": [],
            "model_version": "test",
        }
    }
    mock_mod.detect_available_models = lambda: available_models  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "_agent_registry", mock_mod)


def test_dispatch_to_model_uses_provider_registry(monkeypatch):
    """dispatch_to_model routes through the provider registry when provider available."""
    from runtime.cli_provider import _PROVIDER_REGISTRY
    from runtime.team_router import dispatch_to_model

    _mock_agent_registry(
        monkeypatch,
        agent_name="test-agent",
        preferred_model="opencode-cli",
        available_models={"opencode-cli": True},
    )

    mock_provider = MagicMock()
    mock_provider.detect.return_value = True
    mock_provider.invoke.return_value = {
        "model": "opencode-cli",
        "output": "done",
        "exit_code": 0,
    }
    _PROVIDER_REGISTRY["opencode"] = mock_provider

    monkeypatch.setattr("runtime.team_router._should_use_tmux", lambda: False)

    result = dispatch_to_model("test-agent", "test prompt", "/tmp/project")
    assert result.get("model") == "opencode-cli"
    mock_provider.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Fallback to Claude
# ---------------------------------------------------------------------------


def test_dispatch_falls_back_when_provider_unavailable(monkeypatch):
    """dispatch_to_model returns claude fallback when no provider in registry."""
    from runtime.cli_provider import _PROVIDER_REGISTRY
    from runtime.team_router import dispatch_to_model

    _mock_agent_registry(
        monkeypatch,
        agent_name="test-agent",
        preferred_model="opencode-cli",
        available_models={"opencode-cli": True},
    )

    # Clear all providers so get_provider returns None
    _PROVIDER_REGISTRY.clear()

    monkeypatch.setattr("runtime.team_router._should_use_tmux", lambda: False)

    result = dispatch_to_model("test-agent", "test prompt", "/tmp/project")
    assert result is not None
    assert result.get("fallback") == "claude"


# ---------------------------------------------------------------------------
# 7. Provider names
# ---------------------------------------------------------------------------


def test_provider_names_are_correct():
    """Each provider returns its expected canonical name."""
    from runtime.providers.codex_provider import CodexProvider
    from runtime.providers.gemini_provider import GeminiProvider
    from runtime.providers.kimi_provider import KimiCodeProvider
    from runtime.providers.opencode_provider import OpenCodeProvider

    assert CodexProvider().get_name() == "codex"
    assert GeminiProvider().get_name() == "gemini"
    assert OpenCodeProvider().get_name() == "opencode"
    assert KimiCodeProvider().get_name() == "kimi"


# ---------------------------------------------------------------------------
# 8. Provider get_non_interactive_cmd
# ---------------------------------------------------------------------------


def test_codex_non_interactive_cmd():
    """CodexProvider command includes 'codex' binary and the prompt text."""
    from runtime.providers.codex_provider import CodexProvider

    cmd = CodexProvider().get_non_interactive_cmd("hello world")
    assert cmd[0] == "codex"
    assert "hello world" in " ".join(cmd)


def test_gemini_non_interactive_cmd():
    """GeminiProvider command includes 'gemini' binary and the prompt text."""
    from runtime.providers.gemini_provider import GeminiProvider

    cmd = GeminiProvider().get_non_interactive_cmd("hello world")
    assert cmd[0] == "gemini"
    assert "hello world" in " ".join(cmd)


def test_opencode_non_interactive_cmd():
    """OpenCodeProvider command includes 'opencode' binary and the prompt text."""
    from runtime.providers.opencode_provider import OpenCodeProvider

    cmd = OpenCodeProvider().get_non_interactive_cmd("hello world")
    assert cmd[0] == "opencode"
    assert "hello world" in " ".join(cmd)


def test_kimi_non_interactive_cmd():
    """KimiCodeProvider command includes 'kimi' binary and the prompt text."""
    from runtime.providers.kimi_provider import KimiCodeProvider

    cmd = KimiCodeProvider().get_non_interactive_cmd("hello world")
    assert cmd[0] == "kimi"
    assert "hello world" in " ".join(cmd)


# ---------------------------------------------------------------------------
# 9. Provider write_mcp_config — use tmp_path
# ---------------------------------------------------------------------------


def test_codex_write_mcp_config_toml(monkeypatch, tmp_path):
    """CodexProvider writes TOML MCP config with server name and URL."""
    from runtime.providers.codex_provider import CodexProvider

    config_file = tmp_path / "codex" / "config.toml"
    p = CodexProvider()
    monkeypatch.setattr(p, "get_config_path", lambda: str(config_file))

    p.write_mcp_config("http://localhost:3000", "test-server")

    content = config_file.read_text()
    assert "test-server" in content
    assert "http://localhost:3000" in content


def test_gemini_write_mcp_config_json(monkeypatch, tmp_path):
    """GeminiProvider writes JSON MCP config with mcpServers key and httpUrl."""
    from runtime.providers.gemini_provider import GeminiProvider

    config_file = tmp_path / "gemini" / "settings.json"
    p = GeminiProvider()
    monkeypatch.setattr(p, "get_config_path", lambda: str(config_file))

    p.write_mcp_config("http://localhost:4000", "mem-server")

    data = json.loads(config_file.read_text())
    assert "mcpServers" in data
    assert data["mcpServers"]["mem-server"]["httpUrl"] == "http://localhost:4000"


def test_opencode_write_mcp_config_json(monkeypatch, tmp_path):
    """OpenCodeProvider writes JSON MCP config with mcp key and remote type."""
    from runtime.providers.opencode_provider import OpenCodeProvider

    config_file = tmp_path / "opencode" / "opencode.json"
    p = OpenCodeProvider()
    monkeypatch.setattr(p, "get_config_path", lambda: str(config_file))

    p.write_mcp_config("http://localhost:5000", "oc-server")

    data = json.loads(config_file.read_text())
    assert "mcp" in data
    assert data["mcp"]["oc-server"]["type"] == "remote"
    assert data["mcp"]["oc-server"]["url"] == "http://localhost:5000"


def test_kimi_write_mcp_config_json(monkeypatch, tmp_path):
    """KimiCodeProvider writes JSON MCP config with mcpServers key and http type."""
    from runtime.providers.kimi_provider import KimiCodeProvider

    config_file = tmp_path / "kimi" / "mcp.json"
    p = KimiCodeProvider()
    monkeypatch.setattr(p, "get_config_path", lambda: str(config_file))

    p.write_mcp_config("http://localhost:6000", "kimi-server")

    data = json.loads(config_file.read_text())
    assert "mcpServers" in data
    assert data["mcpServers"]["kimi-server"]["type"] == "http"
    assert data["mcpServers"]["kimi-server"]["url"] == "http://localhost:6000"
