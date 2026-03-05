"""
claude_experimental — Experimental features for OMG (Oh My God).

Tier availability:
  Tier-1: parallel  — Real parallel agent dispatch
  Tier-2: memory    — SQLite-backed episodic/semantic/procedural memory
  Tier-3: patterns  — AST-based pattern intelligence
  Tier-4: integration — OpenAPI tool gen, SSE streaming, telemetry, auto-tuning
"""
from __future__ import annotations

__version__ = "2.0.0b4"
__all__ = ["parallel", "integration"]


def _safe_is_available(module_name: str) -> bool:
    try:
        module = __import__(module_name, fromlist=["is_available"])
    except ImportError:
        return False

    is_available = getattr(module, "is_available", None)
    if not callable(is_available):
        return False
    return bool(is_available())


def tier_availability() -> dict:
    """Return availability status for all 4 tiers."""

    return {
        "parallel": _safe_is_available("claude_experimental.parallel"),
        "memory": _safe_is_available("claude_experimental.memory"),
        "patterns": _safe_is_available("claude_experimental.patterns"),
        "integration": _safe_is_available("claude_experimental.integration"),
    }
