"""Internal team router for OMG standalone operation."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from typing import Any

from runtime.cli_provider import (
    build_non_interactive_command as _build_non_interactive_command,
    get_cli_contract as _provider_get_cli_contract,
    get_provider as _get_registered_provider,
)
from runtime.mcp_lifecycle import check_memory_server, ensure_memory_server
import runtime.providers  # noqa: F401  # Ensure default providers register on import.

# --- Path resolution (never relies on CWD) ---
_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
_OMG_ROOT = os.path.dirname(_ROUTER_DIR)

_logger = logging.getLogger(__name__)
PACKAGED_PROMPT_MAX_CHARS = 4096
_AGENT_REGISTRY_CACHE: dict[str, dict[str, Any]] | None = None

_HOST_EXECUTION_MATRIX: dict[str, dict[str, Any]] = {
    "claude_native": {
        "provider": "claude",
        "host_mode": "claude_native",
        "native_omg_supported": True,
        "claude_call_supported": False,
        "hooks_supported": True,
        "skills_supported": True,
        "mcp_supported": True,
        "tool_calling_supported": True,
        "policy_mode": "toc_ok",
        "policy_refs": [
            "https://docs.anthropic.com/en/docs/claude-code/legal-and-compliance",
        ],
        "notes": (
            "Claude Code is the primary OMG host. Native hooks, skills, and MCP integration are "
            "supported in this mode."
        ),
    },
    "codex_native": {
        "provider": "codex",
        "host_mode": "codex_native",
        "native_omg_supported": False,
        "claude_call_supported": True,
        "hooks_supported": False,
        "skills_supported": True,
        "mcp_supported": True,
        "tool_calling_supported": True,
        "policy_mode": "toc_ok",
        "policy_refs": [
            "https://developers.openai.com/codex/cli/",
            "https://developers.openai.com/codex/mcp/",
            "https://openai.com/policies/terms-of-use/",
        ],
        "notes": (
            "OpenAI publishes official Codex CLI and MCP docs, so OMG can track Codex as a documented "
            "external host. Native OMG parity still needs runtime compatibility work."
        ),
    },
    "gemini_native": {
        "provider": "gemini",
        "host_mode": "gemini_native",
        "native_omg_supported": False,
        "claude_call_supported": True,
        "hooks_supported": False,
        "skills_supported": False,
        "mcp_supported": True,
        "tool_calling_supported": True,
        "policy_mode": "toc_ok",
        "policy_refs": [
            "https://developers.google.com/gemini-code-assist/docs/gemini-cli",
            "https://policies.google.com/terms?hl=en-US",
            "https://developers.google.com/terms/site-policies",
        ],
        "notes": (
            "Google publishes official Gemini CLI and site-policy docs, so OMG can track Gemini as a "
            "documented external host. Native OMG parity still needs runtime compatibility work."
        ),
    },
    "kimi_native": {
        "provider": "kimi",
        "host_mode": "kimi_native",
        "native_omg_supported": False,
        "claude_call_supported": True,
        "hooks_supported": False,
        "skills_supported": True,
        "mcp_supported": True,
        "tool_calling_supported": True,
        "policy_mode": "manual_review_required",
        "policy_refs": [
            "https://moonshotai.github.io/kimi-cli/en/",
            "https://moonshotai.github.io/kimi-cli/",
            "https://www.kimi.com/",
            "https://www.kimi.com/terms-and-conditions",
            "https://www.kimi.com/privacy-policy",
        ],
        "notes": (
            "Kimi publishes CLI docs and exposes legal links on the official site, but the public ToC "
            "mapping is not yet captured cleanly enough to remove manual review. Native OMG parity also "
            "still needs runtime compatibility work."
        ),
    },
    "claude_dispatch": {
        "provider": "claude",
        "host_mode": "claude_dispatch",
        "native_omg_supported": False,
        "claude_call_supported": True,
        "hooks_supported": True,
        "skills_supported": True,
        "mcp_supported": True,
        "tool_calling_supported": True,
        "policy_mode": "manual_review_required",
        "policy_refs": [
            "https://docs.anthropic.com/en/docs/claude-code/legal-and-compliance",
            "https://openai.com/policies/terms-of-use/",
            "https://policies.google.com/terms",
            "https://moonshotai.github.io/kimi-cli/",
        ],
        "notes": (
            "OMG running in Claude may dispatch external CLIs, but each downstream provider policy "
            "still applies. This mode stays conservative until provider-specific compliance checks are complete."
        ),
    },
}

_CLAUDE_ROLE_TIER_MAP: dict[str, str] = {
    "smol": "haiku",
    "commit": "haiku",
    "default": "sonnet",
    "implement": "sonnet",
    "plan": "opus",
    "slow": "opus",
}

_CLAUDE_TIER_MODEL_MAP: dict[str, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-5",
    "opus": "claude-opus-4-5",
}


def get_host_execution_matrix() -> dict[str, dict[str, Any]]:
    """Return a copy of the host execution and policy matrix."""
    return {host_mode: dict(profile) for host_mode, profile in _HOST_EXECUTION_MATRIX.items()}


def get_host_execution_profile(host_mode: str) -> dict[str, Any] | None:
    """Return a copy of a specific host execution profile or None if missing."""
    profile = _HOST_EXECUTION_MATRIX.get(host_mode)
    return dict(profile) if profile is not None else None


def get_provider_host_parity(provider_name: str) -> dict[str, Any]:
    """Return native/dispatch host capability metadata for a provider or route."""
    normalized = provider_name.strip().lower()
    if normalized == "ccg":
        return {
            "route": "ccg",
            "providers": {
                "codex": get_provider_host_parity("codex"),
                "gemini": get_provider_host_parity("gemini"),
            },
        }

    native_host_mode = "claude_native" if normalized == "claude" else f"{normalized}_native"
    native_host = get_host_execution_profile(native_host_mode) or {}
    dispatch_host = get_host_execution_profile("claude_dispatch") or {}
    return {
        "provider": normalized,
        "native_host": native_host,
        "dispatch_host": dispatch_host,
    }


def get_cli_contract(tool_name: str) -> dict[str, Any] | None:
    """Return a copy of the known CLI contract for a provider."""
    return _provider_get_cli_contract(tool_name)


def build_non_interactive_command(tool_name: str, prompt: str, project_dir: str) -> list[str] | None:
    """Build the current non-interactive command for a provider."""
    return _build_non_interactive_command(tool_name, prompt, project_dir)


@dataclass
class TeamDispatchRequest:
    target: str  # codex | gemini | kimi | ccg | auto
    problem: str
    context: str = ""
    files: list[str] | None = None
    expected_outcome: str = ""


@dataclass
class TeamDispatchResult:
    status: str
    findings: list[str]
    actions: list[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["schema"] = "TeamDispatchResult"
        return out


def _infer_target(problem: str) -> str:
    p = problem.lower()
    # Explicit target keywords should always win.
    ccg_kw = bool(re.search(r"\bccg\b", p)) or "tri-track" in p or "tri track" in p
    gemini_kw = bool(re.search(r"\bgemini\b", p))
    codex_kw = bool(re.search(r"\bcodex\b", p))
    kimi_kw = bool(re.search(r"\bkimi\b", p))

    if kimi_kw:
        return "kimi"
    if ccg_kw or (codex_kw and gemini_kw):
        return "ccg"
    if gemini_kw:
        return "gemini"
    if codex_kw:
        return "codex"

    ui_signals = ["ui", "ux", "layout", "css", "visual", "responsive", "frontend", "accessibility"]
    code_signals = ["auth", "security", "backend", "debug", "performance", "algorithm"]
    kimi_signals = [
        "research",
        "synthesis",
        "synthesize",
        "summary",
        "summarize",
        "compare",
        "notes",
        "local runtime",
        "runtime logs",
        "logs",
        "trace",
        "transcript",
        "long context",
        "long-context",
        "workspace analysis",
        "inspect workspace",
        "inspect runtime",
        "local codebase",
    ]
    ccg_signals = [
        "full-stack",
        "full stack",
        "front-end and back-end",
        "frontend and backend",
        "backend and frontend",
        "cross-functional",
        "review everything",
        "architecture",
        "system design",
        "e2e",
        "end-to-end",
    ]

    ui_hit = any(k in p for k in ui_signals)
    code_hit = any(k in p for k in code_signals)
    kimi_hit = any(k in p for k in kimi_signals)
    ccg_hit = any(k in p for k in ccg_signals)

    if ccg_hit or (ui_hit and code_hit):
        return "ccg"
    if ui_hit:
        return "gemini"
    if kimi_hit and not code_hit:
        return "kimi"
    if code_hit:
        return "codex"
    if kimi_hit:
        return "kimi"
    return "codex"


def _check_tool_available(tool_name: str) -> bool:
    """Return True if *tool_name* is on PATH, else log a warning."""
    if shutil.which(tool_name) is not None:
        return True
    _logger.warning("Tool %r not found on PATH — skipping %s dispatch", tool_name, tool_name)
    return False


def _run_tool(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run an external tool with a mandatory timeout.

    Every subprocess call in the team router MUST go through this helper
    to guarantee the ``timeout`` parameter is always set.
    """
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


