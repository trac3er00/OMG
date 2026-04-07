from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from typing import TypedDict, cast

import pytest

module_path = Path(__file__).resolve().parents[2] / "runtime" / "intent_classifier.py"
module_spec = spec_from_file_location("runtime.intent_classifier", module_path)
assert module_spec is not None
assert module_spec.loader is not None
intent_classifier = module_from_spec(module_spec)
sys.modules[module_spec.name] = intent_classifier
module_spec.loader.exec_module(intent_classifier)

classify_intent = cast(
    Callable[[str], object],
    getattr(intent_classifier, "classify_intent"),
)
PRODUCT_TYPES = cast(Sequence[str], getattr(intent_classifier, "PRODUCT_TYPES"))


class IntentResult(TypedDict):
    type: str
    confidence: float
    clarification_needed: bool
    clarification_prompt: str | None


def _classify(prompt: str) -> IntentResult:
    return cast(IntentResult, classify_intent(prompt))


TYPE_PROMPTS: dict[str, dict[str, list[str]]] = {
    "saas": {
        "ko": [
            "B2B 구독 SaaS 만들어줘",
            "다중 테넌트 구독 플랫폼이 필요해",
            "software as a service 형태의 제품을 만들고 싶어",
            "구독형 팀 협업 saas를 설계해줘",
            "다중 테넌트 B2B 소프트웨어를 개발해줘",
        ],
        "en": [
            "Build a SaaS for team analytics",
            "Create a multi-tenant subscription platform",
            "I need a B2B software as a service app",
            "Make a subscription SaaS for agencies",
            "Launch a multi-tenant SaaS dashboard",
        ],
    },
    "landing": {
        "ko": [
            "랜딩페이지 만들어줘",
            "포트폴리오 사이트 하나 제작해줘",
            "제품 소개 홈페이지가 필요해",
            "브랜드 웹사이트를 빠르게 만들고 싶어",
            "스타트업 랜딩 사이트를 구성해줘",
        ],
        "en": [
            "Build a landing page for my startup",
            "Create a portfolio website",
            "Make a marketing homepage",
            "I need a product website",
            "Design a landing site for a new app",
        ],
    },
    "ecommerce": {
        "ko": [
            "쇼핑몰 만들어줘",
            "상품 판매 스토어를 구축해줘",
            "커머스 사이트와 장바구니가 필요해",
            "마켓플레이스 형태의 쇼핑 서비스를 만들고 싶어",
            "제품을 판매하는 온라인 스토어를 제작해줘",
        ],
        "en": [
            "Build an ecommerce store",
            "Create a marketplace to sell products",
            "Make a shop with a shopping cart",
            "I need a commerce site for product sales",
            "Launch an online store for handmade goods",
        ],
    },
    "api": {
        "ko": [
            "백엔드 API 서버 만들어줘",
            "REST 엔드포인트가 있는 서버가 필요해",
            "GraphQL 백엔드를 구축해줘",
            "데이터 처리용 API를 설계해줘",
            "서버와 엔드포인트 중심 프로젝트를 만들고 싶어",
        ],
        "en": [
            "Build a backend API server",
            "Create a REST service with endpoints",
            "Make a GraphQL backend",
            "I need a server-side API for mobile apps",
            "Design an endpoint-driven backend service",
        ],
    },
    "bot": {
        "ko": [
            "디스코드 봇 만들어줘",
            "챗봇 어시스턴트를 개발해줘",
            "텔레그램 봇이 필요해",
            "슬랙용 봇을 구축하고 싶어",
            "대화형 어시스턴트 봇을 설계해줘",
        ],
        "en": [
            "Build a Discord bot",
            "Create a chatbot assistant",
            "Make a Telegram bot",
            "I need a Slack assistant bot",
            "Design a customer support chatbot",
        ],
    },
    "admin": {
        "ko": [
            "관리자 대시보드 만들어줘",
            "어드민 패널이 필요해",
            "CRUD 관리 시스템을 구축해줘",
            "운영 관리용 dashboard를 설계해줘",
            "관리자용 패널과 관리 화면을 만들고 싶어",
        ],
        "en": [
            "Build an admin dashboard",
            "Create a management panel",
            "Make a CRUD admin system",
            "I need an operations dashboard",
            "Design a back-office admin panel",
        ],
    },
    "cli": {
        "ko": [
            "CLI 도구 만들어줘",
            "터미널 커맨드 툴이 필요해",
            "TUI 기반 도구를 구축해줘",
            "커맨드라인용 유틸리티를 만들고 싶어",
            "터미널에서 쓰는 command tool을 설계해줘",
        ],
        "en": [
            "Build a CLI tool",
            "Create a terminal command utility",
            "Make a TUI application",
            "I need a command-line tool",
            "Design a terminal productivity app",
        ],
    },
}


