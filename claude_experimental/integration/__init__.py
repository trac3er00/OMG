"""claude_experimental.integration — Tier-4: OpenAPI tool gen, SSE streaming, telemetry, auto-tuning."""
from __future__ import annotations


def is_available() -> bool:
    from claude_experimental._flags import get_feature_flag
    return get_feature_flag("ADVANCED_INTEGRATION", default=False)


def _require_enabled() -> None:
    if not is_available():
        raise RuntimeError(
            "Tier-4 advanced integration is disabled. "
            "Enable with: OMG_ADVANCED_INTEGRATION_ENABLED=1 or "
            "settings.json _omg.features.ADVANCED_INTEGRATION: true"
        )
