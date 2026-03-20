"""Semantic tool discovery — surface the most relevant tools for a task.

MVP uses keyword-based scoring. Future: vector similarity with embeddings.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


# Tool catalog: each entry has keywords, description, and category
_TOOL_CATALOG: list[dict[str, Any]] = [
    # OMG Skills (slash commands)
    {"name": "/OMG:deep-plan", "keywords": ["plan", "architecture", "design", "strategy", "complex", "multi-step"], "category": "planning", "description": "5-track parallel strategic planning"},
    {"name": "/OMG:ccg", "keywords": ["claude", "codex", "gemini", "multi-model", "parallel", "synthesis", "cross-model"], "category": "orchestration", "description": "3-track parallel synthesis using Claude+Codex+Gemini"},
    {"name": "/OMG:escalate codex", "keywords": ["debug", "backend", "security", "algorithm", "root cause", "deep", "auth", "crypto"], "category": "escalation", "description": "Route to Codex for deep backend/security analysis"},
    {"name": "/OMG:escalate gemini", "keywords": ["ui", "ux", "visual", "design", "frontend", "accessibility", "responsive", "css"], "category": "escalation", "description": "Route to Gemini for UI/UX review"},
    {"name": "/OMG:ship", "keywords": ["release", "deploy", "ship", "pr", "evidence", "publish"], "category": "release", "description": "Idea → Evidence → PR flow"},
    {"name": "/OMG:forge", "keywords": ["ml", "model", "train", "evaluate", "experiment", "lab", "prototype"], "category": "labs", "description": "Labs domain-model prototyping"},
    {"name": "/OMG:security-check", "keywords": ["security", "vulnerability", "cve", "audit", "secrets", "injection", "xss"], "category": "security", "description": "Security pipeline with dependency enrichment"},
    {"name": "/OMG:browser", "keywords": ["browser", "playwright", "e2e", "screenshot", "visual", "automation"], "category": "testing", "description": "Browser automation and verification"},
    {"name": "/OMG:issue", "keywords": ["bug", "issue", "triage", "diagnose", "error", "crash", "broken"], "category": "diagnostics", "description": "Active red-team diagnostics and issue triage"},
    {"name": "/OMG:deps", "keywords": ["dependency", "cve", "license", "outdated", "upgrade", "npm", "pip"], "category": "dependencies", "description": "Scan dependencies for CVEs and issues"},
    {"name": "/OMG:arch", "keywords": ["architecture", "diagram", "dependency graph", "visualization", "structure"], "category": "visualization", "description": "Codebase dependency graphs and architecture diagrams"},
    {"name": "/OMG:api-twin", "keywords": ["api", "mock", "fixture", "replay", "contract", "endpoint", "simulation"], "category": "testing", "description": "Contract replay and fixture-based API simulation"},
    {"name": "/OMG:crazy", "keywords": ["complex", "multi-agent", "orchestration", "ambitious", "large", "comprehensive"], "category": "orchestration", "description": "Maximum multi-agent orchestration mode"},
    {"name": "/OMG:validate", "keywords": ["validate", "check", "health", "doctor", "verify", "contract"], "category": "validation", "description": "Full validation — doctor + contract + profile checks"},

    # Built-in Agent types
    {"name": "Agent(testing-engineer)", "keywords": ["test", "coverage", "tdd", "e2e", "integration", "unit test", "regression"], "category": "agent", "description": "Test specialist"},
    {"name": "Agent(security-auditor)", "keywords": ["security", "vulnerability", "audit", "threat", "penetration"], "category": "agent", "description": "Security audit specialist"},
    {"name": "Agent(database-engineer)", "keywords": ["database", "schema", "migration", "query", "sql", "index", "orm"], "category": "agent", "description": "Database specialist"},
    {"name": "Agent(backend-engineer)", "keywords": ["api", "server", "backend", "logic", "integration", "performance"], "category": "agent", "description": "Backend/API specialist"},
    {"name": "Agent(frontend-designer)", "keywords": ["ui", "ux", "frontend", "design", "responsive", "css", "component"], "category": "agent", "description": "Frontend UI/UX specialist"},
    {"name": "Agent(architect)", "keywords": ["architecture", "system design", "planning", "delegation", "routing"], "category": "agent", "description": "System design and planning"},
    {"name": "Agent(reviewer)", "keywords": ["review", "quality", "best practices", "code review", "pr"], "category": "agent", "description": "Code review specialist"},
    {"name": "Agent(infra-engineer)", "keywords": ["deploy", "ci/cd", "docker", "cloud", "monitoring", "infrastructure"], "category": "agent", "description": "Infrastructure specialist"},
]


def _tokenize(text: str) -> set[str]:
    """Extract unique lowercase tokens from text."""
    return set(re.findall(r'\b[a-z][a-z0-9_-]{2,}\b', text.lower()))


def _score_tool(tool: dict[str, Any], prompt_tokens: set[str], prompt_lower: str) -> float:
    """Score a tool's relevance to the prompt."""
    score = 0.0

    # Keyword overlap scoring
    tool_keywords = set(kw.lower() for kw in tool.get("keywords", []))
    for kw in tool_keywords:
        kw_tokens = set(kw.split())
        # Multi-word keyword: check if all tokens present or phrase in prompt
        if len(kw_tokens) > 1:
            if kw in prompt_lower:
                score += 3.0  # Exact multi-word match
            elif kw_tokens.issubset(prompt_tokens):
                score += 2.0  # All tokens present
        else:
            if kw in prompt_tokens:
                score += 2.0  # Single keyword match

    # Description overlap scoring (weaker signal)
    desc_tokens = _tokenize(tool.get("description", ""))
    overlap = desc_tokens & prompt_tokens
    score += len(overlap) * 0.5

    # Name mention bonus
    tool_name = tool["name"].lower()
    if tool_name in prompt_lower or tool_name.replace("/omg:", "") in prompt_lower:
        score += 5.0  # Explicit mention

    return score


