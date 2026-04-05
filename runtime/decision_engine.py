"""Smart decision engine for agent selection and routing."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from hooks._agent_registry import detect_available_models, AGENT_REGISTRY


class TaskComplexity(Enum):
    TRIVIAL = 1
    SIMPLE = 2
    MODERATE = 3
    COMPLEX = 4
    EXTREME = 5


@dataclass
class DecisionContext:
    prompt: str
    project_dir: str
    domain_hints: list[str] = field(default_factory=list)
    intent: str | None = None
    history: list[dict] = field(default_factory=list)


@dataclass
class AgentRecommendation:
    agent_name: str
    category: str
    provider: str
    confidence: float
    fallback: list[str] = field(default_factory=list)
    reasoning: str


COMPLEXITY_INDICATORS = {
    TaskComplexity.TRIVIAL: [
        r"typo", r"fix.*spelling", r"rename.*file", r"change.*label",
    ],
    TaskComplexity.SIMPLE: [
        r"simple", r"quick", r"minor", r"small", r"add.*comment",
    ],
    TaskComplexity.MODERATE: [
        r"implement", r"add.*feature", r"refactor", r"fix.*bug",
    ],
    TaskComplexity.COMPLEX: [
        r"design.*system", r"architecture", r"multi.*agent", r"parallel",
        r"security.*audit", r"performance.*optim",
    ],
    TaskComplexity.EXTREME: [
        r"redesign", r"rewrite.*entire", r"machine.*learning",
        r"novel.*algorithm", r"research.*new",
    ],
}

DOMAIN_AGENT_MAP = {
    frozenset(["ui", "ux", "css", "visual", "design", "frontend", "component"]): "frontend-designer",
    frozenset(["api", "rest", "graphql", "endpoint", "contract"]): "api-builder",
    frozenset(["security", "auth", "vulnerability", "audit"]): "security-auditor",
    frozenset(["database", "sql", "migration", "schema"]): "database-engineer",
    frozenset(["test", "spec", "coverage", "e2e"]): "testing-engineer",
    frozenset(["deploy", "docker", "kubernetes", "ci", "cd", "infra"]): "infra-engineer",
    frozenset(["release", "version", "publish", "changelog"]): "release-engineer",
}


def analyze_complexity(prompt: str) -> TaskComplexity:
    prompt_lower = prompt.lower()
    for complexity, patterns in COMPLEXITY_INDICATORS.items():
        for pattern in patterns:
            if re.search(pattern, prompt_lower):
                return complexity
    return TaskComplexity.MODERATE


def extract_domain(prompt: str) -> str | None:
    prompt_lower = prompt.lower()
    words = set(re.findall(r'\b\w+\b', prompt_lower))

    for domain_words, agent_name in DOMAIN_AGENT_MAP.items():
        if domain_words & words:
            return agent_name

    return None


def get_provider_priority() -> list[str]:
    available = detect_available_models()
    priority = []

    if available.get('codex-cli'):
        priority.append('codex')
    if available.get('gemini-cli'):
        priority.append('gemini')
    if available.get('claude-code'):
        priority.append('claude')
    if available.get('claude'):
        priority.append('claude')
    if available.get('opencode-cli'):
        priority.append('opencode')
    if available.get('kimi-cli'):
        priority.append('kimi')
    if available.get('cursor-cli'):
        priority.append('cursor')

    return priority


def map_category_to_provider(category: str, available: dict[str, bool]) -> str:
    category_provider_map = {
        'visual-engineering': ['gemini-cli', 'claude'],
        'deep': ['codex-cli', 'claude'],
        'ultrabrain': ['codex-cli', 'claude'],
        'quick': ['claude', 'opencode-cli'],
    }

    preferred = category_provider_map.get(category, ['claude'])
    for p in preferred:
        if available.get(p):
            return p.replace('-cli', '')

    for p in ['codex', 'gemini', 'claude', 'opencode', 'kimi']:
        if available.get(f'{p}-cli') or available.get(p):
            return p

    return 'claude'


def decide_agent(context: DecisionContext) -> AgentRecommendation:
    complexity = analyze_complexity(context.prompt)
    domain_agent = extract_domain(context.prompt)

    if domain_agent:
        agent_config = AGENT_REGISTRY.get(domain_agent, {})
    else:
        agent_config = {}

    category = agent_config.get('task_category', 'unspecified-high')
    available = detect_available_models()
    provider = map_category_to_provider(category, available)

    confidence = 0.5
    if domain_agent:
        confidence += 0.3
    if complexity == TaskComplexity.TRIVIAL or complexity == TaskComplexity.SIMPLE:
        confidence += 0.1

    fallback = []
    if provider != 'claude':
        fallback.append('claude')
    if provider != 'codex' and available.get('codex-cli'):
        fallback.append('codex')
    if provider != 'gemini' and available.get('gemini-cli'):
        fallback.append('gemini')

    reasoning = f"Complexity={complexity.name}, Domain={domain_agent or 'general'}, Provider={provider}"

    return AgentRecommendation(
        agent_name=domain_agent or 'task',
        category=category,
        provider=provider,
        confidence=confidence,
        fallback=fallback,
        reasoning=reasoning,
    )


def get_fallback_chain(primary_failures: list[str]) -> list[str]:
    available = detect_available_models()
    chain = []

    order = ['claude', 'codex', 'gemini', 'opencode', 'kimi', 'cursor']
    for p in order:
        if p not in primary_failures:
            if available.get(f'{p}-cli') or available.get(p):
                chain.append(p)

    return chain


def should_parallelize(context: DecisionContext) -> bool:
    prompt_lower = context.prompt.lower()
    parallel_indicators = [
        r"parallel", r"concurrent", r"simultaneous",
        r"multiple.*files", r"batch", r"all.*at once",
    ]

    for pattern in parallel_indicators:
        if re.search(pattern, prompt_lower):
            return True

    if analyze_complexity(context.prompt) >= TaskComplexity.COMPLEX:
        return True

    return False
