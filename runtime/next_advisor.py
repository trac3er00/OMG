from __future__ import annotations

from typing import NotRequired, TypedDict


class Recommendation(TypedDict):
    agent: str
    action: str
    dimension: str
    score: float
    impact: str
    reason: str


class ProofScoreBreakdown(TypedDict, total=False):
    completeness: float
    validity: float
    diversity: float
    traceability: float


class ProofScoreResult(TypedDict):
    score: NotRequired[int]
    band: NotRequired[str]
    breakdown: ProofScoreBreakdown


DIMENSION_AGENTS = {
    "security": {
        "agent": "security-reviewer",
        "action": "/OMG:red-team",
        "impact": "high",
    },
    "testing": {
        "agent": "test-writer",
        "action": "/OMG:code-review --focus tests",
        "impact": "high",
    },
    "docs": {
        "agent": "doc-writer",
        "action": "/OMG:learn --topic documentation",
        "impact": "medium",
    },
    "architecture": {
        "agent": "omg-architect",
        "action": "/OMG:deep-plan",
        "impact": "high",
    },
    "performance": {
        "agent": "performance-analyst",
        "action": "/OMG:code-review --focus performance",
        "impact": "medium",
    },
    "reliability": {
        "agent": "verifier",
        "action": "/OMG:validate",
        "impact": "medium",
    },
}

THRESHOLD = 70
DEFAULT_SCORE = 50


def _coerce_breakdown(raw_breakdown: object) -> ProofScoreBreakdown:
    if not isinstance(raw_breakdown, dict):
        return {}

    breakdown: ProofScoreBreakdown = {}
    for key in ("completeness", "validity", "diversity", "traceability"):
        value = raw_breakdown.get(key)
        if isinstance(value, (int, float)):
            breakdown[key] = float(value)
    return breakdown


def recommend_next(health: dict[str, float] | None = None) -> list[Recommendation]:
    health_scores = health or {}
    recommendations: list[Recommendation] = []

    for dimension, config in DIMENSION_AGENTS.items():
        score = health_scores.get(dimension, DEFAULT_SCORE)
        if score >= THRESHOLD:
            continue

        recommendations.append(
            {
                "agent": config["agent"],
                "action": config["action"],
                "dimension": dimension,
                "score": score,
                "impact": config["impact"],
                "reason": f"{dimension} score is {score}/100 - improvement recommended",
            }
        )

    recommendations.sort(key=lambda recommendation: recommendation["score"])
    return recommendations


def recommend_from_proof_score(
    proof_score_result: ProofScoreResult | dict[str, object],
) -> list[Recommendation]:
    breakdown = _coerce_breakdown(proof_score_result.get("breakdown", {}))
    recommendations: list[Recommendation] = []

    completeness = float(breakdown.get("completeness", 100))
    if completeness < 30:
        recommendations.append(
            {
                "agent": "verifier",
                "action": "/OMG:validate",
                "dimension": "evidence",
                "score": completeness,
                "impact": "high",
                "reason": "Low evidence completeness",
            }
        )

    validity = float(breakdown.get("validity", 100))
    if validity < 25:
        recommendations.append(
            {
                "agent": "test-writer",
                "action": "/OMG:code-review",
                "dimension": "validity",
                "score": validity,
                "impact": "high",
                "reason": "Invalid evidence detected",
            }
        )

    return recommendations
