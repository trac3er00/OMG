"""claude_experimental.memory — Tier-2: SQLite-backed episodic/semantic/procedural memory."""
from __future__ import annotations


def is_available() -> bool:
    from claude_experimental._flags import get_feature_flag
    return get_feature_flag("EXPERIMENTAL_MEMORY", default=False)


def _require_enabled() -> None:
    if not is_available():
        raise RuntimeError(
            "Tier-2 experimental memory is disabled. "
            "Enable with: OMG_EXPERIMENTAL_MEMORY_ENABLED=1 or "
            "settings.json _omg.features.EXPERIMENTAL_MEMORY: true"
        )