ALL_CASES = [
    pytest.param(expected, prompt, id=f"{expected}-{lang}-{index}")
    for expected, prompts_by_language in TYPE_PROMPTS.items()
    for lang, prompts in prompts_by_language.items()
    for index, prompt in enumerate(prompts, start=1)
]


@pytest.mark.parametrize(("expected_type", "prompt"), ALL_CASES)
def test_product_prompts_classify_across_languages(
    expected_type: str, prompt: str
) -> None:
    result = _classify(prompt)
    assert result["type"] == expected_type
    assert result["confidence"] >= 0.7
    assert result["clarification_needed"] is False
    assert result["clarification_prompt"] is None


def test_product_types_constant_contains_all_supported_types() -> None:
    assert tuple(PRODUCT_TYPES) == (
        "saas",
        "landing",
        "ecommerce",
        "api",
        "bot",
        "admin",
        "cli",
    )


def test_result_shape_is_stable() -> None:
    result = _classify("portfolio website for a designer")
    assert set(result) == {
        "type",
        "confidence",
        "clarification_needed",
        "clarification_prompt",
    }
    assert result["type"] in PRODUCT_TYPES
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.parametrize(
    "prompt",
    [
        "Build a SaaS subscription platform with multi-tenant billing",
        "구독형 다중 테넌트 B2B SaaS를 설계해줘",
        "Create a commerce marketplace shop to sell product bundles",
        "REST API backend server with multiple endpoint groups",
        "Discord chatbot assistant bot for support",
        "관리자 대시보드와 CRUD 관리 패널을 만들어줘",
        "CLI terminal command tool with TUI workflows",
    ],
)
def test_three_or_more_keyword_matches_raise_confidence_to_0_9(prompt: str) -> None:
    result = _classify(prompt)
    assert result["confidence"] == 0.9


@pytest.mark.parametrize(
    "prompt",
    [
        "Build a SaaS product",
        "랜딩 페이지 만들어줘",
        "shopping cart 기능이 있는 store를 원해",
        "backend server 필요해",
        "telegram bot 만들어줘",
        "admin dashboard가 필요해",
        "terminal tool 하나 만들어줘",
    ],
)
def test_one_or_two_keyword_matches_score_0_7(prompt: str) -> None:
    result = _classify(prompt)
    assert result["confidence"] == 0.7
    assert result["clarification_needed"] is False


@pytest.mark.parametrize(
    "prompt",
    [
        "뭔가 만들어줘",
        "make something useful",
        "새 프로젝트 아이디어가 필요해",
        "help me build stuff",
    ],
)
def test_zero_keyword_matches_require_clarification(prompt: str) -> None:
    result = _classify(prompt)
    assert result["confidence"] == 0.3
    assert result["clarification_needed"] is True
    assert result["clarification_prompt"]


def test_ambiguous_multitype_prompt_requests_clarification() -> None:
    result = _classify("Build a dashboard admin panel and Discord bot")
    assert result["clarification_needed"] is True
    assert result["confidence"] < 0.7
    prompt = result["clarification_prompt"]
    assert prompt is not None
    assert "admin" in prompt.lower()
    assert "bot" in prompt.lower()


def test_ambiguous_korean_prompt_requests_korean_clarification() -> None:
    result = _classify("쇼핑몰이랑 관리자 대시보드 둘 다 필요해")
    assert result["clarification_needed"] is True
    assert result["confidence"] < 0.7
    assert result["clarification_prompt"] is not None
    assert "어떤" in result["clarification_prompt"]


def test_korean_prompt_gets_korean_clarification_prompt() -> None:
    result = _classify("서비스를 하나 만들고 싶어")
    assert result["clarification_needed"] is True
    assert result["clarification_prompt"] is not None
    assert "어떤" in result["clarification_prompt"]


def test_english_prompt_gets_english_clarification_prompt() -> None:
    result = _classify("I want to build something")
    assert result["clarification_needed"] is True
    assert result["clarification_prompt"] is not None
    assert "Which" in result["clarification_prompt"]


@pytest.mark.parametrize(
    ("prompt", "expected_type"),
    [
        ("한국어 landing page 사이트를 만들어줘", "landing"),
        ("B2B 구독 subscription SaaS 플랫폼", "saas"),
        ("상품 product 판매 store 구축", "ecommerce"),
        ("백엔드 backend API endpoint 설계", "api"),
        ("디스코드 Discord chatbot 봇", "bot"),
        ("관리 admin dashboard 패널", "admin"),
        ("터미널 terminal CLI tool", "cli"),
    ],
)
def test_mixed_language_prompts_are_supported(prompt: str, expected_type: str) -> None:
    result = _classify(prompt)
    assert result["type"] == expected_type
    assert result["confidence"] >= 0.7


def test_non_empty_string_input_never_raises_and_returns_known_type() -> None:
    result = _classify("   \n  website   ")
    assert result["type"] in PRODUCT_TYPES


def test_blank_string_falls_back_to_clarification() -> None:
    result = _classify("")
    assert result["confidence"] == 0.3
    assert result["clarification_needed"] is True
