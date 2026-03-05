"""claude_experimental.parallel — Tier-1: Real parallel agent dispatch (feature-flagged)."""
from __future__ import annotations


def is_available() -> bool:
    """Return True if Tier-1 parallel dispatch is enabled via feature flag."""
    from claude_experimental._flags import get_feature_flag

    return get_feature_flag("PARALLEL_DISPATCH", default=False)


def _require_enabled() -> None:
    if not is_available():
        raise RuntimeError(
            "Tier-1 parallel dispatch is disabled. "
            "Enable with: OMG_PARALLEL_DISPATCH_ENABLED=1 or "
            "settings.json _omg.features.PARALLEL_DISPATCH: true"
        )
