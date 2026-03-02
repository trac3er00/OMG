#!/usr/bin/env python3
"""Agent Registry — Central dispatch table for OAL domain agents.

Maps domain keywords to agents with model preferences, skills, and MCP tools.
"""
import json
import os
import shutil

# Agent registry: domain → agent config
AGENT_REGISTRY = {
    'frontend-designer': {
        'preferred_model': 'gemini-cli',
        'task_category': 'visual-engineering',
        'skills': ['frontend-design', 'frontend-ui-ux'],
        'trigger_keywords': {'ui', 'ux', 'css', 'layout', 'responsive', 'visual', 'frontend', 'component', 'style', 'design', 'animation', 'color', 'theme'},
        'mcp_tools': ['puppeteer_screenshot', 'puppeteer_navigate'],
        'description': 'Frontend/UI specialist. Uses Gemini for visual tasks.',
        'agent_file': 'agents/oal-frontend-designer.md',
        'model_version': 'gemini-3.1-pro-preview',
    },
    'backend-engineer': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['backend-patterns', 'api-design'],
        'trigger_keywords': {'api', 'server', 'database', 'logic', 'algorithm', 'backend', 'endpoint', 'route', 'middleware', 'service'},
        'mcp_tools': [],
        'description': 'Backend/logic specialist. Uses Codex for deep reasoning.',
        'agent_file': 'agents/oal-backend-engineer.md',
        'model_version': 'gpt-5.3',
    },
    'api-builder': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['api-design', 'backend-patterns'],
        'trigger_keywords': {'openapi', 'swagger', 'rest', 'graphql', 'api-spec', 'schema', 'contract', 'endpoint-design'},
        'mcp_tools': ['context7_query-docs'],
        'description': 'API design/build specialist. Contracts, endpoint shape, and versioning.',
        'agent_file': 'agents/oal-api-builder.md',
        'model_version': 'gpt-5.3',
    },
    'security-auditor': {
        'preferred_model': 'codex-cli',
        'task_category': 'deep',
        'skills': ['security-review'],
        'trigger_keywords': {'auth', 'encrypt', 'cors', 'jwt', 'vulnerability', 'security', 'xss', 'csrf', 'injection', 'secret', 'password', 'token'},
        'mcp_tools': ['sentry_search_issues', 'sentry_get_issue_details'],
        'description': 'Security specialist. Uses Codex for deep security analysis.',
        'agent_file': 'agents/oal-security-auditor.md',
        'model_version': 'gpt-5.3',
    },
    'database-engineer': {
        'preferred_model': 'codex-cli',
        'task_category': 'unspecified-high',
        'skills': [],
        'trigger_keywords': {'sql', 'migration', 'schema', 'query', 'index', 'database', 'postgres', 'mongo', 'redis', 'orm'},
        'mcp_tools': [],
        'description': 'Database specialist. Schema design, query optimization, migrations.',
        'agent_file': 'agents/oal-database-engineer.md',
        'model_version': 'gpt-5.3',
    },
    'testing-engineer': {
        'preferred_model': 'claude',
        'task_category': 'unspecified-high',
        'skills': ['python-testing', 'e2e-testing'],
        'trigger_keywords': {'test', 'spec', 'coverage', 'fixture', 'mock', 'playwright', 'e2e', 'unit', 'integration', 'pytest', 'jest'},
        'mcp_tools': ['puppeteer_navigate', 'puppeteer_screenshot'],
        'description': 'Testing specialist. Unit tests, integration tests, E2E with Playwright.',
        'agent_file': 'agents/oal-testing-engineer.md',
        'model_version': 'claude-sonnet-4-5',
    },
    'infra-engineer': {
        'preferred_model': 'codex-cli',
        'task_category': 'unspecified-high',
        'skills': ['docker-patterns'],
        'trigger_keywords': {'docker', 'ci', 'cd', 'deploy', 'terraform', 'k8s', 'kubernetes', 'nginx', 'pipeline', 'container', 'cloud'},
        'mcp_tools': [],
        'description': 'Infrastructure specialist. Docker, CI/CD, deployment, cloud.',
        'agent_file': 'agents/oal-infra-engineer.md',
        'model_version': 'gpt-5.3',
    },
    # Cognitive modes
    'research-mode': {
        'preferred_model': 'claude',
        'task_category': None,
        'subagent_type': 'librarian',
        'skills': [],
        'trigger_keywords': {'research', 'find', 'how to', 'explain', 'documentation', 'docs', 'lookup'},
        'mcp_tools': ['web_search_exa', 'google_search', 'context7_query-docs'],
        'description': 'Research mode. Web search, docs lookup, library exploration.',
        'agent_file': 'agents/oal-research-mode.md',
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
        'agent_file': 'agents/oal-architect-mode.md',
        'model_version': 'claude-sonnet-4-5',
    },
    'implement-mode': {
        'preferred_model': 'domain-dependent',
        'task_category': 'deep',
        'skills': [],
        'trigger_keywords': {'implement', 'build', 'create', 'add', 'develop', 'write', 'code'},
        'mcp_tools': [],
        'description': 'Implementation mode. Model chosen based on domain of task.',
        'agent_file': 'agents/oal-implement-mode.md',
        'model_version': 'claude-sonnet-4-5',
    },
}

