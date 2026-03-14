"""Canonical host/model context-limit registry.

Single authoritative source of truth for context window sizes, output reserves,
preflight counting capability, and compaction fallback strategy across supported
host/model families.

Supported hosts (canonical release-blocking):
    claude   — Anthropic (claude-opus-4-6, claude-sonnet-4-6, etc.)
    codex    — OpenAI (gpt-5.4, gpt-5.2, o3, etc.)
    gemini   — Google (gemini-3.1-pro-preview, gemini-3-flash, etc.)
    kimi     — Moonshot (kimi-k2.5, etc.)

External references (source URLs embedded in comments below):
    Anthropic:  https://docs.anthropic.com/en/docs/about-claude/models/overview
                https://docs.anthropic.com/en/docs/build-with-claude/context-windows
    OpenAI:     https://platform.openai.com/docs/models/gpt-5.4
                https://platform.openai.com/docs/guides/compaction
    Gemini:     https://ai.google.dev/gemini-api/docs/long-context
    Kimi:       https://platform.moonshot.ai/docs/guide/kimi-k2-5-quickstart
"""
from __future__ import annotations

from typing import TypedDict


class ContextLimitEntry(TypedDict):
    """Per-model context limit metadata."""

    context_tokens: int
    """Effective input context window in tokens."""

    output_reserve_tokens: int
    """Max output tokens (reserved from the context window for output)."""

    class_label: str
    """Human-readable class: '1M-class', '400k-class', '256k-class', '200k-class', '128k-class'."""

    preflight_counting: bool
    """Whether provider offers a dedicated token-counting API for pre-flight use."""

    native_compaction: bool
    """Whether provider supports server-side context compaction."""

    compaction_trigger_default: int
    """Default recommended compaction trigger (tokens used), tuned for the class."""

    notes: str
    """Free-text rationale for this entry."""


