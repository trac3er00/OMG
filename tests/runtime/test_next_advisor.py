from __future__ import annotations

from importlib import import_module
from typing import Callable, cast

from runtime.next_advisor import Recommendation


next_advisor = import_module("runtime.next_advisor")
recommend_next = cast(
    Callable[[dict[str, float] | None], list[Recommendation]],
    next_advisor.recommend_next,
)
recommend_from_proof_score = cast(
    Callable[[dict[str, object]], list[Recommendation]],
    next_advisor.recommend_from_proof_score,
)


def test_recommend_next_prioritizes_low_security_first() -> None:
    recommendations = recommend_next({"security": 30, "testing": 80})

    assert recommendations
    assert recommendations[0]["dimension"] == "security"
    assert "security" in recommendations[0]["agent"]


def test_recommend_next_returns_empty_list_when_all_known_scores_are_healthy() -> None:
    recommendations = recommend_next(
        {
            "security": 90,
            "testing": 90,
            "docs": 90,
            "architecture": 90,
            "performance": 90,
            "reliability": 90,
        }
    )

    assert recommendations == []


def test_recommend_next_defaults_unknown_scores_to_fifty() -> None:
    recommendations = recommend_next({})

    assert len(recommendations) == 6
    assert all(recommendation["score"] == 50 for recommendation in recommendations)


def test_recommend_next_sorts_recommendations_by_lowest_score_first() -> None:
    recommendations = recommend_next(
        {
            "performance": 65,
            "testing": 25,
            "security": 40,
            "docs": 90,
            "architecture": 75,
            "reliability": 85,
        }
    )

    assert [recommendation["dimension"] for recommendation in recommendations] == [
        "testing",
        "security",
        "performance",
    ]


def test_recommend_next_excludes_scores_at_or_above_threshold() -> None:
    recommendations = recommend_next(
        {
            "security": 69,
            "testing": 70,
            "docs": 71,
            "architecture": 10,
            "performance": 70,
            "reliability": 100,
        }
    )

    assert [recommendation["dimension"] for recommendation in recommendations] == [
        "architecture",
        "security",
    ]


def test_recommend_from_proof_score_returns_evidence_recommendation() -> None:
    recommendations = recommend_from_proof_score({"breakdown": {"completeness": 10}})

    assert recommendations == [
        {
            "agent": "verifier",
            "action": "/OMG:validate",
            "dimension": "evidence",
            "score": 10,
            "impact": "high",
            "reason": "Low evidence completeness",
        }
    ]


def test_recommend_from_proof_score_includes_validity_follow_up() -> None:
    recommendations = recommend_from_proof_score(
        {"breakdown": {"completeness": 50, "validity": 20}}
    )

    assert recommendations == [
        {
            "agent": "test-writer",
            "action": "/OMG:code-review",
            "dimension": "validity",
            "score": 20,
            "impact": "high",
            "reason": "Invalid evidence detected",
        }
    ]
