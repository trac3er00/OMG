"""Agent selector — dynamically picks the best agents for a task from the full pool.

Reads all agent definitions from agents/*.md, scores each against the problem
statement, and returns the top-N most relevant agents for parallel dispatch.

Used by CCG (pick 3) and deep-plan (pick 5) instead of hardcoded agent lists.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Agent definition loading
# ---------------------------------------------------------------------------

_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

# Agents that should never be auto-selected (routers, meta-agents)
_EXCLUDED_AGENTS = frozenset({
    "omg-escalation-router",
    "omg-implement-mode",
    "omg-architect-mode",
    "quick_task",
})


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter fields from an agent markdown file."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def load_all_agents(agents_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load all agent definitions from the agents directory.

    Returns:
        List of dicts with keys: name, description, model, tools, file, body
    """
    d = agents_dir or _AGENTS_DIR
    agents: list[dict[str, Any]] = []

    if not d.is_dir():
        return agents

    for md_file in sorted(d.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        text = md_file.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(text)
        if not fm.get("name"):
            continue
        # Skip meta-agents
        if md_file.stem in _EXCLUDED_AGENTS:
            continue

        agents.append({
            "name": fm["name"],
            "description": fm.get("description", ""),
            "model": fm.get("model", "claude-sonnet-4-5"),
            "tools": [t.strip() for t in fm.get("tools", "").split(",") if t.strip()],
            "file": str(md_file),
            "body": text,
        })

    return agents


# ---------------------------------------------------------------------------
# Domain keyword taxonomy — maps problem keywords → agent affinity
# ---------------------------------------------------------------------------

# Each entry: keyword → list of (agent_name, weight) tuples
# Higher weight = stronger signal that this agent is relevant
_KEYWORD_AFFINITY: dict[str, list[tuple[str, float]]] = {
    # Architecture & planning
    "architecture": [("plan", 2.0), ("architect", 1.5)],
    "system design": [("plan", 2.0), ("architect", 1.5)],
    "dependency": [("plan", 1.5), ("dependency-analyst", 2.0), ("architect", 1.0)],
    "design": [("plan", 1.5), ("frontend-designer", 1.5), ("designer", 1.5), ("architect", 1.0)],
    "trade-off": [("plan", 2.0), ("architect", 1.5)],
    "component": [("frontend-designer", 1.5), ("designer", 1.5), ("architect", 1.0)],
    "boundary": [("architect", 2.0), ("plan", 1.5), ("api-builder", 1.0)],

    # Backend & API
    "api": [("backend-engineer", 2.0), ("api-builder", 2.0), ("api-tester", 1.5)],
    "endpoint": [("backend-engineer", 2.0), ("api-builder", 1.5), ("api-tester", 1.5)],
    "rest": [("backend-engineer", 2.0), ("api-builder", 2.0)],
    "graphql": [("backend-engineer", 2.0), ("api-builder", 2.0)],
    "middleware": [("backend-engineer", 2.0)],
    "server": [("backend-engineer", 2.0), ("infra-engineer", 1.0)],
    "webhook": [("backend-engineer", 2.0), ("api-builder", 1.0)],
    "caching": [("backend-engineer", 1.5), ("performance-engineer", 2.0)],
    "backend": [("backend-engineer", 2.5)],

    # Frontend & UI
    "ui": [("frontend-designer", 2.5), ("designer", 2.0), ("accessibility-auditor", 1.0)],
    "ux": [("frontend-designer", 2.0), ("designer", 2.0), ("accessibility-auditor", 1.0)],
    "layout": [("frontend-designer", 2.0), ("designer", 2.0)],
    "responsive": [("frontend-designer", 2.0), ("designer", 1.5), ("accessibility-auditor", 1.0)],
    "css": [("frontend-designer", 2.5), ("designer", 2.0)],
    "style": [("frontend-designer", 2.0), ("designer", 1.5)],
    "animation": [("frontend-designer", 2.0)],
    "react": [("frontend-designer", 2.0), ("designer", 1.5)],
    "vue": [("frontend-designer", 2.0), ("designer", 1.5)],
    "svelte": [("frontend-designer", 2.0), ("designer", 1.5)],
    "frontend": [("frontend-designer", 2.5), ("designer", 2.0)],
    "visual": [("frontend-designer", 2.0), ("designer", 2.0)],
    "redesign": [("frontend-designer", 2.5), ("designer", 2.0), ("refactor-agent", 1.0)],
    "dashboard": [("frontend-designer", 2.0), ("designer", 2.0), ("backend-engineer", 1.0)],
    "dark mode": [("frontend-designer", 2.5), ("designer", 2.0)],
    "light mode": [("frontend-designer", 2.0), ("designer", 1.5)],
    "theme": [("frontend-designer", 2.0), ("designer", 2.0), ("config-manager", 1.0)],
    "page": [("frontend-designer", 1.5), ("designer", 1.5)],
    "form": [("frontend-designer", 2.0), ("designer", 1.5), ("accessibility-auditor", 1.0)],
    "button": [("frontend-designer", 2.0), ("designer", 1.5)],
    "modal": [("frontend-designer", 2.0), ("designer", 1.5), ("accessibility-auditor", 1.0)],
    "table": [("frontend-designer", 1.5), ("designer", 1.5)],
    "navigation": [("frontend-designer", 2.0), ("designer", 1.5), ("accessibility-auditor", 1.5)],
    "login": [("frontend-designer", 1.5), ("backend-engineer", 1.5), ("security-auditor", 1.5)],
    "signup": [("frontend-designer", 1.5), ("backend-engineer", 1.5)],

    # Database
    "database": [("database-engineer", 2.5), ("backend-engineer", 1.0)],
    "schema": [("database-engineer", 2.0), ("migration-specialist", 1.5)],
    "query": [("database-engineer", 2.0), ("performance-engineer", 1.5)],
    "migration": [("migration-specialist", 2.5), ("database-engineer", 1.5)],
    "sql": [("database-engineer", 2.5)],
    "index": [("database-engineer", 2.0), ("performance-engineer", 1.5)],
    "orm": [("database-engineer", 2.0), ("backend-engineer", 1.0)],

    # Security
    "security": [("security-auditor", 2.5), ("backend-engineer", 1.0)],
    "authentication": [("security-auditor", 2.0), ("backend-engineer", 1.5)],
    "authorization": [("security-auditor", 2.0), ("backend-engineer", 1.5)],
    "auth": [("security-auditor", 2.0), ("backend-engineer", 1.5)],
    "vulnerability": [("security-auditor", 2.5), ("dependency-analyst", 1.5)],
    "cve": [("security-auditor", 2.0), ("dependency-analyst", 2.0)],
    "injection": [("security-auditor", 2.5)],
    "xss": [("security-auditor", 2.5)],
    "csrf": [("security-auditor", 2.5)],
    "encryption": [("security-auditor", 2.0)],
    "secrets": [("security-auditor", 2.0), ("config-manager", 1.5)],
    "audit": [("security-auditor", 2.0), ("critic", 1.5), ("reviewer", 1.5)],

    # Testing
    "test": [("testing-engineer", 2.0), ("qa-tester", 2.0), ("api-tester", 1.0)],
    "coverage": [("testing-engineer", 2.0), ("qa-tester", 1.5)],
    "tdd": [("testing-engineer", 2.5)],
    "e2e": [("testing-engineer", 2.0), ("qa-tester", 2.0)],
    "integration test": [("testing-engineer", 2.0), ("api-tester", 2.0)],
    "unit test": [("testing-engineer", 2.5)],
    "regression": [("testing-engineer", 2.0), ("qa-tester", 1.5)],
    "fixture": [("testing-engineer", 2.0)],

    # Performance
    "performance": [("performance-engineer", 2.5), ("backend-engineer", 1.0)],
    "optimization": [("performance-engineer", 2.5)],
    "profiling": [("performance-engineer", 2.5)],
    "benchmark": [("performance-engineer", 2.5)],
    "latency": [("performance-engineer", 2.5), ("backend-engineer", 1.0)],
    "throughput": [("performance-engineer", 2.0)],
    "memory": [("performance-engineer", 2.0), ("concurrency-expert", 1.0)],
    "cpu": [("performance-engineer", 2.5)],
    "bottleneck": [("performance-engineer", 2.5), ("debugger", 1.0)],
    "slow": [("performance-engineer", 2.0), ("debugger", 1.5)],
    "bundle size": [("performance-engineer", 2.0), ("frontend-designer", 1.0)],

    # DevOps & Infrastructure
    "ci/cd": [("devops-engineer", 2.5), ("infra-engineer", 1.0)],
    "ci": [("devops-engineer", 2.5)],
    "cd": [("devops-engineer", 2.0)],
    "pipeline": [("devops-engineer", 2.0), ("data-engineer", 1.5)],
    "docker": [("devops-engineer", 2.0), ("infra-engineer", 2.0)],
    "kubernetes": [("infra-engineer", 2.5), ("devops-engineer", 1.5)],
    "k8s": [("infra-engineer", 2.5), ("devops-engineer", 1.5)],
    "terraform": [("infra-engineer", 2.5)],
    "deploy": [("devops-engineer", 2.0), ("infra-engineer", 1.5)],
    "deployment": [("devops-engineer", 2.0), ("infra-engineer", 1.5)],
    "github actions": [("devops-engineer", 2.5)],
    "workflow": [("devops-engineer", 2.0)],
    "monitoring": [("infra-engineer", 2.0), ("log-analyst", 2.0)],
    "infrastructure": [("infra-engineer", 2.5)],

    # Data & ML
    "data": [("data-engineer", 2.0), ("database-engineer", 1.0)],
    "etl": [("data-engineer", 2.5)],
    "data pipeline": [("data-engineer", 2.5), ("devops-engineer", 1.0)],
    "transformation": [("data-engineer", 2.0)],
    "warehouse": [("data-engineer", 2.5)],
    "ml": [("ml-engineer", 2.5)],
    "machine learning": [("ml-engineer", 2.5)],
    "model": [("ml-engineer", 2.0)],
    "training": [("ml-engineer", 2.5)],
    "inference": [("ml-engineer", 2.5)],
    "prediction": [("ml-engineer", 2.0)],
    "feature engineering": [("ml-engineer", 2.0), ("data-engineer", 1.5)],
    "neural": [("ml-engineer", 2.5)],
    "pytorch": [("ml-engineer", 2.5)],
    "tensorflow": [("ml-engineer", 2.5)],

    # Debugging
    "bug": [("debugger", 2.5), ("backend-engineer", 1.0)],
    "fix": [("debugger", 2.0), ("backend-engineer", 1.5)],
    "crash": [("debugger", 2.5)],
    "error": [("debugger", 2.0), ("error-handler", 2.0)],
    "stack trace": [("debugger", 2.5)],
    "traceback": [("debugger", 2.5)],
    "bisect": [("debugger", 2.5), ("code-archeologist", 1.5)],
    "regression": [("debugger", 2.0), ("testing-engineer", 1.5)],
    "reproduce": [("debugger", 2.5)],
    "debug": [("debugger", 2.5)],
    "root cause": [("debugger", 2.5)],

    # Refactoring
    "refactor": [("refactor-agent", 2.5), ("critic", 1.0)],
    "clean up": [("refactor-agent", 2.0)],
    "simplify": [("refactor-agent", 2.0)],
    "duplication": [("refactor-agent", 2.5)],
    "code smell": [("refactor-agent", 2.5)],
    "complexity": [("refactor-agent", 2.0), ("performance-engineer", 1.0)],
    "rename": [("refactor-agent", 2.0)],
    "extract": [("refactor-agent", 2.0)],
    "pattern": [("refactor-agent", 1.5)],

    # Concurrency
    "concurrent": [("concurrency-expert", 2.5)],
    "parallel": [("concurrency-expert", 2.0)],
    "thread": [("concurrency-expert", 2.5)],
    "async": [("concurrency-expert", 2.0), ("backend-engineer", 1.0)],
    "await": [("concurrency-expert", 2.0)],
    "race condition": [("concurrency-expert", 2.5)],
    "deadlock": [("concurrency-expert", 2.5)],
    "lock": [("concurrency-expert", 2.0)],
    "mutex": [("concurrency-expert", 2.5)],
    "semaphore": [("concurrency-expert", 2.5)],
    "atomicity": [("concurrency-expert", 2.5)],

    # Error handling
    "error handling": [("error-handler", 2.5)],
    "retry": [("error-handler", 2.5)],
    "circuit breaker": [("error-handler", 2.5)],
    "fallback": [("error-handler", 2.0)],
    "timeout": [("error-handler", 2.0), ("performance-engineer", 1.0)],
    "graceful degradation": [("error-handler", 2.5)],
    "fault tolerance": [("error-handler", 2.5)],
    "resilience": [("error-handler", 2.0)],

    # Documentation
    "documentation": [("docs-writer", 2.5)],
    "docs": [("docs-writer", 2.5)],
    "readme": [("docs-writer", 2.5)],
    "api docs": [("docs-writer", 2.0), ("api-builder", 1.0)],
    "changelog": [("docs-writer", 2.0), ("release-engineer", 2.0)],
    "guide": [("docs-writer", 2.0)],
    "comment": [("docs-writer", 1.5)],
    "jsdoc": [("docs-writer", 2.0)],
    "docstring": [("docs-writer", 2.0)],

    # Accessibility
    "accessibility": [("accessibility-auditor", 2.5), ("frontend-designer", 1.0)],
    "a11y": [("accessibility-auditor", 2.5)],
    "wcag": [("accessibility-auditor", 2.5)],
    "screen reader": [("accessibility-auditor", 2.5)],
    "aria": [("accessibility-auditor", 2.5)],
    "keyboard navigation": [("accessibility-auditor", 2.5)],
    "contrast": [("accessibility-auditor", 2.0), ("frontend-designer", 1.0)],
    "focus": [("accessibility-auditor", 2.0)],

    # Dependencies
    "dependency": [("dependency-analyst", 2.0)],
    "npm audit": [("dependency-analyst", 2.5)],
    "pip audit": [("dependency-analyst", 2.5)],
    "license": [("dependency-analyst", 2.5)],
    "outdated": [("dependency-analyst", 2.0)],
    "supply chain": [("dependency-analyst", 2.5), ("security-auditor", 1.5)],
    "package": [("dependency-analyst", 1.5)],

    # Configuration
    "config": [("config-manager", 2.5)],
    "configuration": [("config-manager", 2.5)],
    "environment": [("config-manager", 2.0), ("devops-engineer", 1.0)],
    "env": [("config-manager", 2.0)],
    "feature flag": [("config-manager", 2.5)],
    "dotenv": [("config-manager", 2.0)],

    # Logging & observability
    "logging": [("log-analyst", 2.5)],
    "log": [("log-analyst", 2.0)],
    "tracing": [("log-analyst", 2.0)],
    "alerting": [("log-analyst", 2.0), ("infra-engineer", 1.0)],
    "observability": [("log-analyst", 2.5)],
    "structured logging": [("log-analyst", 2.5)],

    # Release
    "release": [("release-engineer", 2.5)],
    "version": [("release-engineer", 2.0), ("migration-specialist", 1.0)],
    "semver": [("release-engineer", 2.5)],
    "tag": [("release-engineer", 2.0)],
    "publish": [("release-engineer", 2.0), ("devops-engineer", 1.0)],

    # Legacy & tech debt
    "legacy": [("code-archeologist", 2.5)],
    "technical debt": [("code-archeologist", 2.5), ("refactor-agent", 1.5)],
    "tech debt": [("code-archeologist", 2.5), ("refactor-agent", 1.5)],
    "dead code": [("code-archeologist", 2.5)],
    "history": [("code-archeologist", 2.0)],
    "git blame": [("code-archeologist", 2.5)],
    "why": [("code-archeologist", 1.5)],
    "archeology": [("code-archeologist", 2.5)],

    # Prototyping
    "prototype": [("prototype-builder", 2.5)],
    "mvp": [("prototype-builder", 2.5)],
    "proof of concept": [("prototype-builder", 2.5)],
    "poc": [("prototype-builder", 2.5)],
    "spike": [("prototype-builder", 2.5)],
    "experiment": [("prototype-builder", 2.0)],
    "demo": [("prototype-builder", 2.0)],
    "quick": [("prototype-builder", 1.5)],

    # Upgrade & migration
    "upgrade": [("migration-specialist", 2.5)],
    "migrate": [("migration-specialist", 2.5)],
    "port": [("migration-specialist", 2.0)],
    "convert": [("migration-specialist", 2.0)],
    "typescript": [("migration-specialist", 1.5), ("frontend-designer", 1.0)],

    # Review
    "review": [("reviewer", 2.5), ("critic", 2.0)],
    "code review": [("reviewer", 2.5), ("critic", 2.0)],
    "pr review": [("reviewer", 2.5)],

    # General implementation
    "implement": [("executor", 2.0), ("backend-engineer", 1.5), ("task", 1.5)],
    "build": [("executor", 2.0), ("task", 1.5)],
    "create": [("executor", 1.5), ("task", 1.5)],
    "add": [("executor", 1.5), ("task", 1.5)],
    "feature": [("executor", 1.5), ("task", 1.5), ("backend-engineer", 1.0)],

    # Research & exploration
    "research": [("research-mode", 2.5), ("explore", 1.5)],
    "explore": [("explore", 2.5), ("research-mode", 1.5)],
    "investigate": [("research-mode", 2.0), ("debugger", 1.5), ("explore", 1.5)],
    "analyze": [("research-mode", 2.0), ("explore", 1.5)],
    "understand": [("explore", 2.0), ("code-archeologist", 1.5)],
}

# Maps agent names to their canonical subagent_type for Agent tool invocation
_AGENT_TO_SUBAGENT_TYPE: dict[str, str] = {
    "plan": "plan",
    "task": "task",
    "designer": "designer",
    "reviewer": "reviewer",
    "explore": "explore",
    "critic": "critic",
    "executor": "executor",
    "architect": "architect",
    "backend-engineer": "backend-engineer",
    "frontend-designer": "frontend-designer",
    "database-engineer": "database-engineer",
    "infra-engineer": "infra-engineer",
    "api-builder": "api-builder",
    "qa-tester": "qa-tester",
    "testing-engineer": "testing-engineer",
    "security-auditor": "security-auditor",
    "research-mode": "research-mode",
    # New agents
    "performance-engineer": "general-purpose",
    "devops-engineer": "general-purpose",
    "data-engineer": "general-purpose",
    "ml-engineer": "general-purpose",
    "docs-writer": "general-purpose",
    "accessibility-auditor": "general-purpose",
    "dependency-analyst": "general-purpose",
    "migration-specialist": "general-purpose",
    "debugger": "general-purpose",
    "refactor-agent": "general-purpose",
    "concurrency-expert": "general-purpose",
    "api-tester": "general-purpose",
    "config-manager": "general-purpose",
    "log-analyst": "general-purpose",
    "release-engineer": "general-purpose",
    "code-archeologist": "general-purpose",
    "error-handler": "general-purpose",
    "prototype-builder": "general-purpose",
}


# ---------------------------------------------------------------------------
# Scoring & selection
# ---------------------------------------------------------------------------

def _description_bonus(agent: dict[str, Any], problem_lower: str) -> float:
    """Give a small bonus if words in the agent's description appear in the problem."""
    desc_words = set(re.findall(r"\b[a-z]{4,}\b", agent["description"].lower()))
    problem_words = set(re.findall(r"\b[a-z]{4,}\b", problem_lower))
    overlap = desc_words & problem_words
    return len(overlap) * 0.3


def score_agents(
    problem: str,
    agents: list[dict[str, Any]] | None = None,
    *,
    file_hints: list[str] | None = None,
) -> list[tuple[dict[str, Any], float]]:
    """Score all agents against a problem statement.

    Args:
        problem: The problem or goal description.
        agents: Agent list (loaded automatically if None).
        file_hints: Optional file paths involved, used for file-type affinity.

    Returns:
        List of (agent, score) tuples sorted by score descending.
    """
    if agents is None:
        agents = load_all_agents()

    problem_lower = problem.lower()

    # Build score map: agent_name → float
    scores: dict[str, float] = {a["name"]: 0.0 for a in agents}

    # 1) Keyword affinity scoring
    for keyword, affinities in _KEYWORD_AFFINITY.items():
        # Match keyword in problem (word boundary for single words)
        if " " in keyword:
            matched = keyword in problem_lower
        else:
            matched = bool(re.search(r"\b" + re.escape(keyword) + r"\b", problem_lower))

        if matched:
            for agent_name, weight in affinities:
                if agent_name in scores:
                    scores[agent_name] += weight

    # 2) Description overlap bonus
    for agent in agents:
        scores[agent["name"]] += _description_bonus(agent, problem_lower)

    # 3) File-type affinity boost
    if file_hints:
        _boost_from_files(scores, file_hints)

    # Sort agents by score descending
    scored = [(a, scores[a["name"]]) for a in agents]
    scored.sort(key=lambda x: (-x[1], x[0]["name"]))

    return scored


def _boost_from_files(scores: dict[str, float], files: list[str]) -> None:
    """Boost agent scores based on file extensions present."""
    exts = {os.path.splitext(f)[1].lower() for f in files}

    backend_exts = {".py", ".go", ".rs", ".java", ".rb", ".php", ".cs"}
    frontend_exts = {".tsx", ".jsx", ".css", ".scss", ".vue", ".svelte", ".html"}
    infra_exts = {".yml", ".yaml", ".toml", ".tf", ".hcl"}
    data_exts = {".sql", ".parquet", ".csv", ".jsonl"}
    test_indicators = any("test" in f.lower() for f in files)

    if exts & backend_exts:
        for name in ("backend-engineer", "debugger", "performance-engineer"):
            if name in scores:
                scores[name] += 1.0
    if exts & frontend_exts:
        for name in ("frontend-designer", "designer", "accessibility-auditor"):
            if name in scores:
                scores[name] += 1.0
    if exts & infra_exts:
        for name in ("devops-engineer", "infra-engineer", "config-manager"):
            if name in scores:
                scores[name] += 1.0
    if exts & data_exts:
        for name in ("data-engineer", "database-engineer"):
            if name in scores:
                scores[name] += 1.0
    if test_indicators:
        for name in ("testing-engineer", "qa-tester", "api-tester"):
            if name in scores:
                scores[name] += 1.0


# ---------------------------------------------------------------------------
# Public API — used by CCG and deep-plan
# ---------------------------------------------------------------------------

def select_agents(
    problem: str,
    n: int = 3,
    *,
    file_hints: list[str] | None = None,
    exclude: list[str] | None = None,
    ensure_diversity: bool = True,
) -> list[dict[str, Any]]:
    """Select the top-N agents for a problem.

    Args:
        problem: The problem or goal description.
        n: Number of agents to select.
        file_hints: Optional file paths for context.
        exclude: Agent names to exclude from selection.
        ensure_diversity: If True, avoid selecting agents with very similar roles.

    Returns:
        List of agent dicts, each with keys: name, description, model, tools,
        file, body, score, subagent_type
    """
    scored = score_agents(problem, file_hints=file_hints)

    # Apply exclusions
    exclude_set = set(exclude or [])
    candidates = [(a, s) for a, s in scored if a["name"] not in exclude_set]

    if ensure_diversity:
        candidates = _diversify(candidates, n)

    selected = []
    for agent, score in candidates[:n]:
        result = dict(agent)
        result["score"] = score
        result["subagent_type"] = _AGENT_TO_SUBAGENT_TYPE.get(
            agent["name"], "general-purpose"
        )
        selected.append(result)

    # Ensure we always return exactly n agents (pad with general ones if needed)
    if len(selected) < n:
        # Add fallback agents
        fallbacks = ["plan", "task", "reviewer", "backend-engineer", "testing-engineer"]
        for fb_name in fallbacks:
            if len(selected) >= n:
                break
            if not any(s["name"] == fb_name for s in selected):
                for agent, score in scored:
                    if agent["name"] == fb_name:
                        result = dict(agent)
                        result["score"] = score
                        result["subagent_type"] = _AGENT_TO_SUBAGENT_TYPE.get(
                            fb_name, "general-purpose"
                        )
                        selected.append(result)
                        break

    return selected[:n]


# Diversity groups — agents that serve similar roles
_DIVERSITY_GROUPS: list[set[str]] = [
    {"frontend-designer", "designer"},
    {"testing-engineer", "qa-tester", "api-tester"},
    {"reviewer", "critic"},
    {"plan", "architect"},
    {"executor", "task"},
    {"infra-engineer", "devops-engineer"},
    {"data-engineer", "database-engineer"},
    {"security-auditor", "dependency-analyst"},
    {"explore", "research-mode", "code-archeologist"},
]


def _diversify(
    candidates: list[tuple[dict[str, Any], float]],
    n: int,
) -> list[tuple[dict[str, Any], float]]:
    """Ensure no more than one agent from each diversity group in top-N."""
    result: list[tuple[dict[str, Any], float]] = []
    used_groups: set[int] = set()

    for agent, score in candidates:
        if len(result) >= n * 2:  # keep a buffer for later filtering
            break

        # Check if this agent's group is already represented
        agent_group = None
        for i, group in enumerate(_DIVERSITY_GROUPS):
            if agent["name"] in group:
                agent_group = i
                break

        if agent_group is not None and agent_group in used_groups:
            continue  # Skip — already have someone from this group

        if agent_group is not None:
            used_groups.add(agent_group)

        result.append((agent, score))

    return result


def format_agent_selection(selected: list[dict[str, Any]]) -> str:
    """Format selected agents as a human-readable summary."""
    lines = ["## Selected Agents\n"]
    for i, agent in enumerate(selected, 1):
        score = agent.get("score", 0)
        lines.append(
            f"{i}. **{agent['name']}** (score: {score:.1f}) — {agent['description']}"
        )
    return "\n".join(lines)


def get_agent_prompt_context(agent: dict[str, Any]) -> str:
    """Extract the agent's constraints and guardrails from its body for injection into prompts."""
    body = agent.get("body", "")
    # Extract everything after the frontmatter
    match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", body, re.DOTALL)
    if match:
        return match.group(1).strip()
    return body.strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 agent_selector.py <problem> [--n N] [--files f1,f2]")
        sys.exit(1)

    problem_arg = sys.argv[1]
    n_agents = 3
    files_arg: list[str] | None = None

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--n" and i + 1 < len(sys.argv):
            n_agents = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--files" and i + 1 < len(sys.argv):
            files_arg = sys.argv[i + 1].split(",")
            i += 2
        else:
            i += 1

    selected = select_agents(problem_arg, n=n_agents, file_hints=files_arg)
    print(format_agent_selection(selected))
    print()
    print(json.dumps(
        [{"name": a["name"], "score": a["score"], "subagent_type": a["subagent_type"]}
         for a in selected],
        indent=2,
    ))