# ---------------------------------------------------------------------------
# Canonical registry (keyed by model-id prefix or exact model-id)
# ---------------------------------------------------------------------------
# Lookup order: exact match → prefix match → fallback
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ContextLimitEntry] = {
    # ── Anthropic Claude ──────────────────────────────────────────────────
    # Source: https://docs.anthropic.com/en/docs/about-claude/models/overview
    # claude-opus-4-6 and claude-sonnet-4-6 have *native* 1M (no beta header)
    "claude-opus-4-6": {
        "context_tokens": 1_000_000,
        "output_reserve_tokens": 128_000,
        "class_label": "1M-class",
        "preflight_counting": True,   # POST /v1/messages/count_tokens
        "native_compaction": True,    # anthropic-beta: compact-2026-01-12
        "compaction_trigger_default": 150_000,
        "notes": (
            "Native 1M context window. No beta header required for 1M on opus-4-6. "
            "Long-context pricing above 200k. Compaction via compact-2026-01-12 beta header."
        ),
    },
    "claude-sonnet-4-6": {
        "context_tokens": 1_000_000,
        "output_reserve_tokens": 64_000,
        "class_label": "1M-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 150_000,
        "notes": (
            "Native 1M context window. No beta header required for 1M on sonnet-4-6. "
            "Long-context pricing above 200k."
        ),
    },
    # claude-haiku-4-5: 200k only, no 1M option
    "claude-haiku-4-5": {
        "context_tokens": 200_000,
        "output_reserve_tokens": 64_000,
        "class_label": "200k-class",
        "preflight_counting": True,
        "native_compaction": False,   # compact-2026-01-12 not supported on Haiku
        "compaction_trigger_default": 120_000,
        "notes": "200k only. No 1M option. Compaction beta not supported.",
    },
    # claude-sonnet-4-5 and claude-sonnet-4: 200k by default, 1M with Tier 4 + beta header
    "claude-sonnet-4-5": {
        "context_tokens": 200_000,
        "output_reserve_tokens": 64_000,
        "class_label": "200k-class",
        "preflight_counting": True,
        "native_compaction": False,
        "compaction_trigger_default": 120_000,
        "notes": (
            "200k default. 1M available with context-1m-2025-08-07 beta header + Usage Tier 4. "
            "Treated as 200k here unless gated tier is confirmed."
        ),
    },
    # ── OpenAI / Codex ────────────────────────────────────────────────────
    # Source: https://platform.openai.com/docs/models/gpt-5.4
    "gpt-5.4": {
        "context_tokens": 1_050_000,
        "output_reserve_tokens": 128_000,
        "class_label": "1M-class",
        "preflight_counting": True,   # POST /v1/responses/input_tokens
        "native_compaction": True,    # context_management inline + /v1/responses/compact
        "compaction_trigger_default": 200_000,
        "notes": (
            "1,050,000 tokens (not exactly 1M). Long-context price cliff at 272k input tokens. "
            "Compaction item is opaque (encrypted). Do not prune the returned compaction item."
        ),
    },
    "gpt-5.4-pro": {
        "context_tokens": 1_050_000,
        "output_reserve_tokens": 128_000,
        "class_label": "1M-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 200_000,
        "notes": "Max-accuracy variant of gpt-5.4. Same context limits.",
    },
    "gpt-5.2": {
        "context_tokens": 400_000,
        "output_reserve_tokens": 128_000,
        "class_label": "400k-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 250_000,
        "notes": "400k context window.",
    },
    "gpt-5": {
        "context_tokens": 400_000,
        "output_reserve_tokens": 128_000,
        "class_label": "400k-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 250_000,
        "notes": "400k context window.",
    },
    "gpt-4.1": {
        "context_tokens": 1_047_576,
        "output_reserve_tokens": 32_768,
        "class_label": "1M-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 200_000,
        "notes": "1,047,576 token window. 32,768 max output.",
    },
    "o4-mini": {
        "context_tokens": 200_000,
        "output_reserve_tokens": 100_000,
        "class_label": "200k-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 120_000,
        "notes": "Reasoning model. 200k context.",
    },
    "o3": {
        "context_tokens": 200_000,
        "output_reserve_tokens": 100_000,
        "class_label": "200k-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 120_000,
        "notes": "Reasoning model. 200k context.",
    },
    "gpt-4o": {
        "context_tokens": 128_000,
        "output_reserve_tokens": 16_384,
        "class_label": "128k-class",
        "preflight_counting": True,
        "native_compaction": True,
        "compaction_trigger_default": 80_000,
        "notes": "Legacy. 128k context.",
    },
    # ── Google Gemini ─────────────────────────────────────────────────────
    # Source: https://ai.google.dev/gemini-api/docs/long-context
    # NOTE: Gemini 3 Pro was deprecated/shut down March 9, 2026.
    # Use gemini-3.1-pro-preview.
    "gemini-3.1-pro-preview": {
        "context_tokens": 1_048_576,
        "output_reserve_tokens": 65_536,
        "class_label": "1M-class",
        "preflight_counting": True,   # countTokens() SDK method
        "native_compaction": False,   # No server-side compaction API
        "compaction_trigger_default": 150_000,
        "notes": (
            "1,048,576 token context. The 65,536 output limit is shared with the context. "
            "No native compaction. Gemini 3 Pro deprecated March 9, 2026."
        ),
    },
    "gemini-2.5-pro": {
        "context_tokens": 1_048_576,
        "output_reserve_tokens": 65_536,
        "class_label": "1M-class",
        "preflight_counting": True,
        "native_compaction": False,
        "compaction_trigger_default": 150_000,
        "notes": "Still available. 1M context. No native compaction.",
    },
    "gemini-3-flash": {
        "context_tokens": 200_000,
        "output_reserve_tokens": 32_768,
        "class_label": "200k-class",
        "preflight_counting": True,
        "native_compaction": False,
        "compaction_trigger_default": 120_000,
        "notes": "Speed-optimized Gemini variant. 200k context.",
    },
    # ── Moonshot Kimi ─────────────────────────────────────────────────────
    # Source: https://platform.moonshot.ai/docs/guide/kimi-k2-5-quickstart
    # NOTE: Confidence MEDIUM — /docs/api/text-generation returned 404 during research.
    # 256k figure confirmed from official quickstart page for K2.x models.
    # moonshot-v1-128k is the *older* series (not K2).
    "kimi-k2.5": {
        "context_tokens": 256_000,
        "output_reserve_tokens": 32_768,
        "class_label": "256k-class",
        "preflight_counting": False,  # No dedicated token-counting endpoint documented
        "native_compaction": False,   # No server-side compaction
        "compaction_trigger_default": 160_000,
        "notes": (
            "256k context (K2.5 series). OpenAI-compatible API format. "
            "No pre-flight token count endpoint documented. "
            "Do NOT confuse with moonshot-v1-128k (older 128k series)."
        ),
    },
    "kimi-k2-thinking": {
        "context_tokens": 256_000,
        "output_reserve_tokens": 32_768,
        "class_label": "256k-class",
        "preflight_counting": False,
        "native_compaction": False,
        "compaction_trigger_default": 160_000,
        "notes": "Reasoning-mode Kimi. 256k context.",
    },
}

# ---------------------------------------------------------------------------
# Prefix-based lookup table for family matching
# (order matters: more specific prefixes first)
# ---------------------------------------------------------------------------

