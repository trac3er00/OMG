"""
claude_experimental — Experimental features for OMG (Oh My God).

Tier availability:
  Tier-1: parallel  — Real parallel agent dispatch
  Tier-2: memory    — SQLite-backed episodic/semantic/procedural memory
  Tier-3: patterns  — AST-based pattern intelligence
  Tier-4: integration — OpenAPI tool gen, SSE streaming, telemetry, auto-tuning
"""
from __future__ import annotations

__version__ = "0.1.0-alpha"
__all__ = ["parallel", "memory", "patterns", "integration"]


def tier_availability() -> dict:
    """Return availability status for all 4 tiers."""
    from claude_experimental.parallel import is_available as p_avail
    from claude_experimental.memory import is_available as m_avail
    from claude_experimental.patterns import is_available as pat_avail
    from claude_experimental.integration import is_available as i_avail
    return {
        "parallel": p_avail(),
        "memory": m_avail(),
        "patterns": pat_avail(),
        "integration": i_avail(),
    }
