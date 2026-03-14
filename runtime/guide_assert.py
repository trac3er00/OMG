"""Rule-based output assertions for OMG guide checks."""
from __future__ import annotations

import re
from typing import Any


def guide_assert(candidate: str, rules: dict[str, Any]) -> dict[str, Any]:
    text = candidate or ""
    lowered = text.lower()
    violations: list[dict[str, str]] = []

    terms_rules = rules.get("terms_guard") if isinstance(rules, dict) else {}
    terms_verdict = terms_guard(text, terms_rules if isinstance(terms_rules, dict) else {})
    if terms_verdict.get("status") != "ok":
        violations.append(
            {
                "rule_type": "terms_guard",
                "rule": "terms_guard",
                "reason": str(terms_verdict.get("reason", "terms_guard_rejected")),
            }
        )

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
        "terms_guard": terms_verdict,
        "summary": {
            "rule_count": sum(len(_as_list(rules.get(key))) for key in ("goals", "non_goals", "acceptance_criteria", "architecture_constraints", "style_rules", "risk_appetite")),
            "violation_count": len(violations),
        },
    }


def terms_guard(input_text: str, rules: dict[str, Any]) -> dict[str, Any]:
    text = str(input_text or "")
    config = rules if isinstance(rules, dict) else {}

    min_length = _as_int(config.get("min_length"))
    max_length = _as_int(config.get("max_length"))
    if min_length is not None and min_length < 0:
        return {"status": "rejected", "reason": "terms_guard_invalid_min_length"}
    if max_length is not None and max_length < 0:
        return {"status": "rejected", "reason": "terms_guard_invalid_max_length"}
    if min_length is not None and max_length is not None and min_length > max_length:
        return {"status": "rejected", "reason": "terms_guard_invalid_length_bounds"}

    allowlist = _as_exact_terms(config.get("allowlist"))
    if config.get("allowlist") is not None and allowlist is None:
        return {"status": "rejected", "reason": "terms_guard_invalid_allowlist"}

    pattern = config.get("pattern")
    if pattern is not None and not isinstance(pattern, str):
        return {"status": "rejected", "reason": "terms_guard_invalid_pattern"}

    deny_patterns = _as_exact_terms(config.get("deny_patterns"))
    if config.get("deny_patterns") is not None and deny_patterns is None:
        return {"status": "rejected", "reason": "terms_guard_invalid_deny_patterns"}

    if min_length is not None and len(text) < min_length:
        return {"status": "rejected", "reason": "terms_guard_too_short"}
    if max_length is not None and len(text) > max_length:
        return {"status": "rejected", "reason": "terms_guard_too_long"}

    if allowlist is not None and text not in allowlist:
        return {"status": "rejected", "reason": "terms_guard_not_in_allowlist"}

    if isinstance(pattern, str) and pattern:
        try:
            if re.fullmatch(pattern, text) is None:
                return {"status": "rejected", "reason": "terms_guard_pattern_mismatch"}
        except re.error:
            return {"status": "rejected", "reason": "terms_guard_invalid_pattern"}

    if deny_patterns:
        for blocked in deny_patterns:
            try:
                if re.search(blocked, text):
                    return {"status": "rejected", "reason": "terms_guard_disallowed_pattern"}
            except re.error:
                return {"status": "rejected", "reason": "terms_guard_invalid_deny_pattern"}

    return {"status": "ok"}


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _mentions(lowered_candidate: str, rule: str) -> bool:
    tokens = [token.lower() for token in rule.split() if len(token) >= 4]
    if not tokens:
        return False
    return all(token in lowered_candidate for token in tokens)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _as_exact_terms(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        token = item.strip()
        if not token:
            return None
        output.append(token)
    return output