_PREFIX_TABLE: list[tuple[str, str]] = [
    ("claude-opus-4-6", "claude-opus-4-6"),
    ("claude-sonnet-4-6", "claude-sonnet-4-6"),
    ("claude-haiku-4-5", "claude-haiku-4-5"),
    ("claude-sonnet-4-5", "claude-sonnet-4-5"),
    ("claude-sonnet-4", "claude-sonnet-4-5"),   # treat claude-sonnet-4 like 4-5
    ("claude-opus-4", "claude-haiku-4-5"),       # conservative fallback for older opus
    ("claude-", "claude-haiku-4-5"),             # generic Claude fallback (200k conservative)
    ("gpt-5.4-pro", "gpt-5.4-pro"),
    ("gpt-5.4", "gpt-5.4"),
    ("gpt-5.2", "gpt-5.2"),
    ("gpt-5", "gpt-5"),
    ("gpt-4.1", "gpt-4.1"),
    ("gpt-4o", "gpt-4o"),
    ("o4-mini", "o4-mini"),
    ("o3", "o3"),
    ("o1", "o4-mini"),                          # treat o1 conservatively like o4-mini
    ("gemini-3.1", "gemini-3.1-pro-preview"),
    ("gemini-3-flash", "gemini-3-flash"),
    ("gemini-3", "gemini-3.1-pro-preview"),     # gemini-3.x family → 3.1 limits
    ("gemini-2.5", "gemini-2.5-pro"),
    ("gemini-1.5", "gemini-2.5-pro"),           # 1.5 Pro has larger window; use 2.5 entry as safe floor
    ("gemini-", "gemini-3-flash"),              # generic Gemini fallback (200k conservative)
    ("kimi-k2", "kimi-k2.5"),
    ("kimi-", "kimi-k2.5"),
    ("moonshot-v1", "kimi-k2.5"),              # legacy Kimi
]

# ---------------------------------------------------------------------------
# Conservative fallback for unknown models
# ---------------------------------------------------------------------------

_FALLBACK: ContextLimitEntry = {
    "context_tokens": 128_000,
    "output_reserve_tokens": 8_192,
    "class_label": "128k-class",
    "preflight_counting": False,
    "native_compaction": False,
    "compaction_trigger_default": 80_000,
    "notes": (
        "Unknown model fallback. Conservative 128k limit used to avoid exceeding actual window. "
        "Identify the model ID and add an explicit entry to runtime/context_limits.py."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_model_limits(model_id: str) -> ContextLimitEntry:
    """Return context limit metadata for a model ID.

    Lookup order:
        1. Exact match in ``_REGISTRY``
        2. Prefix match via ``_PREFIX_TABLE``
        3. Conservative fallback (``_FALLBACK``)

    Args:
        model_id: A model identifier string (e.g. ``"claude-sonnet-4-6"``,
                  ``"gpt-5.4"``, ``"gemini-3.1-pro-preview"``).

    Returns:
        A ``ContextLimitEntry`` TypedDict. Always returns a value; never raises.
    """
    normalized = (model_id or "").strip().lower()

    # 1. Exact match
    if normalized in _REGISTRY:
        return _clone_entry(_REGISTRY[normalized])

    # 2. Prefix match (longest prefix first via _PREFIX_TABLE ordering)
    for prefix, registry_key in _PREFIX_TABLE:
        if normalized.startswith(prefix.lower()):
            return _clone_entry(_REGISTRY[registry_key])

    # 3. Fallback
    return _clone_entry(_FALLBACK)


def _clone_entry(entry: ContextLimitEntry) -> ContextLimitEntry:
    return {
        "context_tokens": int(entry["context_tokens"]),
        "output_reserve_tokens": int(entry["output_reserve_tokens"]),
        "class_label": str(entry["class_label"]),
        "preflight_counting": bool(entry["preflight_counting"]),
        "native_compaction": bool(entry["native_compaction"]),
        "compaction_trigger_default": int(entry["compaction_trigger_default"]),
        "notes": str(entry["notes"]),
    }


def is_1m_class(model_id: str) -> bool:
    """Return True if the model has a 1M-token-class context window."""
    return get_model_limits(model_id)["class_label"] == "1M-class"


def compaction_trigger(model_id: str) -> int:
    """Return the recommended compaction trigger threshold in tokens for a model."""
    return get_model_limits(model_id)["compaction_trigger_default"]


def supports_preflight_counting(model_id: str) -> bool:
    """Return True if the provider offers a dedicated pre-flight token-counting API."""
    return get_model_limits(model_id)["preflight_counting"]


def supports_native_compaction(model_id: str) -> bool:
    """Return True if the provider offers server-side context compaction."""
    return get_model_limits(model_id)["native_compaction"]
