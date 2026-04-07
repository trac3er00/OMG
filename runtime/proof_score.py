from __future__ import annotations

from typing import Any, TypedDict


class ProofScoreBreakdown(TypedDict):
    completeness: float
    validity: float
    diversity: float
    traceability: float


class ProofScoreResult(TypedDict):
    score: int
    band: str
    breakdown: ProofScoreBreakdown


def compute_score(evidence_list: list[dict[str, Any]] | None) -> ProofScoreResult:
    items = evidence_list if isinstance(evidence_list, list) else []
    if not items:
        return {
            "score": 0,
            "band": "weak",
            "breakdown": {
                "completeness": 0,
                "validity": 0,
                "diversity": 0,
                "traceability": 0,
            },
        }

    total = len(items)
    invalid = sum(1 for item in items if not item.get("valid", True))
    unique_types = len(
        {
            str(item.get("type", "")).strip()
            for item in items
            if str(item.get("type", "")).strip()
        }
    )
    path_backed = sum(1 for item in items if str(item.get("path", "")).strip())

    completeness = min(40, total * 20)
    validity = max(0, 35 - invalid * 20)
    diversity = min(15, unique_types * 7.5)
    traceability = min(10, path_backed * 5)
    score = max(0, min(100, int(completeness + validity + diversity + traceability)))

    return {
        "score": score,
        "band": _to_band(score),
        "breakdown": {
            "completeness": completeness,
            "validity": validity,
            "diversity": diversity,
            "traceability": traceability,
        },
    }


def _to_band(score: int) -> str:
    if score >= 85:
        return "complete"
    if score >= 65:
        return "strong"
    if score >= 40:
        return "developing"
    return "weak"
