from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


COMPLEXITY_TIERS = ("trivial", "simple", "medium", "complex", "critical")


@dataclass
class ComplexityResult:
    tier: str
    confidence: float
    reasoning: str
    scores: dict[str, float]


def classify(
    task: Mapping[str, object],
    *,
    overrides: Mapping[str, str] | None = None,
) -> ComplexityResult:
    if overrides and "tier" in overrides:
        forced_tier = overrides["tier"]
        if forced_tier in COMPLEXITY_TIERS:
            return ComplexityResult(
                tier=forced_tier,
                confidence=1.0,
                reasoning=f"Forced by override: {forced_tier}",
                scores={},
            )

    scores: dict[str, float] = {}

    files = _coerce_int(task.get("files", 1), default=1)
    if files <= 1:
        scores["scope"] = 0.0
    elif files <= 3:
        scores["scope"] = 0.2
    elif files <= 7:
        scores["scope"] = 0.5
    elif files <= 15:
        scores["scope"] = 0.7
    else:
        scores["scope"] = 1.0

    lines = _coerce_int(task.get("lines_changed", 1), default=1)
    if lines <= 5:
        scores["size"] = 0.0
    elif lines <= 30:
        scores["size"] = 0.2
    elif lines <= 150:
        scores["size"] = 0.5
    elif lines <= 500:
        scores["size"] = 0.7
    else:
        scores["size"] = 1.0

    cross_cutting = _coerce_bool(task.get("cross_cutting", False))
    modules = _coerce_int(task.get("modules", 1), default=1)
    if cross_cutting or modules >= 4:
        scores["coupling"] = 0.8
    elif modules >= 2:
        scores["coupling"] = 0.4
    else:
        scores["coupling"] = 0.0

    risk_indicators = _coerce_str_list(task.get("risk_indicators", []))
    high_risk = {"security", "data_loss", "breaking", "performance", "auth"}
    risk_count = sum(1 for risk in risk_indicators if risk.lower() in high_risk)
    scores["risk"] = min(1.0, risk_count * 0.35)

    task_type = str(task.get("type", "feat")).lower()
    type_scores = {
        "docs": -0.2,
        "test": -0.1,
        "fix": 0.0,
        "feat": 0.1,
        "refactor": 0.2,
        "perf": 0.2,
        "breaking": 0.4,
    }
    scores["type"] = max(0.0, type_scores.get(task_type, 0.0))

    test_req = str(task.get("test_requirements", "unit")).lower()
    test_scores = {"none": 0.0, "unit": 0.1, "integration": 0.3, "e2e": 0.5}
    scores["test_req"] = test_scores.get(test_req, 0.1)

    weights = {
        "scope": 0.30,
        "size": 0.20,
        "coupling": 0.25,
        "risk": 0.20,
        "type": 0.025,
        "test_req": 0.025,
    }
    aggregate = sum(scores.get(key, 0.0) * weight for key, weight in weights.items())

    if aggregate < 0.15:
        tier, confidence = "trivial", min(0.95, 0.95 - aggregate)
    elif aggregate < 0.30:
        tier, confidence = "simple", 0.85
    elif aggregate < 0.55:
        tier, confidence = "medium", 0.80
    elif aggregate < 0.75:
        tier, confidence = "complex", 0.80
    else:
        tier, confidence = "critical", min(0.95, 0.70 + aggregate * 0.25)

    reasoning = (
        f"scope={scores['scope']:.2f}, size={scores['size']:.2f}, "
        f"coupling={scores['coupling']:.2f}, risk={scores['risk']:.2f} "
        f"→ aggregate={aggregate:.2f} → {tier}"
    )

    return ComplexityResult(
        tier=tier,
        confidence=round(confidence, 2),
        reasoning=reasoning,
        scores=scores,
    )


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Iterable):
        return []

    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)

    return result