_TOOL_MAP: dict[str, str] = {
    "codex": "codex",
    "gemini": "gemini",
    "kimi": "kimi",
}

_INSTALL_HINTS: dict[str, str] = {
    "codex": "Install Codex CLI: npm install -g @openai/codex",
    "gemini": "Install Gemini CLI: npm install -g @google/gemini-cli",
    "kimi": "Install Kimi CLI from https://moonshotai.github.io/kimi-cli/en/",
}

_MODEL_PROVIDER_MAP: dict[str, str] = {
    "codex-cli": "codex",
    "gemini-cli": "gemini",
    "kimi-cli": "kimi",
}


_tmux_mgr: Any = None


def _get_tmux_mgr() -> Any:
    """Return the module-level TmuxSessionManager singleton (lazy init)."""
    global _tmux_mgr
    if _tmux_mgr is None:
        try:
            from runtime.tmux_session_manager import TmuxSessionManager  # pyright: ignore[reportMissingImports]

            _tmux_mgr = TmuxSessionManager()
        except ImportError:
            class _FallbackMgr:  # type: ignore[no-redef]
                def is_tmux_available(self):
                    return False

            _tmux_mgr = _FallbackMgr()
    return _tmux_mgr


def _should_use_tmux() -> bool:
    """Return True only when tmux is usable in this execution context.

    Returns False if:
    - tmux is not installed
    - TERM env var is 'dumb' or empty (non-interactive terminal)
    - Running inside a ThreadPoolExecutor worker thread
    """
    try:
        if not _get_tmux_mgr().is_tmux_available():
            return False
        term = os.environ.get("TERM", "")
        if term in ("dumb", ""):
            return False
        # Detect ThreadPoolExecutor worker threads (named 'ThreadPoolExecutor-N_N')
        thread_name = threading.current_thread().name
        if "ThreadPoolExecutor" in thread_name:
            return False
        return True
    except Exception:
        return False


def _auth_status_command(tool_name: str) -> list[str] | None:
    contract = get_cli_contract(tool_name)
    if contract is None:
        return None
    if contract.get("auth_probe_kind") != "status":
        return None
    command = contract.get("auth_probe")
    if isinstance(command, list):
        return [str(part) for part in command]
    return None


def _check_tool_auth(tool_name: str) -> tuple[bool | None, str]:
    cmd = _auth_status_command(tool_name)
    if cmd is None:
        return None, "auth status check not supported"
    try:
        probe = _run_tool(cmd, timeout=15)
    except subprocess.TimeoutExpired:
        return None, "auth status check timed out"
    except FileNotFoundError:
        return False, "CLI is not installed"
    except Exception as exc:
        return None, f"auth status check failed: {exc}"

    output = f"{probe.stdout}\n{probe.stderr}".lower()
    if probe.returncode == 0:
        if "not logged" in output or "not authenticated" in output or "login required" in output:
            return False, "CLI is installed but not authenticated"
        return True, "CLI is authenticated"

    unsupported_markers = ("unknown command", "unrecognized", "invalid choice", "did you mean")
    if any(marker in output for marker in unsupported_markers):
        return None, "auth status subcommand is unavailable"
    if "not logged" in output or "not authenticated" in output or "login" in output:
        return False, "CLI is installed but not authenticated"
    return None, f"unable to verify auth status (exit={probe.returncode})"


