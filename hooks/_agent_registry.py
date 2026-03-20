#!/usr/bin/env python3
"""Agent Registry — Central dispatch table for OMG domain agents.

Maps domain keywords to agents with model preferences, skills, and MCP tools.
"""
from __future__ import annotations

import json
import os
import shutil


def _claude_config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))


def _load_mcp_servers(path: str) -> dict[str, object]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(config, dict):
        return {}
    servers = config.get("mcpServers", {})
    return servers if isinstance(servers, dict) else {}


# Agent registry: domain → agent config
AGENT_REGISTRY = {
    'frontend-designer': {
        'preferred_model': 'gemini-cli',
        'task_category': 'visual-engineering',
        'skills': ['frontend-design', 'frontend-patterns'],
        'trigger_keywords': {'ui', 'ux', 'css', 'layout', 'responsive', 'visual', 'frontend', 'component', 'style', 'design', 'animation', 'color', 'theme'},
        'mcp_tools': ['chrome-devtools'],
        'description': 'Frontend/UI specialist. Uses Gemini for visual tasks.',
        'agent_file': 'agents/omg-frontend-designer.md',
        'model_version': 'gemini-3.1-pro-preview',
    },
    'backend-engineer': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['backend-patterns', 'api-design'],
        'trigger_keywords': {'api', 'server', 'database', 'logic', 'algorithm', 'backend', 'endpoint', 'route', 'middleware', 'service'},
        'mcp_tools': [],
        'description': 'Backend/logic specialist. Uses Codex for deep reasoning.',
        'agent_file': 'agents/omg-backend-engineer.md',
        'model_version': 'gpt-5.3',
    },
    'api-builder': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['api-design', 'backend-patterns'],
        'trigger_keywords': {'openapi', 'swagger', 'rest', 'graphql', 'api-spec', 'schema', 'contract', 'endpoint-design'},
        'mcp_tools': ['context7'],
        'description': 'API design/build specialist. Contracts, endpoint shape, and versioning.',
        'agent_file': 'agents/omg-api-builder.md',
        'model_version': 'gpt-5.3',
    },
    'security-auditor': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['security-review'],
        'trigger_keywords': {'auth', 'encrypt', 'cors', 'jwt', 'vulnerability', 'security', 'xss', 'csrf', 'injection', 'secret', 'password', 'token'},
        'mcp_tools': ['context7', 'websearch'],
        'description': 'Security specialist. Uses Codex for deep security analysis.',
        'agent_file': 'agents/omg-security-auditor.md',
        'model_version': 'gpt-5.3',
    },
    'database-engineer': {
        'preferred_model': 'codex-cli',
        'task_category': 'unspecified-high',
        'skills': [],
        'trigger_keywords': {'sql', 'migration', 'schema', 'query', 'index', 'database', 'postgres', 'mongo', 'redis', 'orm'},
        'mcp_tools': [],
        'description': 'Database specialist. Schema design, query optimization, migrations.',
        'agent_file': 'agents/omg-database-engineer.md',
        'model_version': 'gpt-5.3',
    },
    'testing-engineer': {
        'preferred_model': 'claude',
        'task_category': 'unspecified-high',
        'skills': ['python-testing', 'e2e-testing'],
        'trigger_keywords': {'test', 'spec', 'coverage', 'fixture', 'mock', 'playwright', 'e2e', 'unit', 'integration', 'pytest', 'jest'},
        'mcp_tools': ['chrome-devtools'],
        'description': 'Testing specialist. Unit tests, integration tests, E2E with Playwright.',
        'agent_file': 'agents/omg-testing-engineer.md',
        'model_version': 'claude-sonnet-4-5',
    },
    'infra-engineer': {
        'preferred_model': 'codex-cli',
        'task_category': 'unspecified-high',
        'skills': ['docker-patterns'],
        'trigger_keywords': {'docker', 'ci', 'cd', 'deploy', 'terraform', 'k8s', 'kubernetes', 'nginx', 'pipeline', 'container', 'cloud'},
        'mcp_tools': [],
        'description': 'Infrastructure specialist. Docker, CI/CD, deployment, cloud.',
        'agent_file': 'agents/omg-infra-engineer.md',
        'model_version': 'gpt-5.3',
    },
    'release-engineer': {
        'preferred_model': 'claude',
        'task_category': 'unspecified-high',
        'skills': [],
        'trigger_keywords': {'release', 'version', 'publish', 'changelog', 'semver', 'tag', 'bump', 'distribute'},
        'mcp_tools': ['context7'],
        'description': 'Release specialist. Versioning, changelogs, release automation, SemVer compliance.',
        'agent_file': 'agents/omg-release-engineer.md',
        'model_version': 'claude-sonnet-4-5',
    },
    # Cognitive modes
    'research-mode': {
        'preferred_model': 'claude',
        'task_category': None,
        'subagent_type': 'librarian',
        'skills': [],
        'trigger_keywords': {'research', 'find', 'how to', 'explain', 'documentation', 'docs', 'lookup'},
        'mcp_tools': ['websearch', 'context7', 'chrome-devtools'],
        'description': 'Research mode. Web search, docs lookup, library exploration.',
        'agent_file': 'agents/omg-research-mode.md',
        'model_version': 'claude-haiku-3-5',
    },
    'architect-mode': {
        'preferred_model': 'claude',
        'task_category': None,
        'subagent_type': 'oracle',
        'skills': [],
        'trigger_keywords': {'architect', 'design', 'plan', 'structure', 'system', 'architecture', 'tradeoff'},
        'mcp_tools': [],
        'description': 'Architecture mode. System design, trade-off analysis.',
        'agent_file': 'agents/omg-architect-mode.md',
        'model_version': 'claude-sonnet-4-5',
    },
     'implement-mode': {
         'preferred_model': 'domain-dependent',
         'task_category': 'deep',
         'skills': [],
         'trigger_keywords': {'implement', 'build', 'create', 'add', 'develop', 'write', 'code'},
         'mcp_tools': [],
         'description': 'Implementation mode. Model chosen based on domain of task.',
         'agent_file': 'agents/omg-implement-mode.md',
         'model_version': 'claude-sonnet-4-5',
     },
    # Bundled agents (Task 2.3)
    'explore': {
        'preferred_model': 'claude',
        'task_category': 'quick',
        'skills': [],
        'trigger_keywords': {'find', 'search', 'grep', 'locate', 'where', 'which', 'lookup', 'explore', 'discover'},
        'mcp_tools': [],
        'description': 'Fast codebase search agent. Read-only: grep, glob, file reading, pattern matching.',
        'agent_file': 'agents/explore.md',
        'model_version': 'claude-haiku-4-5',
        'model_role': 'smol',
        'bundled': True,
    },
    'plan': {
        'preferred_model': 'claude',
        'task_category': 'unspecified-high',
        'skills': [],
        'trigger_keywords': {'plan', 'architect', 'design', 'decompose', 'strategy', 'roadmap', 'breakdown', 'structure'},
        'mcp_tools': [],
        'description': 'Strategic planning agent. Architecture design, task decomposition, risk analysis.',
        'agent_file': 'agents/plan.md',
        'model_version': 'claude-opus-4-5',
        'model_role': 'slow',
        'bundled': True,
    },
    'designer': {
        'preferred_model': 'gemini-cli',
        'task_category': 'visual-engineering',
        'skills': ['frontend-design', 'frontend-patterns'],
        'trigger_keywords': {'component', 'layout', 'accessibility', 'responsive', 'tailwind', 'css', 'aria', 'wcag', 'breakpoint'},
        'mcp_tools': ['chrome-devtools'],
        'description': 'UI/UX design agent. Component design, layout, accessibility, responsive design.',
        'agent_file': 'agents/designer.md',
        'model_version': 'claude-opus-4-5',
        'model_role': 'default',
        'bundled': True,
    },
    'reviewer': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['security-review'],
        'trigger_keywords': {'review', 'audit', 'check', 'inspect', 'critique', 'feedback', 'pr', 'pull-request', 'quality'},
        'mcp_tools': ['context7', 'websearch'],
        'description': 'Code review agent. Security, performance, quality, best practices, test coverage.',
        'agent_file': 'agents/reviewer.md',
        'model_version': 'claude-opus-4-5',
        'model_role': 'slow',
        'bundled': True,
    },
    'task': {
        'preferred_model': 'claude',
        'task_category': 'unspecified-high',
        'skills': [],
        'trigger_keywords': {'fix', 'implement', 'feature', 'bug', 'patch', 'update', 'change', 'modify', 'refactor'},
        'mcp_tools': [],
        'description': 'General task execution agent. Implement features, fix bugs, write tests.',
        'agent_file': 'agents/task.md',
        'model_version': 'claude-opus-4-5',
        'model_role': 'default',
        'bundled': True,
    },
    'quick_task': {
        'preferred_model': 'claude',
        'task_category': 'quick',
        'skills': [],
        'trigger_keywords': {'typo', 'rename', 'label', 'caption', 'spelling', 'minor', 'small', 'quick', 'simple'},
        'mcp_tools': [],
        'description': 'Fast task execution agent. Simple fixes, typo corrections, single-file changes.',
        'agent_file': 'agents/quick_task.md',
        'model_version': 'claude-haiku-4-5',
        'model_role': 'smol',
        'bundled': True,
    },
}

