"""Backward-compatible alias for evidence requirements registry."""
from __future__ import annotations

from importlib import import_module

_registry = import_module("runtime.evidence_requirements")

EVIDENCE_REQUIREMENTS_BY_PROFILE = getattr(_registry, "EVIDENCE_REQUIREMENTS_BY_PROFILE", {})
FULL_REQUIREMENTS = getattr(_registry, "FULL_REQUIREMENTS", [])
requirements_for_profile = getattr(_registry, "requirements_for_profile")

__all__ = [
    "EVIDENCE_REQUIREMENTS_BY_PROFILE",
    "FULL_REQUIREMENTS",
    "requirements_for_profile",
]
