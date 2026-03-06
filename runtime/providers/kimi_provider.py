"""Kimi CLI provider registration."""
from __future__ import annotations

from runtime.cli_provider import ContractCLIProvider, default_config_path, register_provider


register_provider(
    ContractCLIProvider(
        "kimi",
        config_path=default_config_path("kimi"),
        model_name="kimi-cli",
    )
)
