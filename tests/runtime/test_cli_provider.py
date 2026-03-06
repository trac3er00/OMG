"""Tests for runtime/cli_provider.py."""

from __future__ import annotations

from typing import Any, override

import pytest

import runtime.cli_provider as cli_provider
from runtime.cli_provider import CLIProvider, get_provider, list_available_providers, register_provider


@pytest.fixture(autouse=True)
def reset_provider_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a fresh in-memory registry for each test."""
    monkeypatch.setattr(cli_provider, "_PROVIDER_REGISTRY", {})


def test_cli_provider_abstract_contract_enforced() -> None:
    """Subclass without methods cannot be instantiated."""
    bad_provider = type("BadProvider", (CLIProvider,), {})

    with pytest.raises(TypeError) as exc_info:
        _ = bad_provider()

    message = str(exc_info.value)
    expected_methods = [
        "get_name",
        "detect",
        "check_auth",
        "invoke",
        "invoke_tmux",
        "get_non_interactive_cmd",
        "get_config_path",
    ]
    for method_name in expected_methods:
        assert method_name in message


def test_registry_register_lookup_and_list() -> None:
    """Registry stores provider and resolves by name."""

    class DummyProvider(CLIProvider):
        @override
        def get_name(self) -> str:
            return "dummy"

        @override
        def detect(self) -> bool:
            return True

        @override
        def check_auth(self) -> tuple[bool | None, str]:
            return True, "ok"

        @override
        def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
            return {"model": "dummy", "output": prompt, "exit_code": 0}

        @override
        def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
            return {"model": "dummy", "output": prompt, "exit_code": 0}

        @override
        def get_non_interactive_cmd(self, prompt: str, project_dir: str) -> list[str]:
            return ["dummy", prompt, project_dir]

        @override
        def get_config_path(self) -> str:
            return "~/.dummy/config"

    provider = DummyProvider()
    register_provider(provider)

    assert get_provider("dummy") is provider
    assert list_available_providers() == ["dummy"]


def test_get_provider_returns_none_for_unknown_name() -> None:
    """Registry lookup for unknown name returns None."""
    assert get_provider("missing") is None
    assert list_available_providers() == []