# Core agent model preferences. NOT keyword-matched — used by orchestration pipeline only. model_version is informational (not passed to CLI).
CORE_AGENT_MODELS = {
    'architect': {
        'preferred_model': 'codex-cli',
        'model_version': 'gpt-5.2',
        'task_category': None,
        'description': 'System design + planning + delegation routing.',
        'agent_file': 'agents/oal-architect.md',
    },
    'critic': {
        'preferred_model': 'codex-cli',
        'model_version': 'gpt-5.3',
        'task_category': None,
        'description': 'Code review — 3 perspectives, no LGTM allowed.',
        'agent_file': 'agents/oal-critic.md',
    },
    'executor': {
        'preferred_model': 'claude',
        'model_version': 'claude-sonnet-4-5',
        'task_category': 'deep',
        'description': 'Implements code with evidence, auto-escalates when stuck.',
        'agent_file': 'agents/oal-executor.md',
    },
    'qa-tester': {
        'preferred_model': 'claude',
        'model_version': 'claude-sonnet-4-5',
        'task_category': 'unspecified-high',
        'description': 'User-journey test writer — no boilerplate.',
        'agent_file': 'agents/oal-qa-tester.md',
    },
    'escalation-router': {
        'preferred_model': 'claude',
        'model_version': 'claude-haiku-3-5',
        'task_category': None,
        'description': 'Routes problems to Codex/Gemini/CCG based on domain.',
        'agent_file': 'agents/oal-escalation-router.md',
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


def detect_available_models() -> dict[str, bool]:
    """Check which CLIs are available: codex-cli, gemini-cli.

    Returns dict: {'claude': True, 'codex-cli': bool, 'gemini-cli': bool}
    Caches result per process.
    """
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    result = {'claude': True}  # Claude is always available
    result['codex-cli'] = shutil.which('codex') is not None
    result['gemini-cli'] = shutil.which('gemini') is not None
    _model_cache = result
    return result


def discover_mcp_tools() -> list[str]:
    """Read MCP config to find available tool names.

    Checks ~/.claude/settings.json for mcpServers keys.
    Returns list of server names (not individual tool names).
    """
    settings_path = os.path.expanduser('~/.claude/settings.json')
    if not os.path.exists(settings_path):
        return []
    try:
        with open(settings_path) as f:
            settings = json.load(f)
        mcp_servers = settings.get('mcpServers', {})
        return list(mcp_servers.keys())
    except (json.JSONDecodeError, OSError, KeyError):
        return []
