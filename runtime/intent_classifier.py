from __future__ import annotations

import re
from typing import TypedDict


PRODUCT_TYPES = ("saas", "landing", "ecommerce", "api", "bot", "admin", "cli")

KEYWORDS: dict[str, tuple[str, ...]] = {
    "saas": (
        "saas",
        "sass",
        "subscription",
        "multi-tenant",
        "multi tenant",
        "b2b",
        "software as a service",
        "구독",
        "다중 테넌트",
    ),
    "landing": (
        "landing",
        "portfolio",
        "website",
        "site",
        "homepage",
        "포트폴리오",
        "사이트",
        "홈페이지",
        "랜딩",
        "랜딩페이지",
        "랜딩 페이지",
        "웹사이트",
    ),
    "ecommerce": (
        "shop",
        "store",
        "commerce",
        "cart",
        "product",
        "sell",
        "marketplace",
        "쇼핑",
        "상품",
        "판매",
        "스토어",
        "커머스",
        "쇼핑몰",
        "장바구니",
        "마켓플레이스",
    ),
    "api": (
        "api",
        "backend",
        "server",
        "rest",
        "graphql",
        "endpoint",
        "백엔드",
        "서버",
        "엔드포인트",
    ),
    "bot": (
        "bot",
        "chatbot",
        "telegram",
        "discord",
        "slack",
        "assistant",
        "봇",
        "챗봇",
        "어시스턴트",
        "텔레그램",
        "디스코드",
    ),
    "admin": (
        "admin",
        "dashboard",
        "panel",
        "management",
        "crud",
        "어드민",
        "대시보드",
        "관리자",
        "관리",
        "패널",
    ),
    "cli": (
        "cli",
        "command",
        "tool",
        "terminal",
        "tui",
        "커맨드",
        "터미널",
        "도구",
        "커맨드라인",
        "명령줄",
    ),
}

WEAK_KEYWORDS: dict[str, frozenset[str]] = {
    "ecommerce": frozenset({"product"}),
}

DISPLAY_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "saas": "SaaS",
        "landing": "landing page",
        "ecommerce": "ecommerce",
        "api": "API",
        "bot": "bot",
        "admin": "admin dashboard",
        "cli": "CLI",
    },
    "ko": {
        "saas": "SaaS",
        "landing": "랜딩페이지",
        "ecommerce": "이커머스",
        "api": "API",
        "bot": "봇",
        "admin": "관리자 대시보드",
        "cli": "CLI",
    },
}


class IntentResult(TypedDict):
    type: str
    confidence: float
    clarification_needed: bool
    clarification_prompt: str | None


def classify_intent(prompt: str) -> IntentResult:
    normalized_prompt = _normalize(prompt)
    language = _detect_language(prompt)
    scores = _score_prompt(normalized_prompt)

    ranked = sorted(
        scores.items(), key=lambda item: (-item[1], PRODUCT_TYPES.index(item[0]))
    )
    best_type, best_matches = ranked[0]
    second_best_matches = ranked[1][1] if len(ranked) > 1 else 0
    tied_types = [
        intent_type
        for intent_type, score in ranked
        if score == best_matches and score > 0
    ]

    if best_matches == 0:
        return {
            "type": best_type,
            "confidence": 0.3,
            "clarification_needed": True,
            "clarification_prompt": _zero_match_prompt(language),
        }

    if len(tied_types) > 1 or (
        second_best_matches > 0
        and best_matches - second_best_matches <= 1
        and (second_best_matches >= 2 or _has_multi_intent_connector(normalized_prompt))
    ):
        ambiguous_types = (
            tied_types
            if len(tied_types) > 1
            else [
                intent_type
                for intent_type, score in ranked
                if score in {best_matches, second_best_matches} and score > 0
            ]
        )
        return {
            "type": best_type,
            "confidence": 0.5,
            "clarification_needed": True,
            "clarification_prompt": _ambiguous_prompt(language, ambiguous_types[:3]),
        }

    confidence = 0.9 if best_matches >= 3 else 0.7
    return {
        "type": best_type,
        "confidence": confidence,
        "clarification_needed": False,
        "clarification_prompt": None,
    }


def _normalize(prompt: str) -> str:
    return " ".join(prompt.casefold().split())


def _detect_language(prompt: str) -> str:
    return "ko" if any("가" <= char <= "힣" for char in prompt) else "en"


def _score_prompt(normalized_prompt: str) -> dict[str, int]:
    token_set = set(re.findall(r"[a-z0-9-]+", normalized_prompt))
    scores: dict[str, int] = {}
    for intent_type, keywords in KEYWORDS.items():
        matched_keywords = [
            keyword
            for keyword in keywords
            if _keyword_matches(normalized_prompt, token_set, keyword)
        ]
        weak_keywords = WEAK_KEYWORDS.get(intent_type, frozenset())
        strong_matches = [
            keyword for keyword in matched_keywords if keyword not in weak_keywords
        ]
        weak_match_count = sum(
            1 for keyword in matched_keywords if keyword in weak_keywords
        )
        scores[intent_type] = len(strong_matches) + (
            weak_match_count if strong_matches else 0
        )
    return scores


def _keyword_matches(normalized_prompt: str, token_set: set[str], keyword: str) -> bool:
    normalized_keyword = keyword.casefold()
    if any("가" <= char <= "힣" for char in normalized_keyword):
        return normalized_keyword in normalized_prompt
    if " " in normalized_keyword or "-" in normalized_keyword:
        return normalized_keyword in normalized_prompt
    return normalized_keyword in token_set


def _has_multi_intent_connector(normalized_prompt: str) -> bool:
    connectors = (" and ", " both ", " also ", " & ", "이랑", "랑 ", "둘 다")
    return any(connector in normalized_prompt for connector in connectors)


def _zero_match_prompt(language: str) -> str:
    if language == "ko":
        return (
            "어떤 제품을 만들고 싶은지 조금만 더 알려주세요. "
            "SaaS, 랜딩페이지, 이커머스, API, 봇, 관리자 대시보드, CLI 중 무엇에 가까운가요?"
        )

    return (
        "Which product would you like to build? "
        "Please choose SaaS, landing page, ecommerce, API, bot, admin dashboard, or CLI."
    )


def _ambiguous_prompt(language: str, tied_types: list[str]) -> str:
    labels = [
        DISPLAY_LABELS[language].get(intent_type, intent_type)
        for intent_type in tied_types
        if intent_type
    ]
    if language == "ko":
        joined = ", ".join(labels)
        return f"{joined} 신호가 함께 보여요. 어떤 제품 유형이 더 중요한가요?"

    if len(labels) == 2:
        joined = " and ".join(labels)
    else:
        joined = ", ".join(labels[:-1]) + f", and {labels[-1]}"
    return f"I found signals for {joined}. Which product type should I optimize for?"
