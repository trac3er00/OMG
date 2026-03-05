"""Feature flag lifecycle management — tracks feature flag stages (ALPHA → BETA → STABLE → DEPRECATED)."""
from __future__ import annotations

import sys
from enum import Enum


class LifecycleStage(str, Enum):
    """Feature flag lifecycle stages."""

    ALPHA = "alpha"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class FeatureFlagLifecycle:
    """Tracks feature flag lifecycle stages and provides warnings for alpha/deprecated features."""

    def __init__(self) -> None:
        """Initialize a new lifecycle registry."""
        self._registry: dict[str, dict[str, str]] = {}

    def register(
        self,
        flag_name: str,
        status: str = "alpha",
        since_version: str = "2.0.0-beta.3",
        description: str = "",
    ) -> None:
        """Register a feature flag with its lifecycle status.

        Args:
            flag_name: Name of the feature flag (e.g., 'PARALLEL_DISPATCH')
            status: Lifecycle stage ('alpha', 'beta', 'stable', 'deprecated')
            since_version: Version when this status was set
            description: Human-readable description of the feature
        """
        self._registry[flag_name] = {
            "status": status,
            "since_version": since_version,
            "description": description,
        }

    def check_health(self) -> dict[str, dict[str, str]]:
        """Return health status of all registered features.

        Returns:
            Dict mapping flag_name to {status, since_version, description}
        """
        return {
            flag_name: {
                "status": info["status"],
                "since_version": info["since_version"],
                "description": info["description"],
            }
            for flag_name, info in self._registry.items()
        }

    def use_feature(self, flag_name: str) -> None:
        """Log usage of a feature flag, warning if alpha or deprecated.

        Args:
            flag_name: Name of the feature flag being used
        """
        if flag_name not in self._registry:
            return

        status = self._registry[flag_name]["status"]

        if status == LifecycleStage.ALPHA.value:
            _ = sys.stderr.write(
                f"[OMG ALPHA] Feature '{flag_name}' is alpha. Behavior may change.\n"
            )
        elif status == LifecycleStage.DEPRECATED.value:
            _ = sys.stderr.write(
                f"[OMG DEPRECATED] Feature '{flag_name}' is deprecated. Please migrate.\n"
            )

    def get_registry(self) -> dict[str, dict[str, str]]:
        """Return the complete registry of all registered features.

        Returns:
            Dict mapping flag_name to {status, since_version, description}
        """
        return dict(self._registry)


# Module-level default lifecycle instance with pre-registered experimental flags
_DEFAULT_LIFECYCLE = FeatureFlagLifecycle()

# Pre-register all 5 experimental flags as ALPHA
_DEFAULT_LIFECYCLE.register(
    "PARALLEL_DISPATCH",
    status="alpha",
    since_version="2.0.0-beta.3",
    description="Parallel task dispatch across multiple workers",
)
_DEFAULT_LIFECYCLE.register(
    "EXPERIMENTAL_MEMORY",
    status="alpha",
    since_version="2.0.0-beta.3",
    description="Experimental memory system with semantic/episodic/procedural tiers",
)
_DEFAULT_LIFECYCLE.register(
    "PATTERN_INTELLIGENCE",
    status="alpha",
    since_version="2.0.0-beta.3",
    description="Pattern detection and mining with anti-pattern analysis",
)
_DEFAULT_LIFECYCLE.register(
    "ADVANCED_INTEGRATION",
    status="alpha",
    since_version="2.0.0-beta.3",
    description="Advanced integration features (checkpoints, telemetry, experiments)",
)
_DEFAULT_LIFECYCLE.register(
    "ULTRAWORKER",
    status="alpha",
    since_version="2.0.0-beta.3",
    description="Ultra-high-performance worker pool with dynamic scaling",
)
