"""Internal English reasoning pipeline for OMG.

Detects user input language and ensures internal processing is in English,
while preserving user's language for output. Code identifiers are never translated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict


_KOREAN_RANGE = (0xAC00, 0xD7A3)
_JAPANESE_RANGES = [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF)]
_CHINESE_RANGE = (0x4E00, 0x9FFF)
_FEATURE_FLAG_ENV = "OMG_LANGUAGE_PIPELINE"

# Terms that should never be translated (code identifiers, tech terms)
_PRESERVE_PATTERNS = [
    re.compile(r"\b[a-zA-Z][a-zA-Z0-9_]*\([^)]*\)"),  # function calls
    re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]+\b"),  # identifiers
    re.compile(r"`[^`]+`"),  # backtick-wrapped code
    re.compile(r"```[\s\S]*?```"),  # code blocks
]

SUPPORTED_LANGUAGES = ("korean", "japanese", "chinese", "english", "unknown")


class InternalProcessingPayload(TypedDict):
    internal_text: str
    source_language: str
    preserved_terms: list[str]
    pipeline_active: bool


@dataclass
class LanguageResult:
    language: str  # one of SUPPORTED_LANGUAGES
    confidence: float  # 0.0 - 1.0
    has_code: bool  # contains code identifiers that must be preserved
    preserved_terms: list[str]  # terms that must not be translated


def detect_language(text: str) -> LanguageResult:
    """Detect the primary language of input text."""
    if not text or not text.strip():
        return LanguageResult("english", 0.5, False, [])

    total_chars = len(text.replace(" ", ""))
    if total_chars == 0:
        return LanguageResult("english", 0.5, False, [])

    korean_count = sum(1 for c in text if _KOREAN_RANGE[0] <= ord(c) <= _KOREAN_RANGE[1])
    japanese_count = sum(
        1 for c in text if any(lo <= ord(c) <= hi for lo, hi in _JAPANESE_RANGES)
    )
    chinese_count = max(
        0,
        sum(1 for c in text if _CHINESE_RANGE[0] <= ord(c) <= _CHINESE_RANGE[1])
        - japanese_count,
    )

    preserved: list[str] = []
    for pattern in _PRESERVE_PATTERNS:
        matches = pattern.findall(text)
        preserved.extend(matches[:5])

    has_code = len(preserved) > 0

    max_count = max(korean_count, japanese_count, chinese_count)
    if max_count == 0:
        return LanguageResult("english", 0.9, has_code, preserved[:10])

    if korean_count >= japanese_count and korean_count >= chinese_count:
        confidence = min(0.99, korean_count / total_chars * 3)
        return LanguageResult("korean", confidence, has_code, preserved[:10])
    if japanese_count >= chinese_count:
        confidence = min(0.99, japanese_count / total_chars * 3)
        return LanguageResult("japanese", confidence, has_code, preserved[:10])

    confidence = min(0.99, chinese_count / total_chars * 3)
    return LanguageResult("chinese", confidence, has_code, preserved[:10])


def should_use_pipeline() -> bool:
    """Check if the language pipeline is enabled (default: ON)."""
    import os

    val = os.environ.get(_FEATURE_FLAG_ENV, "1").strip().lower()
    return val not in ("0", "false", "off", "no")


def wrap_for_internal_processing(
    text: str, source_language: str | None = None
) -> InternalProcessingPayload:
    """Prepare text for internal English processing.

    Returns dict with:
    - internal_text: text suitable for internal English processing (with preservation markers)
    - source_language: detected or provided language
    - preserved_terms: list of code identifiers that must not be changed
    - pipeline_active: whether pipeline is active
    """
    if not should_use_pipeline():
        return {
            "internal_text": text,
            "source_language": "english",
            "preserved_terms": [],
            "pipeline_active": False,
        }

    result = detect_language(text)
    lang = source_language or result.language

    if lang in ("korean", "japanese", "chinese"):
        context_hint = (
            f"[Internal processing in English. User language: {lang}. "
            "Preserve code identifiers verbatim.]\n"
        )
        internal_text = context_hint + text
    else:
        internal_text = text

    return {
        "internal_text": internal_text,
        "source_language": lang,
        "preserved_terms": result.preserved_terms,
        "pipeline_active": True,
    }
