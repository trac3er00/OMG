"""Gemini CLI provider registration."""
from __future__ import annotations

from runtime.cli_provider import ContractCLIProvider, default_config_path, register_provider


register_provider(
    ContractCLIProvider(
        "gemini",
        config_path=default_config_path("gemini"),
        model_name="gemini-cli",
    )
)
