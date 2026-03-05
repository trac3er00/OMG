"""claude_experimental.patterns — Tier-3: AST-based pattern intelligence and anti-pattern detection."""
from __future__ import annotations


def is_available() -> bool:
    from claude_experimental._flags import get_feature_flag
    return get_feature_flag("PATTERN_INTELLIGENCE", default=False)


def _require_enabled() -> None:
    if not is_available():
        raise RuntimeError(
            "Tier-3 pattern intelligence is disabled. "
            "Enable with: OMG_PATTERN_INTELLIGENCE_ENABLED=1 or "
            "settings.json _omg.features.PATTERN_INTELLIGENCE: true"
        )