# ═══════════════════════════════════════════════════════════
# Intent-to-Agent Routing Table (Magic Keyword Router)
# Maps LEADER_HINT intents from intentgate-keyword-detector
# to target agent names. None = halt (no agent dispatch).
# ═══════════════════════════════════════════════════════════
INTENT_ROUTING = {
    "INTENT_MAX_EFFORT":  "sisyphus",     # ultrawork → full-effort agent
    "INTENT_AUTONOMOUS":  "sisyphus",     # autopilot → autonomous agent
    "INTENT_LOOP":        "sisyphus",     # ralph → loop agent
    "INTENT_PLAN":        "prometheus",   # plan this → planning agent
    "INTENT_TEST_DRIVEN": "sisyphus",     # tdd → TDD agent
    "INTENT_SEARCH":      "librarian",    # search → search agent
    "INTENT_STOP":        None,           # stop → halt (no agent)
    "INTENT_CRAZY":       "sisyphus",     # crazy → aggressive agent
    # Bundled agent intents (Task 2.3)
    "INTENT_EXPLORE":     "explore",      # explore/find → fast search agent
    "INTENT_REVIEW":      "reviewer",     # review/audit → code review agent
    "INTENT_QUICK":       "quick_task",   # quick/simple → fast task agent
    # Clarification intent (Task 3) — halts mutation-capable execution
    "INTENT_CLARIFICATION": None,         # clarification needed → halt (no agent dispatch)
}

