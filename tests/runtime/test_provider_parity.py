from __future__ import annotations

from runtime.host_parity import (
    evaluate_provider_registry_parity,
    get_provider_parity_stubs,
)
from runtime.providers.provider_registry import (
    ProviderEntry,
    generate_parity_report,
    get_confirmed,
    get_pending,
    get_registry,
)


def test_registry_structure() -> None:
    registry = get_registry()

    assert isinstance(registry, list)
    assert len(registry) == 8
    assert all(isinstance(provider, ProviderEntry) for provider in registry)


def test_confirmed_providers() -> None:
    confirmed_names = {provider.name for provider in get_confirmed()}

    assert confirmed_names == {"claude", "codex", "gemini", "kimi", "ollama-cloud"}


def test_pending_stubs() -> None:
    pending = get_pending()

    assert {provider.name for provider in pending} == {
        "qwen-cli",
        "kilocode",
        "conductor",
    }
    assert all(provider.status == "pending" for provider in pending)
    assert all(provider.notes for provider in pending)


def test_parity_report(monkeypatch) -> None:
    monkeypatch.setattr(
        ProviderEntry, "is_available", lambda self: self.name in {"claude", "codex"}
    )

    report = generate_parity_report(get_registry())

    assert report["total"] == 8
    assert report["confirmed"] == 5
    assert report["pending"] == 3
    assert report["available_on_path"] == 2
    assert len(report["providers"]) == 8


def test_provider_to_dict(monkeypatch) -> None:
    monkeypatch.setattr(ProviderEntry, "is_available", lambda self: True)
    provider = ProviderEntry("test-provider", "test-cli", "stub")

    payload = provider.to_dict()

    assert payload == {
        "name": "test-provider",
        "cli_command": "test-cli",
        "status": "stub",
        "available": True,
        "mcp_config_supported": False,
        "notes": "",
    }


def test_get_confirmed() -> None:
    confirmed = get_confirmed()

    assert confirmed
    assert all(provider.status == "confirmed" for provider in confirmed)


def test_get_pending() -> None:
    pending = get_pending()

    assert pending
    assert all(provider.status == "pending" for provider in pending)


def test_host_parity_registry_evaluation_covers_all_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        ProviderEntry, "is_available", lambda self: self.name != "conductor"
    )

    parity_stubs = get_provider_parity_stubs()
    report = evaluate_provider_registry_parity()

    assert parity_stubs == [
        "claude",
        "codex",
        "gemini",
        "kimi",
        "ollama-cloud",
        "qwen-cli",
        "kilocode",
        "conductor",
    ]
    assert report["total"] == len(parity_stubs)
    assert {provider["name"] for provider in report["providers"]} == set(parity_stubs)
