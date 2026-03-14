"""Rule-based output assertions for OMG guide checks."""
from __future__ import annotations

from typing import Any


def guide_assert(candidate: str, rules: dict[str, Any]) -> dict[str, Any]:
    text = candidate or ""
    lowered = text.lower()
    violations: list[dict[str, str]] = []

    for goal in _as_list(rules.get("goals")):
        if "todo" in goal.lower() and "todo" in lowered:
            violations.append({"rule_type": "goal", "rule": goal, "reason": "candidate still includes TODO markers"})

    for non_goal in _as_list(rules.get("non_goals")):
        if _mentions(lowered, non_goal):
            violations.append({"rule_type": "non_goal", "rule": non_goal, "reason": "candidate mentions an explicit non-goal"})

    for criterion in _as_list(rules.get("acceptance_criteria")):
        if "production-ready" in criterion.lower() and any(token in lowered for token in ("todo", "insecure", "placeholder")):
            violations.append({"rule_type": "acceptance_criteria", "rule": criterion, "reason": "candidate contains non-production wording"})

    return {
        "schema": "GuideAssertionResult",
        "verdict": "fail" if violations else "pass",
        "violations": violations,
        "summary": {
            "rule_count": sum(len(_as_list(rules.get(key))) for key in ("goals", "non_goals", "acceptance_criteria", "architecture_constraints", "style_rules", "risk_appetite")),
            "violation_count": len(violations),
        },
    }


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _mentions(lowered_candidate: str, rule: str) -> bool:
    tokens = [token.lower() for token in rule.split() if len(token) >= 4]
    if not tokens:
        return False
    return all(token in lowered_candidate for token in tokens)
