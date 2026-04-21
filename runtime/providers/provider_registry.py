"""Provider registry for OMG v3.0.0 expansion.
Tracks confirmed, pending, and stub providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ProviderStatus = Literal["confirmed", "pending", "stub"]


@dataclass
class ProviderEntry:
    name: str
    cli_command: str  # CLI binary name
    status: ProviderStatus
    mcp_config_supported: bool = False
    output_normalization: str = "passthrough"
    notes: str = ""

    def is_available(self) -> bool:
        """Check if CLI binary exists on PATH."""
        import shutil

        return shutil.which(self.cli_command) is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cli_command": self.cli_command,
            "status": self.status,
            "available": self.is_available(),
            "mcp_config_supported": self.mcp_config_supported,
            "notes": self.notes,
        }


# Canonical confirmed providers (already have full adapters)
CONFIRMED_PROVIDERS = [
    ProviderEntry("claude", "claude", "confirmed", mcp_config_supported=True),
    ProviderEntry("codex", "codex", "confirmed", mcp_config_supported=True),
    ProviderEntry("gemini", "gemini", "confirmed", mcp_config_supported=True),
    ProviderEntry("kimi", "kimi", "confirmed", mcp_config_supported=True),
    ProviderEntry("ollama-cloud", "ollama", "confirmed", mcp_config_supported=True),
]

# Providers to investigate — create stubs with "pending" status
PENDING_PROVIDERS = [
    ProviderEntry(
        "qwen-cli", "qwen", "pending", notes="Alibaba Qwen CLI — verify availability"
    ),
    ProviderEntry(
        "kilocode", "kilocode", "pending", notes="Kilocode — verify CLI existence"
    ),
    ProviderEntry(
        "conductor", "conductor", "pending", notes="Conductor AI — verify CLI"
    ),
]

ALL_PROVIDERS = CONFIRMED_PROVIDERS + PENDING_PROVIDERS


def get_registry() -> list[ProviderEntry]:
    return ALL_PROVIDERS


def get_confirmed() -> list[ProviderEntry]:
    return [p for p in ALL_PROVIDERS if p.status == "confirmed"]


def get_pending() -> list[ProviderEntry]:
    return [p for p in ALL_PROVIDERS if p.status == "pending"]


def generate_parity_report(providers: list[ProviderEntry]) -> dict[str, Any]:
    """Generate parity report for all providers."""
    return {
        "total": len(providers),
        "confirmed": len([p for p in providers if p.status == "confirmed"]),
        "pending": len([p for p in providers if p.status == "pending"]),
        "available_on_path": len([p for p in providers if p.is_available()]),
        "providers": [p.to_dict() for p in providers],
    }
