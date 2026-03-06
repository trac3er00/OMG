"""OpenCode CLI provider registration."""
from __future__ import annotations

from runtime.cli_provider import ContractCLIProvider, default_config_path, register_provider


register_provider(
    ContractCLIProvider(
        "opencode",
        config_path=default_config_path("opencode"),
        model_name="opencode-cli",
    )
)