_LEGACY_CHECK_TOOL_AVAILABLE = _check_tool_available
_LEGACY_CHECK_TOOL_AUTH = _check_tool_auth


def _providers_for_target(target: str) -> tuple[str, ...]:
    if target == "ccg":
        return ("codex", "gemini")
    if target in _TOOL_MAP:
        return (target,)
    return tuple()


def _collect_provider_health(provider_name: str) -> dict[str, Any]:
    provider = _get_registered_provider(provider_name)
    legacy_availability_override = _check_tool_available is not _LEGACY_CHECK_TOOL_AVAILABLE
    legacy_auth_override = _check_tool_auth is not _LEGACY_CHECK_TOOL_AUTH

    if provider is not None and not legacy_availability_override:
        available = provider.detect()
    else:
        available = _check_tool_available(provider_name)

    auth_ok: bool | None = None
    auth_message = "CLI is not installed"
    if available:
        if provider is not None and not legacy_auth_override:
            auth_ok, auth_message = provider.check_auth()
        else:
            auth_ok, auth_message = _check_tool_auth(provider_name)

    live_connection = bool(available and auth_ok is True)
    return {
        "available": available,
        "auth_ok": auth_ok,
        "live_connection": live_connection,
        "status_message": auth_message,
        "install_hint": _INSTALL_HINTS.get(provider_name, ""),
    }


def _collect_cli_health(target: str) -> dict[str, dict[str, Any]]:
    return {provider: _collect_provider_health(provider) for provider in _providers_for_target(target)}


def dispatch_team(req: TeamDispatchRequest) -> TeamDispatchResult:
    target = req.target.lower().strip()
    if target == "auto":
        target = _infer_target(req.problem)

    findings = [f"Target router selected: {target}", f"Problem: {req.problem}"]
    if req.files:
        findings.append(f"Focus files: {', '.join(req.files[:8])}")
    if req.expected_outcome:
        findings.append(f"Expected: {req.expected_outcome}")

    cli_health = _collect_cli_health(target)
    for provider, info in cli_health.items():
        if info.get("live_connection"):
            findings.append(f"{provider} live connection: ready")
            continue
        if not info.get("available"):
            findings.append(f"{provider} live connection: missing CLI ({info.get('install_hint', '').strip()})")
            continue
        findings.append(f"{provider} live connection: unavailable ({info.get('status_message', 'unknown status')})")

    actions = []
    if target == "codex":
        actions.extend(
            [
                "Perform deep code-level analysis",
                "Prioritize security and root-cause checks",
                "Return fix strategy with verification commands",
            ]
        )
    elif target == "gemini":
        actions.extend(
            [
                "Perform UI/UX and visual structure review",
                "Return accessibility and responsive design improvements",
                "Return component-level edit suggestions",
            ]
        )
    elif target == "kimi":
        actions.extend(
            [
                "Inspect long-context workspace and runtime evidence",
                "Synthesize logs, traces, and local findings into one diagnosis",
                "Return research-style recommendations with concrete next checks",
            ]
        )
    else:
        actions.extend(
            [
                "Run parallel backend and frontend review tracks",
                "Synthesize cross-cutting findings",
                "Return merged action plan with dependency order",
            ]
        )

    evidence = {
        "target": target,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context_length": len(req.context or ""),
        "file_count": len(req.files or []),
        "cli_health": cli_health,
        "live_connection": all(h.get("live_connection") for h in cli_health.values()) if cli_health else True,
    }

    return TeamDispatchResult(status="ok", findings=findings, actions=actions, evidence=evidence)


def package_prompt(agent_name: str, user_prompt: str, project_dir: str) -> str:
    """Build structured prompt for external CLI dispatch."""
    agent = _get_agent_registry_snapshot().get(agent_name, {})
    description = str(agent.get("description", f"{agent_name} specialist"))
    model_version = str(agent.get("model_version", "not specified"))

    header = (
        f"You are a {description}\n\n"
        f"Model: {model_version}\n"
        f"Project: {project_dir}\n"
        "Task: "
    )
    footer = "\n\nConstraints: Follow existing patterns. No hardcoded secrets. Verify changes."
    task_budget = max(PACKAGED_PROMPT_MAX_CHARS - len(header) - len(footer), 256)
    packaged = f"{header}{_truncate_for_budget(user_prompt, task_budget)}{footer}"
    return _truncate_for_budget(packaged, PACKAGED_PROMPT_MAX_CHARS)


def _clear_agent_registry_cache() -> None:
    """Clear the cached agent registry snapshot used for prompt packaging."""
    global _AGENT_REGISTRY_CACHE
    _AGENT_REGISTRY_CACHE = None


def _truncate_for_budget(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = " [truncated]"
    if max_chars <= len(suffix):
        return suffix[:max_chars]
    return text[: max_chars - len(suffix)] + suffix


def _load_agent_registry_snapshot() -> dict[str, dict[str, Any]]:
    import sys as _sys

    _hooks_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks",
    )
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)
    try:
        from _agent_registry import AGENT_REGISTRY  # pyright: ignore[reportMissingImports]

        snapshot: dict[str, dict[str, Any]] = {}
        for name, raw in AGENT_REGISTRY.items():
            if isinstance(raw, dict):
                snapshot[name] = dict(raw)
        return snapshot
    except Exception:
        return {}


def _get_agent_registry_snapshot() -> dict[str, dict[str, Any]]:
    global _AGENT_REGISTRY_CACHE
    if _AGENT_REGISTRY_CACHE is None:
        _AGENT_REGISTRY_CACHE = _load_agent_registry_snapshot()
    return _AGENT_REGISTRY_CACHE


