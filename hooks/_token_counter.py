#!/usr/bin/env python3
"""Tiered token estimation helpers for OMG hooks."""
from __future__ import annotations

import json
import os
import importlib
import urllib.request
from collections.abc import Iterable

API_URL = "https://api.anthropic.com/v1/messages/count_tokens"
API_MODEL = "claude-3-5-haiku-20241022"

_FEATURE_UI_DISPLAY = "ui_display"
_FEATURE_BUDGET_ENFORCEMENT = "budget_enforcement"
_FEATURE_PREFLIGHT = "preflight"


def _safe_int(value: float) -> int:
    if value <= 0:
        return 0
    return int(value)


def _extract_features(text: str) -> tuple[int, int, int]:
    encoded = text.encode("utf-8")
    byte_count = len(encoded)
    word_count = len(text.split())
    line_count = text.count("\n") + (1 if text else 0)
    return byte_count, word_count, line_count


def _default_coefficients() -> tuple[float, float, float, float]:
    return (1.0, 0.19, 0.75, 1.1)


def _gaussian_solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    if n == 0:
        return None
    try:
        for i in range(n):
            pivot = i
            for r in range(i + 1, n):
                if abs(matrix[r][i]) > abs(matrix[pivot][i]):
                    pivot = r
            if abs(matrix[pivot][i]) < 1e-12:
                return None

            if pivot != i:
                matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
                vector[i], vector[pivot] = vector[pivot], vector[i]

            pivot_val = matrix[i][i]
            for c in range(i, n):
                matrix[i][c] /= pivot_val
            vector[i] /= pivot_val

            for r in range(n):
                if r == i:
                    continue
                factor = matrix[r][i]
                if factor == 0:
                    continue
                for c in range(i, n):
                    matrix[r][c] -= factor * matrix[i][c]
                vector[r] -= factor * vector[i]
        return vector
    except Exception:
        return None


def _fit_linear_coefficients(samples: Iterable[tuple[str, int]]) -> tuple[float, float, float, float]:
    rows: list[list[float]] = []
    targets: list[float] = []
    for text, tokens in samples:
        bcount, wcount, lcount = _extract_features(text)
        rows.append([1.0, float(bcount), float(wcount), float(lcount)])
        targets.append(float(tokens))

    dim = 4
    if len(rows) < dim:
        return _default_coefficients()

    xtx = [[0.0 for _ in range(dim)] for _ in range(dim)]
    xty = [0.0 for _ in range(dim)]
    for row, target in zip(rows, targets):
        for i in range(dim):
            xty[i] += row[i] * target
            for j in range(dim):
                xtx[i][j] += row[i] * row[j]

    solved = _gaussian_solve(xtx, xty)
    if solved is None:
        return _default_coefficients()

    return (float(solved[0]), float(solved[1]), float(solved[2]), float(solved[3]))


_CALIBRATION_SAMPLES: tuple[tuple[str, int], ...] = (
    ("ls", 5),
    ("git status", 7),
    ("echo 'hello world'", 10),
    ("python3 -m pytest tests/hooks/test_feature_flags_v2.py -q", 18),
    ("def hello():\n    return 'world'\n", 24),
    (
        """from pathlib import Path\nfor path in Path('hooks').glob('*.py'):\n    print(path.name)\n""",
        44,
    ),
    (
        """def estimate_tokens(text: str, tier: int = 1) -> int:\n    if tier == 1:\n        return max(1, int(len(text) / 3.5))\n    return 0\n""",
        80,
    ),
    (
        "\n".join(["line with common code and comments" for _ in range(80)]),
        720,
    ),
    (
        "\n".join(["longer source line with punctuation () {} [] == != <= >=" for _ in range(250)]),
        1800,
    ),
)

_COEFFICIENTS = _fit_linear_coefficients(_CALIBRATION_SAMPLES)


def _estimate_tier1(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


def _estimate_tier2(text: str) -> int:
    if not text:
        return 0
    bias, w_bytes, w_words, w_lines = _COEFFICIENTS
    bcount, wcount, lcount = _extract_features(text)
    prediction = bias + (w_bytes * bcount) + (w_words * wcount) + (w_lines * lcount)
    return max(1, _safe_int(prediction))


def _get_anthropic_api_key() -> str | None:
    try:
        store_mod = importlib.import_module("credential_store")
        key = store_mod.get_active_key("anthropic")
        if key:
            return key
    except (ImportError, RuntimeError, ValueError, OSError, AttributeError):
        # Optional: credential_store not available
        return os.environ.get("ANTHROPIC_API_KEY")
    return os.environ.get("ANTHROPIC_API_KEY")


def _estimate_tier3(text: str) -> int:
    if not text:
        return 0

    api_key = _get_anthropic_api_key()
    if not api_key:
        return _estimate_tier2(text)

    payload = {
        "model": API_MODEL,
        "messages": [{"role": "user", "content": text}],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        token_value = parsed.get("input_tokens")
        if isinstance(token_value, int) and token_value >= 0:
            return token_value
    except Exception:
        return _estimate_tier2(text)

    return _estimate_tier2(text)


def auto_select_tier(operation: str, text: str = "") -> int:
    normalized = (operation or "").strip().lower()
    if normalized == _FEATURE_UI_DISPLAY:
        return 1
    if normalized == _FEATURE_BUDGET_ENFORCEMENT:
        return 2
    if normalized == _FEATURE_PREFLIGHT:
        if len(text) >= 8000:
            return 3
        if _estimate_tier2(text) >= 1000:
            return 3
        return 2
    return 1


def estimate_tokens(text: str, tier: int = 1) -> int:
    """Estimate token count with 3 reliability/cost tiers.

    Tier 1: fast heuristic (`len(text)/3.5`).
    Tier 2: calibrated linear model using bytes, words, lines.
    Tier 3: Anthropic count_tokens API with graceful fallback to tier 2.
    """
    try:
        if tier == 1:
            return _estimate_tier1(text)
        if tier == 2:
            return _estimate_tier2(text)
        if tier == 3:
            return _estimate_tier3(text)
        return _estimate_tier1(text)
    except Exception:
        return _estimate_tier1(text)
