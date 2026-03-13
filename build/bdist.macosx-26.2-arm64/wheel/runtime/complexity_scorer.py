from __future__ import annotations

import re


_MULTI_STEP_SIGNALS = (
    "and then",
    "after that",
    "followed by",
    "next",
    "also",
    "그리고",
    "다음에",
    "이후에",
    "또한",
    "하고",
    "그다음",
)

_ACTION_VERBS = (
    "fix",
    "implement",
    "build",
    "create",
    "add",
    "update",
    "refactor",
    "migrate",
    "deploy",
    "rewrite",
    "redesign",
    "수정",
    "구현",
    "만들",
    "추가",
    "리팩토링",
    "배포",
)

_MULTI_COMPONENT_SIGNALS = (
    "entire",
    "all files",
    "whole project",
    "full stack",
    "frontend and backend",
    "client and server",
    "end to end",
    "every",
    "all the",
    "across",
    "전체",
    "모든 파일",
    "풀스택",
    "모두",
    "전부",
    "처음부터 끝까지",
)

_ARCHITECTURE_SIGNALS = (
    "architect",
    "redesign",
    "migration",
    "microservice",
    "monorepo",
    "restructure",
    "overhaul",
    "rewrite from scratch",
    "아키텍처",
    "마이그레이션",
    "재설계",
    "전면 수정",
    "처음부터 다시",
)


def score_complexity(goal: str) -> dict[str, object]:
    normalized_goal = str(goal or "").strip()
    score = _score_goal(normalized_goal)
    category = _categorize_goal(normalized_goal, score)
    governance = {
        "read_first": score >= 3,
        "simplify_only": category in {"trivial", "low"},
        "optimize_only": category == "high",
        "complexity": category,
        "complexity_score": score,
    }
    return {
        "score": score,
        "category": category,
        "governance": governance,
    }


def _score_goal(goal: str) -> int:
    if not goal:
        return 0

    score = 0
    lowered = goal.lower()

    score += sum(1 for signal in _MULTI_STEP_SIGNALS if _signal_matches(signal, goal, lowered=lowered))
    verb_count = sum(1 for signal in _ACTION_VERBS if _signal_matches(signal, goal, lowered=lowered))
    score += min(max(verb_count - 1, 0), 3)
    score += sum(
        2 for signal in _MULTI_COMPONENT_SIGNALS if _signal_matches(signal, goal, lowered=lowered)
    )
    score += sum(2 for signal in _ARCHITECTURE_SIGNALS if _signal_matches(signal, goal, lowered=lowered))

    numbered_items = len(re.findall(r"(?:^|\n)\s*[\d]+[.)]\s", lowered))
    bullet_items = len(re.findall(r"(?:^|\n)\s*[-*]\s", lowered))
    score += min(numbered_items + bullet_items, 5)

    word_count = len(lowered.split())
    if word_count > 80:
        score += 2
    elif word_count > 40:
        score += 1

    return score


def _categorize_goal(goal: str, score: int) -> str:
    if not goal:
        return _score_bucket(score)

    word_count = len(goal.split())
    if word_count >= 25:
        return "high"
    if word_count >= 10:
        return "medium"
    return "low"


def _score_bucket(score: int) -> str:
    if score <= 1:
        return "trivial"
    if score <= 4:
        return "low"
    if score <= 9:
        return "medium"
    return "high"


def _signal_matches(signal: str, text: str, *, lowered: str | None = None) -> bool:
    lowered_text = lowered if lowered is not None else text.lower()
    if re.search(r"[\uac00-\ud7a3]", signal):
        return signal in text
    return re.search(r"\b" + re.escape(signal) + r"\b", lowered_text, re.IGNORECASE) is not None
