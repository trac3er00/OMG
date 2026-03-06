"""Codex CLI provider registration."""
from __future__ import annotations

from runtime.cli_provider import ContractCLIProvider, default_config_path, register_provider


register_provider(
    ContractCLIProvider(
        "codex",
        config_path=default_config_path("codex"),
        model_name="codex-cli",
    )
)
