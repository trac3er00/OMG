"""Tests for root-source CLI provider registry."""
from __future__ import annotations

from runtime.cli_provider import CLIProvider, get_provider, list_available_providers

# Import modules to trigger registration.
import runtime.providers.codex_provider  # noqa: F401
import runtime.providers.gemini_provider  # noqa: F401
import runtime.providers.opencode_provider  # noqa: F401
import runtime.providers.kimi_provider  # noqa: F401


def test_list_available_providers_is_deterministic():
    assert list_available_providers() == ["codex", "gemini", "opencode", "kimi"]
    assert get_provider("legacy-provider") is None
    assert get_provider("kimi") is not None


def test_registered_providers_implement_common_contract():
    for name in list_available_providers():
        provider = get_provider(name)
        assert provider is not None
        assert isinstance(provider, CLIProvider)
        assert provider.get_name() == name
        assert isinstance(provider.detect(), bool)


def test_codex_provider_returns_current_non_interactive_command():
    provider = get_provider("codex")
    assert provider is not None

    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "codex",
        "exec",
        "--json",
        "Reply with OK.",
    ]


def test_gemini_provider_returns_current_non_interactive_command():
    provider = get_provider("gemini")
    assert provider is not None

    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "gemini",
        "-p",
        "Reply with OK.",
        "--output-format",
        "json",
    ]


def test_kimi_provider_returns_current_non_interactive_command():
    provider = get_provider("kimi")
    assert provider is not None

    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "kimi",
        "--print",
        "--output-format",
        "text",
        "--final-message-only",
        "-w",
        "/tmp/project",
        "-p",
        "Reply with OK.",
    ]


def test_opencode_provider_returns_current_non_interactive_command():
    provider = get_provider("opencode")
    assert provider is not None

    assert provider.get_non_interactive_cmd("Reply with OK.", "/tmp/project") == [
        "opencode",
        "run",
        "Reply with OK.",
        "--format",
        "json",
        "--dir",
        "/tmp/project",
    ]