def discover_relevant_tools(
    prompt: str,
    *,
    max_results: int = 5,
    min_score: float = 2.0,
    catalog: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Discover the most relevant tools for a given prompt.

    Args:
        prompt: The user's task description
        max_results: Maximum number of tools to return
        min_score: Minimum relevance score to include
        catalog: Optional custom tool catalog (uses built-in if None)

    Returns:
        List of dicts: [{name, score, description, category, reason}, ...]
    """
    tools = catalog or _TOOL_CATALOG
    prompt_lower = prompt.lower()
    prompt_tokens = _tokenize(prompt_lower)

    scored: list[tuple[float, dict[str, Any]]] = []
    for tool in tools:
        score = _score_tool(tool, prompt_tokens, prompt_lower)
        if score >= min_score:
            # Build reason from matched keywords
            matched_kws = [
                kw for kw in tool.get("keywords", [])
                if kw.lower() in prompt_lower or set(kw.lower().split()).issubset(prompt_tokens)
            ]
            scored.append((score, {
                "name": tool["name"],
                "score": round(score, 1),
                "description": tool.get("description", ""),
                "category": tool.get("category", ""),
                "reason": ", ".join(matched_kws[:3]) if matched_kws else "description overlap",
            }))

    # Sort by score descending, enforce diversity (max 2 per category)
    scored.sort(key=lambda x: x[0], reverse=True)
    results: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    for _score, entry in scored:
        cat = entry["category"]
        if category_counts.get(cat, 0) >= 2:
            continue
        category_counts[cat] = category_counts.get(cat, 0) + 1
        results.append(entry)
        if len(results) >= max_results:
            break

    return results


def format_tool_suggestions(tools: list[dict[str, Any]]) -> str:
    """Format tool suggestions for prompt injection."""
    if not tools:
        return ""
    parts = ["@tools-available:"]
    for t in tools:
        parts.append(f"  - {t['name']} — {t['description']} (match: {t['reason']})")
    return "\n".join(parts)