# Core agent model preferences. NOT keyword-matched — used by orchestration pipeline only. model_version is informational (not passed to CLI).
CORE_AGENT_MODELS = {
    'architect': {
        'preferred_model': 'codex-cli',
        'model_version': 'gpt-5.2',
        'task_category': None,
        'description': 'System design + planning + delegation routing.',
        'agent_file': 'agents/omg-architect.md',
    },
    'critic': {
        'preferred_model': 'codex-cli',
        'model_version': 'gpt-5.3',
        'task_category': None,
        'description': 'Code review — 3 perspectives, no LGTM allowed.',
        'agent_file': 'agents/omg-critic.md',
    },
    'executor': {
        'preferred_model': 'claude',
        'model_version': 'claude-sonnet-4-5',
        'task_category': 'deep',
        'description': 'Implements code with evidence, auto-escalates when stuck.',
        'agent_file': 'agents/omg-executor.md',
    },
    'qa-tester': {
        'preferred_model': 'claude',
        'model_version': 'claude-sonnet-4-5',
        'task_category': 'unspecified-high',
        'description': 'User-journey test writer — no boilerplate.',
        'agent_file': 'agents/omg-qa-tester.md',
    },
    'escalation-router': {
        'preferred_model': 'claude',
        'model_version': 'claude-haiku-3-5',
        'task_category': None,
        'description': 'Routes problems to Codex/Gemini/CCG based on domain.',
        'agent_file': 'agents/omg-escalation-router.md',
    },
}

# Cache for model availability (per process)
_model_cache: dict[str, bool] | None = None

def resolve_agent(prompt_keywords: set[str]):
    """Match prompt keywords to best agent. Returns registry entry or None.

    Scoring: count of matching trigger_keywords. Returns highest-scoring agent.
    Ties broken by order in registry (first wins).
    """
    best_agent = None
    best_score = 0
    for name, config in AGENT_REGISTRY.items():
        triggers_raw = config.get('trigger_keywords', set())
        triggers = triggers_raw if isinstance(triggers_raw, set) else set()
        score = len(prompt_keywords & triggers)
        if score > best_score:
            best_score = score
            best_agent = dict(config)
            best_agent['name'] = name
    return best_agent if best_score > 0 else None


def get_dispatch_params(agent_name: str):
    """Get task() parameters for dispatching this agent.

    Returns dict with 'category', 'skills', and optionally 'subagent_type'.
    Falls back to claude if preferred model not available.
    """
    config = AGENT_REGISTRY.get(agent_name, {})
    available = detect_available_models()
    preferred = config.get('preferred_model', 'claude')

    # Resolve model availability
    if preferred == 'gemini-cli' and not available.get('gemini-cli'):
        preferred = 'claude'
    elif preferred == 'codex-cli' and not available.get('codex-cli'):
        preferred = 'claude'
    elif preferred == 'domain-dependent':
        preferred = 'claude'

    params = {
        'category': config.get('task_category', 'unspecified-high'),
        'skills': config.get('skills', []),
        'preferred_model': preferred,
        'available_models': available,
        'model_version': config.get('model_version', 'unknown'),
    }
    if 'subagent_type' in config:
        params['subagent_type'] = config['subagent_type']
    return params


def _provider_to_preferred_model(provider: str) -> str:
    mapping = {
        'codex': 'codex-cli',
        'gemini': 'gemini-cli',
        'kimi': 'kimi-cli',
        'claude': 'claude',
    }
    return mapping.get(provider, 'claude')