def _normalize_provider_error(provider_name: str, result: dict[str, Any]) -> dict[str, Any]:
    raw_segments = [
        str(result.get(key, ""))
        for key in ("error", "stderr", "output")
        if result.get(key) not in (None, "")
    ]
    combined = " ".join(raw_segments).lower()
    warning_codes: list[str] = []
    warning_messages: list[str] = []
    additional_recovery_actions: list[str] = []

    raw_stderr = str(result.get("stderr", ""))
    for line in raw_stderr.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if "unknown feature key in config:" not in lowered:
            continue
        if "unsupported_feature_flag" not in warning_codes:
            warning_codes.append("unsupported_feature_flag")
        warning_messages.append(stripped)
        if "remove_incompatible_feature_flags" not in additional_recovery_actions:
            additional_recovery_actions.append("remove_incompatible_feature_flags")

    error_code = None
    if "not found" in combined:
        error_code = "cli_missing"
    elif "gemini_api_key" in combined or "api key" in combined:
        error_code = "missing_env"
    elif "disabled in this account" in combined or "violation of terms of service" in combined:
        error_code = "service_disabled"
    elif "llm not set" in combined or "model not set" in combined:
        error_code = "missing_model"
    elif "mcp" in combined and any(marker in combined for marker in ("unreachable", "connect", "connection", "refused")):
        error_code = "mcp_unreachable"
    elif any(
        marker in combined
        for marker in (
            "not logged",
            "not authenticated",
            "login required",
            "authentication",
            "tokenrefreshfailed",
            "failed to parse server response",
        )
    ):
        error_code = "auth_required"
    elif result.get("error") or result.get("exit_code", 0):
        error_code = "provider_error"

    dependency_state = str(result.get("dependency_state", "")).strip().lower()
    if not dependency_state:
        dependency_state = "unknown"

    timeout_like = any(
        marker in combined
        for marker in (
            " timeout",
            "timed out",
            "timeoutexpired",
            "tmux invocation incomplete",
            "empty output",
            "malformed output",
        )
    )
    empty_success = bool(result.get("model")) and int(result.get("exit_code", 0) or 0) == 0 and not str(result.get("output", "")).strip()

    if error_code is None:
        blocking_class = "ready"
        retryable = True
        recovery_action = "none"
        fallback_provider = ""
        fallback_reason = ""
    elif error_code == "mcp_unreachable" and dependency_state != "ready":
        blocking_class = "mcp_dependency_unavailable"
        retryable = True
        recovery_action = "start_omg_memory_server"
        fallback_provider = "claude"
        fallback_reason = "provider_mcp_unreachable"
    elif error_code == "mcp_unreachable":
        blocking_class = "mcp_unreachable"
        retryable = True
        recovery_action = "inspect_provider_logs"
        fallback_provider = "claude"
        fallback_reason = "provider_mcp_unreachable"
    elif error_code == "service_disabled":
        blocking_class = "service_disabled"
        retryable = False
        recovery_action = "appeal_provider_account"
        fallback_provider = "claude"
        fallback_reason = "provider_service_disabled"
    elif error_code == "missing_env":
        blocking_class = "environment_missing"
        retryable = True
        recovery_action = "set_required_environment"
        fallback_provider = ""
        fallback_reason = ""
    elif error_code == "missing_model":
        blocking_class = "configuration_missing"
        retryable = True
        recovery_action = "configure_default_model"
        fallback_provider = "claude"
        fallback_reason = "provider_configuration_missing"
    elif error_code == "auth_required":
        blocking_class = "authentication_required"
        retryable = True
        recovery_action = "login_to_provider"
        fallback_provider = "claude"
        fallback_reason = "provider_login_required"
    elif error_code == "cli_missing":
        blocking_class = "cli_missing"
        retryable = True
        recovery_action = "install_provider_cli"
        fallback_provider = "claude"
        fallback_reason = "provider_cli_missing"
    else:
        blocking_class = "provider_error"
        retryable = True
        recovery_action = "inspect_provider_logs"
        fallback_provider = "claude"
        fallback_reason = "provider_error"

    fallback_mode = ""
    fallback_trigger_class = ""
    fallback_execution_path = ""
    fallback_decision_source = ""
    if fallback_provider == "claude":
        fallback_mode = "provider_failover"
        fallback_trigger_class = "retry_exhausted" if (timeout_like or empty_success) else "hard_failure"
        fallback_execution_path = "claude_native"
        fallback_decision_source = "team_router"

    normalized = dict(result)
    normalized["provider"] = provider_name
    normalized["host_mode"] = "claude_dispatch"
    normalized["dependency_state"] = dependency_state
    normalized["blocking_class"] = blocking_class
    normalized["retryable"] = retryable
    normalized["recovery_action"] = recovery_action
    normalized["fallback_provider"] = fallback_provider
    normalized["fallback_reason"] = fallback_reason
    normalized["fallback_mode"] = fallback_mode
    normalized["fallback_trigger_class"] = fallback_trigger_class
    normalized["fallback_execution_path"] = fallback_execution_path
    normalized["fallback_decision_source"] = fallback_decision_source
    normalized["warning_codes"] = warning_codes
    normalized["warning_messages"] = warning_messages
    normalized["additional_recovery_actions"] = additional_recovery_actions
    if error_code is not None:
        normalized["error_code"] = error_code
    return normalized


def _agent_registry_entry(agent_name: str) -> dict[str, Any]:
    return dict(_get_agent_registry_snapshot().get(agent_name, {}))


def _infer_claude_fallback_role(agent_name: str, agent: dict[str, Any]) -> str:
    explicit_role = str(agent.get("model_role", "")).strip().lower()
    if explicit_role in _CLAUDE_ROLE_TIER_MAP:
        return explicit_role

    search_text = " ".join(
        [
            agent_name.lower(),
            str(agent.get("task_category", "")).lower(),
            str(agent.get("description", "")).lower(),
            " ".join(str(skill).lower() for skill in agent.get("skills", [])),
        ]
    )
    if any(marker in search_text for marker in ("quick", "smol", "research", "search", "librarian", "typo", "minor", "simple", "commit")):
        return "smol"
    if any(marker in search_text for marker in ("security", "review", "audit", "architect", "architecture", "plan", "oracle", "synthesis")):
        return "slow"
    return "default"


def _claude_tier_for_role(role: str) -> str:
    return _CLAUDE_ROLE_TIER_MAP.get(role, "sonnet")


def _build_claude_fallback(
    agent_name: str,
    agent: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    fallback_reason: str = "provider_error",
    fallback_trigger_class: str = "hard_failure",
) -> dict[str, Any]:
    role = _infer_claude_fallback_role(agent_name, agent)
    tier = _claude_tier_for_role(role)

    payload = dict(base or {})
    payload["fallback"] = "claude"
    payload["fallback_provider"] = "claude"
    payload["fallback_reason"] = fallback_reason
    payload["fallback_mode"] = "provider_failover"
    payload["fallback_trigger_class"] = fallback_trigger_class
    payload["fallback_agent_name"] = agent_name
    payload["fallback_model_tier"] = tier
    payload["fallback_model_role"] = role
    payload["fallback_preserved_skills"] = list(agent.get("skills", []))
    payload["fallback_execution_path"] = "claude_native"
    payload["fallback_decision_source"] = "team_router"
    payload["fallback_model_version"] = _CLAUDE_TIER_MODEL_MAP.get(tier, "claude-sonnet-4-5")
    payload.setdefault("host_mode", "claude_native")
    payload.setdefault("category", agent.get("task_category", "deep"))
    payload.setdefault("skills", list(agent.get("skills", [])))
    return payload


def _collect_claude_tier_mix(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    tiers: dict[str, list[str]] = {"haiku": [], "sonnet": [], "opus": []}
    for row in results:
        if row.get("fallback") != "claude":
            continue
        tier = str(row.get("fallback_model_tier", "sonnet")).strip().lower() or "sonnet"
        agent_name = str(row.get("agent", "unknown"))
        tiers.setdefault(tier, []).append(agent_name)
    return tiers


def _invoke_provider(provider_name: str, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    provider = _get_registered_provider(provider_name)
    if provider is None:
        return _normalize_provider_error(
            provider_name,
            {"error": f"{provider_name}-cli provider not registered", "fallback": "claude"},
        )

    dependency_state = "not_required"
    mcp_server: dict[str, Any] | None = None
    try:
        ensure_result = ensure_memory_server()
        server_state = check_memory_server()
        mcp_server = dict(server_state)
        mcp_server["ensure_status"] = ensure_result.get("status", "unknown")
        dependency_state = "ready" if server_state.get("running") and server_state.get("health_ok") else "startup_failed"
        if _should_use_tmux():
            result = provider.invoke_tmux(prompt, project_dir, timeout=timeout)
        else:
            result = provider.invoke(prompt, project_dir, timeout=timeout)
    except Exception as exc:
        result = {"error": str(exc), "fallback": "claude"}

    result = dict(result)
    result["dependency_state"] = dependency_state
    if mcp_server is not None:
        result["mcp_server"] = mcp_server
    return _normalize_provider_error(provider_name, result)


def invoke_codex(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke codex-cli as subprocess. Returns result dict with model/output/exit_code or error/fallback."""
    if not _check_tool_available("codex"):
        return {"error": "codex-cli not found", "fallback": "claude"}
    try:
        cmd = build_non_interactive_command("codex", prompt, project_dir)
        if cmd is None:
            return {"error": "codex-cli contract missing", "fallback": "claude"}
        result = _run_tool(cmd, timeout=timeout)
        return {
            "model": "codex-cli",
            "output": result.stdout,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "codex-cli timeout", "fallback": "claude"}
    except FileNotFoundError:
        return {"error": "codex-cli not found", "fallback": "claude"}
    except Exception as exc:
        return {"error": str(exc), "fallback": "claude"}


def invoke_codex_tmux(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke codex-cli via persistent tmux session. Falls back to subprocess on error."""
    if not _check_tool_available("codex"):
        return {"error": "codex-cli not found", "fallback": "claude"}
    session = ""
    try:
        mgr = _get_tmux_mgr()
        session_name = mgr.make_session_name("codex", unique_id=str(uuid.uuid4())[:8])
        session = mgr.get_or_create_session(session_name)
        result = mgr.send_command_result(session, f"codex exec --json '{prompt}'", timeout=timeout)
        if result.get("completed"):
            return {
                "model": "codex-cli",
                "output": result.get("output", ""),
                "exit_code": int(result.get("exit_code", 0) or 0),
            }
        return {"error": "codex-cli tmux invocation incomplete", "fallback": "claude"}
    except Exception as exc:
        _logger.warning("tmux codex invocation failed, falling back to subprocess: %s", exc)
        return invoke_codex(prompt, project_dir, timeout=timeout)
    finally:
        if session:
            _get_tmux_mgr().kill_session(session)


def invoke_gemini(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke gemini-cli as subprocess. Returns result dict with model/output/exit_code or error/fallback."""
    if not _check_tool_available("gemini"):
        return {"error": "gemini-cli not found", "fallback": "claude"}
    try:
        cmd = build_non_interactive_command("gemini", prompt, project_dir)
        if cmd is None:
            return {"error": "gemini-cli contract missing", "fallback": "claude"}
        result = _run_tool(cmd, timeout=timeout)
        return {
            "model": "gemini-cli",
            "output": result.stdout,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "gemini-cli timeout", "fallback": "claude"}
    except FileNotFoundError:
        return {"error": "gemini-cli not found", "fallback": "claude"}
    except Exception as exc:
        return {"error": str(exc), "fallback": "claude"}


def invoke_kimi(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke kimi-cli via the provider registry."""
    return _invoke_provider("kimi", prompt, project_dir, timeout=timeout)


def invoke_gemini_tmux(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke gemini-cli via persistent tmux session. Falls back to subprocess on error."""
    if not _check_tool_available("gemini"):
        return {"error": "gemini-cli not found", "fallback": "claude"}
    session = ""
    try:
        mgr = _get_tmux_mgr()
        session_name = mgr.make_session_name("gemini", unique_id=str(uuid.uuid4())[:8])
        session = mgr.get_or_create_session(session_name)
        result = mgr.send_command_result(session, f"gemini -p '{prompt}'", timeout=timeout)
        if result.get("completed"):
            return {
                "model": "gemini-cli",
                "output": result.get("output", ""),
                "exit_code": int(result.get("exit_code", 0) or 0),
            }
        return {"error": "gemini-cli tmux invocation incomplete", "fallback": "claude"}
    except Exception as exc:
        _logger.warning("tmux gemini invocation failed, falling back to subprocess: %s", exc)
        return invoke_gemini(prompt, project_dir, timeout=timeout)
    finally:
        if session:
            _get_tmux_mgr().kill_session(session)


def dispatch_to_model(agent_name: str, user_prompt: str, project_dir: str) -> dict[str, Any]:
    """Dispatch a task to the preferred model for this agent.

    Returns result dict. If preferred model unavailable, returns fallback dict.
    """
    import sys as _sys

    _hooks_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks",
    )
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)
    try:
        from _agent_registry import AGENT_REGISTRY, detect_available_models  # pyright: ignore[reportMissingImports]

        agent = AGENT_REGISTRY.get(agent_name)
        if not agent:
            return {"error": f"Unknown agent: {agent_name}", "fallback": "claude"}

        available = detect_available_models()
        preferred = agent.get("preferred_model", "claude")
        packaged = package_prompt(agent_name, user_prompt, project_dir)
        provider_name = _MODEL_PROVIDER_MAP.get(preferred)

        if provider_name is not None and available.get(preferred):
            result = _invoke_provider(provider_name, packaged, project_dir)
            if result.get("fallback_provider") == "claude":
                return _build_claude_fallback(
                    agent_name,
                    dict(agent),
                    base=result,
                    fallback_reason=str(result.get("fallback_reason", "provider_error") or "provider_error"),
                    fallback_trigger_class=str(result.get("fallback_trigger_class", "hard_failure") or "hard_failure"),
                )
            return result
        if preferred in {"claude", "domain-dependent"} or provider_name is None:
            return {
                "fallback": "claude",
                "host_mode": "claude_native",
                "category": agent.get("task_category", "deep"),
                "skills": agent.get("skills", []),
                "model_version": agent.get("model_version", "unknown"),
            }
        # Fallback: use Claude native task() dispatch
        return _build_claude_fallback(
            agent_name,
            dict(agent),
            base={
                "host_mode": "claude_native",
                "category": agent.get("task_category", "deep"),
                "skills": agent.get("skills", []),
                "model_version": agent.get("model_version", "unknown"),
            },
            fallback_reason="provider_cli_missing",
            fallback_trigger_class="hard_failure",
        )
    except Exception as exc:
        return {"error": str(exc), "fallback": "claude"}


def get_core_agent_model(agent_name: str) -> dict[str, Any] | None:
    """Get model preference for a core (non-keyword-matched) agent."""
    import sys as _sys
    _hooks_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks",
    )
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)
    try:
        from _agent_registry import CORE_AGENT_MODELS  # pyright: ignore[reportMissingImports]
        return CORE_AGENT_MODELS.get(agent_name)
    except Exception:
        return None



def execute_agents_sequentially(
    agent_tasks: list[dict[str, Any]],
    project_dir: str,
    timeout_per_agent: int = 120
) -> list[dict[str, Any]]:
    """Execute agents sequentially (one at a time) for CRAZY mode.
    
    Args:
        agent_tasks: List of {agent_name, prompt, order} dicts
        project_dir: Working directory
        timeout_per_agent: Timeout for each agent invocation
        
    Returns:
        List of results in execution order
    """
    # Sort by order if specified
    sorted_tasks = sorted(agent_tasks, key=lambda x: x.get("order", 0))
    
    results: list[dict[str, Any]] = []
    
    for task in sorted_tasks:
        agent_name = task.get("agent_name", "executor")
        prompt = task.get("prompt", "")
        
        print(f"[CRAZY] Launching {agent_name}...")
        
        # Dispatch to the appropriate model
        result = dispatch_to_model(agent_name, prompt, project_dir)
        
        if result.get("fallback") == "claude":
            print(f"[CRAZY] {agent_name} using Claude (native)")
            status = "fallback-claude"
        elif "error" in result:
            print(f"[CRAZY] {agent_name} error: {result['error']}")
            status = "error"
        else:
            print(f"[CRAZY] {agent_name} completed (exit={result.get('exit_code', 'unknown')})")
            status = "completed" if result.get("exit_code") == 0 else "failed"
        
        results.append({
            "agent": agent_name,
            "order": task.get("order", 0),
            "status": status,
            **result
        })
    
    return results


def execute_agents_parallel(
    agent_tasks: list[dict[str, Any]],
    project_dir: str,
    timeout_per_agent: int = 120,
) -> list[dict[str, Any]]:
    indexed_tasks: list[tuple[int, int, dict[str, Any]]] = [
        (idx, int(task.get("order", 0)), task) for idx, task in enumerate(agent_tasks)
    ]
    sorted_tasks = sorted(indexed_tasks, key=lambda x: (x[1], x[0]))
    if not sorted_tasks:
        return []

    max_workers = min(len(sorted_tasks), 5)
    results_by_index: dict[int, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(
                dispatch_to_model,
                str(task_info[2].get("agent_name", "executor")),
                str(task_info[2].get("prompt", "")),
                project_dir,
            ): task_info
            for task_info in sorted_tasks
        }

        for future in as_completed(future_map):
            task_info = future_map[future]
            task = task_info[2]
            order = task_info[1]
            task_index = task_info[0]
            agent_name = str(task.get("agent_name", "executor"))

            try:
                result = future.result(timeout=timeout_per_agent)
            except Exception as exc:
                result = {"error": str(exc), "fallback": "claude"}

            if result.get("fallback") == "claude":
                status = "fallback-claude"
            elif "error" in result:
                status = "error"
            else:
                status = "completed" if result.get("exit_code") == 0 else "failed"

            results_by_index[task_index] = {
                "agent": agent_name,
                "order": order,
                "status": status,
                **result,
            }

    ordered_results = [results_by_index[task_info[0]] for task_info in sorted_tasks]
    return ordered_results


def execute_ccg_mode(
    problem: str,
    project_dir: str,
    context: str | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """CCG mode runs two specialized tracks and returns an execution payload."""
    context_parts: list[str] = []
    if context:
        context_parts.append(context)
    if files:
        context_parts.append(f"Focus files: {', '.join(files[:8])}")
    full_context = "\n\n".join(context_parts) if context_parts else ""

    worker_tasks = [
        {
            "agent_name": "backend-engineer",
            "prompt": (
                f"Backend implementation strategy for: {problem}\n\n"
                f"Focus: APIs, data flow, failure handling, performance.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 1,
        },
        {
            "agent_name": "frontend-designer",
            "prompt": (
                f"Frontend/UI strategy for: {problem}\n\n"
                f"Focus: UX, accessibility, responsive behavior, component structure.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 2,
        },
    ]

    results = execute_agents_parallel(worker_tasks, project_dir)

    result_blocks: list[str] = []
    for result in results:
        result_blocks.append(
            f"**{result.get('agent', 'unknown')} [{result.get('status', 'unknown')}]:**\n"
            f"{result.get('output', result.get('error', 'No output'))}"
        )

    synthesis_prompt = (
        "Synthesize results from two specialized CCG tracks:\n\n"
        + "\n\n".join(result_blocks)
        + "\n\nProvide a unified action plan merging backend and frontend perspectives."
    )

    model_mix = {
        "gpt": [result.get("agent") for result in results if result.get("model") == "codex-cli"],
        "gemini": [result.get("agent") for result in results if result.get("model") == "gemini-cli"],
        "claude": [result.get("agent") for result in results if result.get("fallback") == "claude"],
    }

    return {
        "status": "ok",
        "phases": [
            {"phase": 1, "agent": "claude-orchestrator", "status": "completed"},
            *[
                {
                    "phase": idx,
                    "agent": result.get("agent"),
                    "status": result.get("status", "unknown"),
                    "model": result.get("model", result.get("fallback", "unknown")),
                    "output": result.get("output", ""),
                }
                for idx, result in enumerate(results, start=2)
            ],
            {"phase": len(results) + 2, "agent": "claude-synthesis", "prompt": synthesis_prompt},
        ],
        "parallel_execution": True,
        "sequential_execution": False,
        "worker_count": len(results),
        "target_worker_count": 2,
        "model_mix": model_mix,
        "findings": [
            f"Workers launched: {len(results)}/2",
            f"GPT tracks: {len(model_mix['gpt'])}",
            f"Gemini tracks: {len(model_mix['gemini'])}",
            f"Claude tracks: {len(model_mix['claude'])}",
        ],
    }


def execute_crazy_mode(
    problem: str,
    project_dir: str,
    context: str | None = None,
    files: list[str] | None = None
) -> dict[str, Any]:
    print("[CRAZY] Starting parallel agent execution...")
    print(f"[CRAZY] Problem: {problem[:100]}...")
    
    # Build context package
    context_parts = []
    if context:
        context_parts.append(context)
    if files:
        context_parts.append(f"Focus files: {', '.join(files[:8])}")
    full_context = "\n\n".join(context_parts) if context_parts else ""
    
    worker_tasks = [
        {
            "agent_name": "architect-mode",
            "prompt": (
                f"Plan decomposition for: {problem}\n\n"
                f"Focus: scope, sequencing, dependency ordering, risk control.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 1,
        },
        {
            "agent_name": "backend-engineer",
            "prompt": (
                f"Backend implementation strategy for: {problem}\n\n"
                f"Focus: APIs, data flow, failure handling, performance.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 2,
        },
        {
            "agent_name": "frontend-designer",
            "prompt": (
                f"Frontend/UI strategy for: {problem}\n\n"
                f"Focus: UX, accessibility, responsive behavior, component structure.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 3,
        },
        {
            "agent_name": "security-auditor",
            "prompt": (
                f"Security review strategy for: {problem}\n\n"
                f"Focus: auth, secrets, input validation, abuse vectors.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 4,
        },
        {
            "agent_name": "testing-engineer",
            "prompt": (
                f"Verification strategy for: {problem}\n\n"
                f"Focus: unit/integration/e2e coverage and failure reproduction.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 5,
        },
    ]

    results = execute_agents_parallel(worker_tasks, project_dir)

    result_blocks: list[str] = []
    for r in results:
        result_blocks.append(
            f"**{r.get('agent', 'unknown')} [{r.get('status', 'unknown')}]:**\n"
            f"{r.get('output', r.get('error', 'No output'))}"
        )

    synthesis_prompt = (
        "Synthesize results from five specialized tracks:\n\n"
        + "\n\n".join(result_blocks)
        + "\n\nProvide a unified action plan with dependency ordering."
    )

    model_mix = {
        "gpt": [r.get("agent") for r in results if r.get("model") == "codex-cli"],
        "gemini": [r.get("agent") for r in results if r.get("model") == "gemini-cli"],
        "claude": [r.get("agent") for r in results if r.get("fallback") == "claude"],
        "claude_tiers": _collect_claude_tier_mix(results),
    }

    return {
        "status": "ok",
        "phases": [
            {"phase": 1, "agent": "claude-orchestrator", "status": "completed"},
            *[
                {
                    "phase": idx,
                    "agent": r.get("agent"),
                    "status": r.get("status", "unknown"),
                    "model": r.get("model", r.get("fallback", "unknown")),
                    "output": r.get("output", ""),
                }
                for idx, r in enumerate(results, start=2)
            ],
            {"phase": 7, "agent": "claude-synthesis", "prompt": synthesis_prompt},
        ],
        "parallel_execution": True,
        "sequential_execution": False,
        "worker_count": len(results),
        "target_worker_count": 5,
        "model_mix": model_mix,
        "findings": [
            f"Workers launched: {len(results)}/5",
            f"GPT tracks: {len(model_mix['gpt'])}",
            f"Gemini tracks: {len(model_mix['gemini'])}",
            f"Claude tracks: {len(model_mix['claude'])}",
        ],
    }


# =============================================================================
# Round-Robin Credential Distribution (Feature: OMG_ROUND_ROBIN_ENABLED)
# =============================================================================


def _fnv1a_hash(data: str) -> int:
    """FNV-1a 32-bit hash for session-stable key assignment.

    Deterministic: same input always produces the same hash.
    Used to pin a session to a consistent starting key index.
    """
    h = 2166136261
    for c in data.encode():
        h ^= c
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _get_hooks_imports():
    """Lazy-import credential_store and get_feature_flag.

    Returns (credential_store_module, get_feature_flag_func) or (None, None).
    Adds hooks dir to sys.path if needed (same pattern as package_prompt).
    """
    import sys as _sys

    _hooks_dir = os.path.join(_OMG_ROOT, "hooks")
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)
    try:
        from _common import get_feature_flag  # pyright: ignore[reportMissingImports]
        import credential_store  # pyright: ignore[reportMissingImports]

        return credential_store, get_feature_flag
    except ImportError:
        return None, None


def get_active_credential(provider: str, session_id: str | None = None) -> str | None:
    """Get active API key for provider via round-robin.

    Returns key string or None if credential store disabled/unavailable.
    Feature flag: OMG_ROUND_ROBIN_ENABLED

    Args:
        provider: Provider name (e.g., 'anthropic', 'openai')
        session_id: Optional session ID for deterministic key assignment via FNV-1a hash
    """
    cred_mod, get_flag = _get_hooks_imports()
    if cred_mod is None or get_flag is None:
        return None

    if not get_flag("ROUND_ROBIN", default=False):
        return None

    passphrase = os.environ.get("OMG_CREDENTIAL_PASSPHRASE")
    if not passphrase:
        return None

    try:
        store = cred_mod.load_store(passphrase)
    except (ValueError, OSError):
        return None

    providers = store.get("providers", {})
    if provider not in providers:
        return None

    pdata = providers[provider]
    keys = pdata.get("keys", [])
    if not keys:
        return None

    # Pick key index: session-stable via FNV-1a or current active_index
    if session_id:
        idx = _fnv1a_hash(session_id) % len(keys)
    else:
        idx = pdata.get("active_index", 0)
        if idx < 0 or idx >= len(keys):
            idx = 0

    # Track usage on selected key
    keys[idx]["usage_count"] = keys[idx].get("usage_count", 0) + 1
    keys[idx]["last_used"] = datetime.now(timezone.utc).isoformat()

    # Advance active_index for next non-session call (round-robin)
    if not session_id:
        pdata["active_index"] = (idx + 1) % len(keys)

    # Persist updated stats (best-effort)
    try:
        cred_mod.save_store(store, passphrase)
    except (ValueError, OSError):
        pass

    return keys[idx].get("key")


def on_rate_limit(provider: str, session_id: str | None = None) -> str | None:
    """Advance to next credential for provider on 429. Returns new active key.

    Called when a rate limit (HTTP 429) is encountered. Advances to the next
    available key in the rotation and returns it.

    Args:
        provider: Provider name (e.g., 'anthropic', 'openai')
        session_id: Optional session ID (currently unused, reserved for future)
    """
    cred_mod, get_flag = _get_hooks_imports()
    if cred_mod is None or get_flag is None:
        return None

    if not get_flag("ROUND_ROBIN", default=False):
        return None

    passphrase = os.environ.get("OMG_CREDENTIAL_PASSPHRASE")
    if not passphrase:
        return None

    try:
        store = cred_mod.load_store(passphrase)
    except (ValueError, OSError):
        return None

    providers = store.get("providers", {})
    if provider not in providers:
        return None

    pdata = providers[provider]
    keys = pdata.get("keys", [])
    if not keys:
        return None

    current_idx = pdata.get("active_index", 0)
    if current_idx < 0 or current_idx >= len(keys):
        current_idx = 0

    # Advance to next key
    new_idx = (current_idx + 1) % len(keys)
    pdata["active_index"] = new_idx

    # Persist (best-effort)
    try:
        cred_mod.save_store(store, passphrase)
    except (ValueError, OSError):
        pass

    return keys[new_idx].get("key")


# =============================================================================
# Role-Based Routing (Feature: OMG_ROLE_ROUTING_ENABLED)
# =============================================================================


def get_role_from_env() -> str | None:
    """Read the active role from OMG_ACTIVE_ROLE environment variable.

    Returns:
        Role name string (e.g., 'smol', 'slow') or None if not set.
    """
    val = os.environ.get("OMG_ACTIVE_ROLE", "").strip().lower()
    return val if val else None


def route_with_role(task_text: str, role: str | None = None) -> dict[str, Any]:
    """Select model based on role + task classification.

    Resolution order for role:
      1. Explicit `role` parameter
      2. OMG_ACTIVE_ROLE env var (via get_role_from_env())
      3. CLI args (--smol, --slow, --plan, --commit) via parse_role_args()
      4. None → fall back to existing routing

    Feature flag: OMG_ROLE_ROUTING_ENABLED (default: False)
    When disabled, returns a baseline dict from existing _infer_target().

    Args:
        task_text: Description of the task to route.
        role: Optional explicit role name override.

    Returns:
        Dict with keys: model, provider, role, reason
    """
    import sys as _sys

    # Baseline: always compute the existing routing target
    existing_target = _infer_target(task_text)
    baseline = {
        "model": None,
        "provider": existing_target,
        "role": None,
        "reason": f"intent-based routing to {existing_target}",
        "host_parity_target": existing_target,
        "host_parity": get_provider_host_parity(existing_target),
    }

    # Check feature flag via lazy import
    _hooks_dir = os.path.join(_OMG_ROOT, "hooks")
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)
    try:
        from _common import get_feature_flag  # pyright: ignore[reportMissingImports]
    except ImportError:
        # If _common unavailable, check env var directly
        env_val = os.environ.get("OMG_ROLE_ROUTING_ENABLED", "").lower()
        if env_val not in ("1", "true", "yes"):
            return baseline
        get_feature_flag = None  # type: ignore[assignment]

    if get_feature_flag is not None and not get_feature_flag("ROLE_ROUTING", default=False):
        return baseline

    # Resolve role: explicit param → env var → CLI args
    resolved_role = role
    if resolved_role is None:
        resolved_role = get_role_from_env()
    if resolved_role is None:
        # Lazy import parse_role_args from agents.model_roles
        _agents_dir = os.path.join(_OMG_ROOT, "agents")
        if _agents_dir not in _sys.path:
            _sys.path.insert(0, _agents_dir)
        try:
            from model_roles import parse_role_args  # pyright: ignore[reportMissingImports]
            resolved_role = parse_role_args(_sys.argv[1:])
        except ImportError:
            pass

    # No role resolved → return baseline
    if resolved_role is None:
        return baseline

    # Get role config via lazy import
    _agents_dir = os.path.join(_OMG_ROOT, "agents")
    if _agents_dir not in _sys.path:
        _sys.path.insert(0, _agents_dir)
    try:
        from model_roles import get_role  # pyright: ignore[reportMissingImports]
        role_config = get_role(resolved_role)
    except ImportError:
        return baseline

    if not role_config:
        return baseline

    return {
        "model": role_config.get("model"),
        "provider": role_config.get("model", existing_target),
        "role": resolved_role,
        "reason": f"role-based routing: {resolved_role} → {role_config.get('model', 'unknown')}",
        "host_parity_target": existing_target,
        "host_parity": get_provider_host_parity(existing_target),
    }