def get_provider_with_equalizer(task_text: str, project_dir: str, agent_name: str | None = None):
    config = AGENT_REGISTRY.get(agent_name or '', {})
    available = detect_available_models()

    baseline_preferred = config.get('preferred_model', 'claude')
    if baseline_preferred == 'domain-dependent':
        baseline_preferred = 'claude'
    if baseline_preferred == 'gemini-cli' and not available.get('gemini-cli'):
        baseline_preferred = 'claude'
    if baseline_preferred == 'codex-cli' and not available.get('codex-cli'):
        baseline_preferred = 'claude'

    try:
        from runtime.equalizer import select_provider

        selection = select_provider(task_text=task_text, project_dir=project_dir)
        provider = str(selection.get('provider', 'claude'))
        preferred_model = _provider_to_preferred_model(provider)

        if preferred_model != 'claude' and not available.get(preferred_model, False):
            return {
                'provider': 'claude',
                'preferred_model': 'claude',
                'reason': f"equalizer selected {provider} but model unavailable; fallback baseline",
                'cost_tier': str(selection.get('cost_tier', 'high')),
                'domain_fit': str(selection.get('domain_fit', 'general')),
                'equalizer_applied': False,
            }

        return {
            'provider': provider,
            'preferred_model': preferred_model,
            'reason': str(selection.get('reason', 'equalizer decision')),
            'cost_tier': str(selection.get('cost_tier', 'high')),
            'domain_fit': str(selection.get('domain_fit', 'general')),
            'equalizer_applied': True,
        }
    except Exception as exc:
        return {
            'provider': 'claude',
            'preferred_model': baseline_preferred,
            'reason': f'equalizer unavailable: {exc}',
            'cost_tier': 'high',
            'domain_fit': 'general',
            'equalizer_applied': False,
        }


def detect_available_models() -> dict[str, bool]:
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    result = {'claude': True}  # Claude is always available
    result['codex-cli'] = shutil.which('codex') is not None
    result['gemini-cli'] = shutil.which('gemini') is not None
    result['kimi-cli'] = shutil.which('kimi') is not None
    _model_cache = result
    return result


def discover_mcp_tools() -> list[str]:
    """Read MCP config to find available tool names.

    Checks project-level and user-level Claude MCP configs for mcpServers keys.
    Returns list of server names (not individual tool names).
    """
    mcp_servers = {}
    project_dir = os.getcwd()

    claude_dir = _claude_config_dir()
    for mcp_loc in [
        os.path.join(project_dir, '.mcp.json'),
        os.path.join(claude_dir, '.mcp.json'),
        os.path.join(claude_dir, 'settings.json'),
    ]:
        mcp_servers.update(_load_mcp_servers(mcp_loc))

    return list(mcp_servers.keys())


# --- Custom Agent Loading (Task 2.4) ---


def load_custom_agents_into_registry(project_dir: str = ".") -> int:
    """Load custom agents from user/project dirs into AGENT_REGISTRY.

    If OMG_CUSTOM_AGENTS_ENABLED is disabled, does nothing.
    Uses lazy import of runtime.custom_agent_loader to avoid circular deps.

    Args:
        project_dir: Project directory path.

    Returns:
        Number of custom agents loaded.
    """
    import sys as _sys

    # Check feature flag via env var first (fast path)
    env_val = os.environ.get("OMG_CUSTOM_AGENTS_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return 0

    # If not explicitly enabled via env, check via _common
    if env_val not in ("1", "true", "yes"):
        try:
            from hooks._common import get_feature_flag
            if not get_feature_flag("CUSTOM_AGENTS", default=False):
                return 0
        except ImportError:
            return 0  # Can't check flag → disabled

    # Lazy import custom_agent_loader from runtime/
    _runtime_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'runtime')
    _runtime_dir = os.path.normpath(_runtime_dir)
    if _runtime_dir not in _sys.path:
        _sys.path.insert(0, _runtime_dir)

    try:
        from custom_agent_loader import load_custom_agents  # pyright: ignore[reportMissingImports]
    except ImportError:
        return 0

    custom_agents = load_custom_agents(project_dir)
    count = 0

    for agent in custom_agents:
        if not agent.get("validated", False):
            continue  # Skip invalid agents

        name = agent["name"]
        AGENT_REGISTRY[name] = {
            'preferred_model': 'claude',
            'task_category': 'unspecified-high',
            'skills': [],
            'trigger_keywords': set(),
            'mcp_tools': [],
            'description': agent.get('description', ''),
            'agent_file': agent.get('file', ''),
            'model_version': 'claude-sonnet-4-5',
            'model_role': agent.get('model_role'),
            'source': 'custom',
            'level': agent.get('level', 'unknown'),
            'validated': True,
        }
        count += 1

    return count
