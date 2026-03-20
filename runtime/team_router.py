"""Internal team router for OMG standalone operation."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from typing import cast

# --- Path resolution (never relies on CWD) ---
_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
_OMG_ROOT = os.path.dirname(_ROUTER_DIR)

_logger = logging.getLogger(__name__)
_ROUTING_MODE_DEFAULT = "normal"
_ROUTING_MODE_CLARIFICATION = "planning_read_only"
_TEAM_STAGED_FLOW = ["team-plan", "team-exec", "team-verify", "team-fix"]
_TEAM_COMMAND_ALIASES = {
    "canonical": "/OMG:team",
    "compatibility": ["/OMG:teams"],
}

# --- Dispatch Strategy Constants (NF7e) ---
DISPATCH_AGENT = "agent-tool"      # Native Claude Code Agent tool
DISPATCH_TMUX = "tmux-session"     # Tmux parallel sessions
DISPATCH_THREAD = "thread-pool"    # ThreadPoolExecutor fallback

# Import providers to trigger auto-registration in provider registry
try:
    import runtime.providers.codex_provider  # noqa: F401  # pyright: ignore[reportUnusedImport]
    import runtime.providers.gemini_provider  # noqa: F401  # pyright: ignore[reportUnusedImport]
    import runtime.providers.kimi_provider  # noqa: F401  # pyright: ignore[reportUnusedImport]
except ImportError:
    pass

from runtime.runtime_profile import resolve_parallel_workers
from runtime.runtime_contracts import write_run_state
from runtime.release_run_coordinator import resolve_current_run_id as resolve_coordinator_run_id, build_release_env_prefix
from runtime.exec_kernel import get_exec_kernel
from runtime.context_engine import ContextEngine
from runtime.context_engine import _extract_clarification
from runtime.context_engine import render_profile_digest_text
from runtime.defense_state import DefenseState
from runtime.equalizer import select_provider
from runtime.router_executor import WorkerTask, execute_workers
from runtime.router_critics import run_critics
from runtime.router_selector import collect_cli_health as _selector_collect_cli_health
from runtime.router_selector import infer_target as _selector_infer_target
from runtime.router_selector import select_target
from runtime.session_health import compute_session_health

@dataclass
class TeamDispatchRequest:
    target: str  # codex | gemini | ccg | auto
    problem: str
    context: str = ""
    context_packet: dict[str, Any] | None = None
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
    return _selector_infer_target(problem)


def _check_tool_available(tool_name: str) -> bool:
    """Return True if *tool_name* is on PATH, else log a warning."""
    if shutil.which(tool_name) is not None:
        return True
    _logger.warning("Tool %r not found on PATH — skipping %s dispatch", tool_name, tool_name)
    return False


def _run_tool(
    cmd: list[str],
    *,
    timeout: int = 30,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external tool with a mandatory timeout.

    Every subprocess call in the team router MUST go through this helper
    to guarantee the ``timeout`` parameter is always set.
    """
    proc_env = os.environ.copy()
    if env:
        proc_env.update({key: str(value) for key, value in env.items()})
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        cwd=cwd,
        env=proc_env,
    )


_TOOL_MAP: dict[str, str] = {
    "codex": "codex",
    "gemini": "gemini",
}

_INSTALL_HINTS: dict[str, str] = {
    "codex": "Install Codex CLI: npm install -g @openai/codex",
    "gemini": "Install Gemini CLI: npm install -g @google/gemini-cli",
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


def _is_tmux_available() -> bool:
    """Return True when tmux binary is available on PATH.

    Unlike _should_use_tmux(), this does not check thread context.
    Use this for deciding whether to attempt tmux-based parallel dispatch.
    """
    try:
        return _get_tmux_mgr().is_tmux_available()
    except Exception:
        return False


def detect_dispatch_strategy() -> str:
    """Detect the best available dispatch strategy for parallel execution.

    Priority order (NF7e hybrid dispatch):
    1. agent-tool: Native Claude Code Agent tool (when running inside Claude Code)
    2. tmux-session: Tmux parallel sessions (when tmux is available)
    3. thread-pool: ThreadPoolExecutor fallback (always available)

    Returns:
        One of DISPATCH_AGENT, DISPATCH_TMUX, or DISPATCH_THREAD.
    """
    # Check for Claude Code environment
    if os.environ.get("CLAUDE_CODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return DISPATCH_AGENT

    # Check for tmux availability
    if _is_tmux_available():
        return DISPATCH_TMUX

    # Fallback to thread pool
    return DISPATCH_THREAD


def dispatch_strategy_report(strategy: str) -> dict[str, Any]:
    """Return metadata about a dispatch strategy's capabilities.

    Args:
        strategy: One of DISPATCH_AGENT, DISPATCH_TMUX, or DISPATCH_THREAD.

    Returns:
        Dict with strategy name, parallel capability, shared_context flag,
        and list of supported providers.
    """
    if strategy == DISPATCH_AGENT:
        return {
            "strategy": "agent-tool",
            "parallel": True,
            "shared_context": True,
            "providers": ["claude"],
        }
    if strategy == DISPATCH_TMUX:
        return {
            "strategy": "tmux-session",
            "parallel": True,
            "shared_context": False,
            "providers": ["codex", "gemini", "kimi", "claude"],
        }
    # DISPATCH_THREAD or unknown
    return {
        "strategy": "thread-pool",
        "parallel": True,
        "shared_context": False,
        "providers": ["codex", "gemini", "kimi"],
    }


def _auth_status_command(tool_name: str) -> list[str] | None:
    if tool_name == "codex":
        return ["codex", "auth", "status"]
    if tool_name == "gemini":
        return ["gemini", "auth", "status"]
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


def _collect_cli_health(target: str) -> dict[str, dict[str, Any]]:
    if os.environ.get("OMG_TEST_FAKE_PROVIDER_HEALTH", "").strip() == "1":
        if target == "ccg":
            providers = ("codex", "gemini")
        elif target in ("codex", "gemini"):
            providers = (target,)
        else:
            providers = tuple()
        return {
            provider: {
                "available": True,
                "auth_ok": True,
                "live_connection": True,
                "status_message": "test-health-override",
                "install_hint": _INSTALL_HINTS.get(provider, ""),
            }
            for provider in providers
        }

    return _selector_collect_cli_health(
        target,
        check_tool_available=_check_tool_available,
        check_tool_auth=_check_tool_auth,
        install_hints=_INSTALL_HINTS,
    )


def dispatch_team(req: TeamDispatchRequest) -> TeamDispatchResult:
    target = req.target.lower().strip()
    selected: dict[str, str] | None = None
    if target == "auto":
        selected = select_target(req.problem, req.context)
        target = selected["target"]

    clarification_status = _extract_clarification_status(req.context_packet)
    clarification_required = bool(clarification_status.get("requires_clarification") is True)

    findings = [f"Target router selected: {target}", f"Problem: {req.problem}"]
    if req.files:
        findings.append(f"Focus files: {', '.join(req.files[:8])}")
    if req.expected_outcome:
        findings.append(f"Expected: {req.expected_outcome}")

    cli_health = _collect_cli_health(target)
    if selected is not None:
        equalizer_decision = select_provider(
            task_text=req.problem,
            project_dir=_OMG_ROOT,
            context_packet={"summary": req.context},
        )
    else:
        equalizer_decision = {
            "provider": target,
            "reason": "explicit target requested",
        }
    findings.append(
        "Equalizer preferred provider: "
        f"{equalizer_decision['provider']} ({equalizer_decision['reason']})"
    )
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
    else:
        actions.extend(
            [
                "Run parallel backend and frontend review tracks",
                "Synthesize cross-cutting findings",
                "Return merged action plan with dependency order",
            ]
        )

    # --- Native question: block the turn when clarification is required ---
    if clarification_required:
        prompt = str(clarification_status.get("clarification_prompt", "")).strip()
        if prompt:
            findings.append(f"Clarification required: {prompt}")
        else:
            findings.append("Clarification required before dispatch")
        return TeamDispatchResult(
            status="clarification_required",
            findings=findings,
            actions=["Resolve the clarification question before dispatch"],
            evidence={
                "target": target,
                "staged_flow": list(_TEAM_STAGED_FLOW),
                "command_aliases": dict(_TEAM_COMMAND_ALIASES),
                "clarification_status": clarification_status,
                "routing_mode": _ROUTING_MODE_CLARIFICATION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    evidence = {
        "target": target,
        "staged_flow": list(_TEAM_STAGED_FLOW),
        "command_aliases": dict(_TEAM_COMMAND_ALIASES),
        "equalizer": equalizer_decision,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context_length": len(req.context or ""),
        "file_count": len(req.files or []),
        "routing_mode": _ROUTING_MODE_DEFAULT,
        "clarification_status": clarification_status,
        "cli_health": cli_health,
        "live_connection": all(h.get("live_connection") for h in cli_health.values()) if cli_health else True,
        "exec_kernel": {
            "enabled": get_exec_kernel(_OMG_ROOT).enabled,
            "run_id": resolve_coordinator_run_id(project_dir=_OMG_ROOT),
        },
    }

    return TeamDispatchResult(status="ok", findings=findings, actions=actions, evidence=evidence)


def package_prompt(agent_name: str, user_prompt: str, project_dir: str) -> str:
    """Build structured prompt for external CLI dispatch with rich context.
    
    Enriches prompt with:
    - Agent description from registry
    - Working memory excerpt (if .omg/state/working-memory.md exists)
    - Profile context (if .omg/state/profile.yaml exists)
    - Recent failure history (if .omg/state/ledger/ exists)
    
    Total prompt capped at 4000 chars (default), configurable via OMG_PROMPT_MAX_CHARS.
    """
    import sys as _sys

    _hooks_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks",
    )
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)

    max_chars = int(os.environ.get("OMG_PROMPT_MAX_CHARS", "4000"))
    sections = []

    try:
        from _agent_registry import AGENT_REGISTRY  # pyright: ignore[reportMissingImports]

        agent = AGENT_REGISTRY.get(agent_name, {})
        description = agent.get("description", f"{agent_name} specialist")
        model_version = agent.get("model_version", "not specified")

        sections.append(f"You are a {description}")
        sections.append(f"Model: {model_version}")

    except Exception:
        sections.append(f"Agent: {agent_name}")

    sections.append(f"Project: {project_dir}")

    working_memory_excerpt = _read_working_memory(project_dir)
    if working_memory_excerpt:
        sections.append(f"Working Memory:\n{working_memory_excerpt}")

    profile_context = _read_profile_context(project_dir)
    if profile_context:
        sections.append(f"Profile:\n{profile_context}")

    failure_history = _read_failure_history(project_dir)
    if failure_history:
        sections.append(f"Recent Failures:\n{failure_history}")

    sections.append(f"Task: {user_prompt}")

    sections.append("Constraints: Follow existing patterns. No hardcoded secrets. Verify changes.")

    result = "\n\n".join(sections)

    if len(result) > max_chars:
        result = result[:max_chars].rstrip()

    return result


def _read_working_memory(project_dir: str) -> str:
    """Read working memory excerpt from .omg/state/working-memory.md."""
    working_memory_path = os.path.join(project_dir, ".omg", "state", "working-memory.md")
    if not os.path.exists(working_memory_path):
        return ""

    try:
        with open(working_memory_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 500:
            content = content[:500] + "..."
        return content
    except (OSError, UnicodeDecodeError):
        return ""


def _read_profile_context(project_dir: str) -> str:
    profile_path = os.path.join(project_dir, ".omg", "state", "profile.yaml")
    if not os.path.exists(profile_path):
        return ""

    try:
        return render_profile_digest_text(project_dir, max_chars=300)
    except (OSError, UnicodeDecodeError):
        return ""
    except Exception:
        return ""


def _read_failure_history(project_dir: str) -> str:
    """Read recent failures from .omg/state/ledger/."""
    ledger_dir = os.path.join(project_dir, ".omg", "state", "ledger")
    if not os.path.exists(ledger_dir):
        return ""

    try:
        failure_files = sorted(glob.glob(os.path.join(ledger_dir, "failure-*.jsonl")))
        if not failure_files:
            return ""

        failures = []
        for file_path in failure_files[-5:]:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            error_msg = entry.get("error", "Unknown error")
                            failures.append(f"- {error_msg}")
                            if len(failures) >= 5:
                                break
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue

        if failures:
            return "\n".join(failures[:5])
        return ""
    except Exception:
        return ""


def invoke_codex(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke codex-cli as subprocess. Returns result dict with model/output/exit_code or error/fallback."""
    if not _check_tool_available("codex"):
        return {"error": "codex-cli not found", "fallback": "claude"}
    try:
        result = _run_tool(
            ["codex", "exec", "--json", prompt],
            timeout=timeout,
            cwd=project_dir,
            env={"CLAUDE_PROJECT_DIR": project_dir},
        )
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


_TMUX_EXIT_MARKER = "__OMG_TMUX_EXIT_CODE__"
_TMUX_EXIT_CODE_RE = re.compile(r"(?:\r?\n)?__OMG_TMUX_EXIT_CODE__:(\d+)\s*$")


def _parse_tmux_command_result(output: str) -> tuple[str, int]:
    """Extract exit code marker from tmux output and return cleaned output + exit code."""
    match = _TMUX_EXIT_CODE_RE.search(output)
    if not match:
        raise RuntimeError("tmux output missing exit code marker")
    exit_code = int(match.group(1))
    cleaned = _TMUX_EXIT_CODE_RE.sub("", output).rstrip()
    return cleaned, exit_code


def invoke_codex_tmux(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke codex-cli via persistent tmux session. Falls back to subprocess on error."""
    if not _check_tool_available("codex"):
        return {"error": "codex-cli not found", "fallback": "claude"}

    mgr = _get_tmux_mgr()
    session: str | None = None
    try:
        session_name = mgr.make_session_name("codex", unique_id=str(uuid.uuid4())[:8])
        session = mgr.get_or_create_session(session_name, cwd=project_dir)
        quoted_prompt = shlex.quote(prompt)
        cmd = (
            f"{build_release_env_prefix(project_dir)}"
            f"codex exec --json {quoted_prompt}; "
            f"printf '\\n{_TMUX_EXIT_MARKER}:%s\\n' \"$?\""
        )
        raw_output = mgr.send_command(session, cmd, timeout=timeout)
        output, exit_code = _parse_tmux_command_result(raw_output)
        return {"model": "codex-cli", "output": output, "exit_code": exit_code}
    except Exception as exc:
        _logger.warning("tmux codex invocation failed, falling back to subprocess: %s", exc)
        return invoke_codex(prompt, project_dir, timeout=timeout)
    finally:
        if session:
            mgr.kill_session(session)


def invoke_gemini(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke gemini-cli as subprocess. Returns result dict with model/output/exit_code or error/fallback."""
    if not _check_tool_available("gemini"):
        return {"error": "gemini-cli not found", "fallback": "claude"}
    try:
        result = _run_tool(
            ["gemini", "-p", prompt],
            timeout=timeout,
            cwd=project_dir,
            env={"CLAUDE_PROJECT_DIR": project_dir},
        )
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


def invoke_gemini_tmux(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke gemini-cli via persistent tmux session. Falls back to subprocess on error."""
    if not _check_tool_available("gemini"):
        return {"error": "gemini-cli not found", "fallback": "claude"}

    mgr = _get_tmux_mgr()
    session: str | None = None
    try:
        session_name = mgr.make_session_name("gemini", unique_id=str(uuid.uuid4())[:8])
        session = mgr.get_or_create_session(session_name, cwd=project_dir)
        quoted_prompt = shlex.quote(prompt)
        cmd = (
            f"{build_release_env_prefix(project_dir)}"
            f"gemini -p {quoted_prompt}; "
            f"printf '\\n{_TMUX_EXIT_MARKER}:%s\\n' \"$?\""
        )
        raw_output = mgr.send_command(session, cmd, timeout=timeout)
        output, exit_code = _parse_tmux_command_result(raw_output)
        return {"model": "gemini-cli", "output": output, "exit_code": exit_code}
    except Exception as exc:
        _logger.warning("tmux gemini invocation failed, falling back to subprocess: %s", exc)
        return invoke_gemini(prompt, project_dir, timeout=timeout)
    finally:
        if session:
            mgr.kill_session(session)


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
        import importlib

        agent_registry = importlib.import_module("_agent_registry")
        AGENT_REGISTRY = getattr(agent_registry, "AGENT_REGISTRY", {})
        detect_available_models = getattr(agent_registry, "detect_available_models", lambda: {"claude": True})
        get_provider_with_equalizer = getattr(agent_registry, "get_provider_with_equalizer", None)

        agent_obj = AGENT_REGISTRY.get(agent_name)
        if not isinstance(agent_obj, dict):
            return {"error": f"Unknown agent: {agent_name}", "fallback": "claude"}
        agent = agent_obj

        available = detect_available_models()
        preferred = agent.get("preferred_model", "claude")
        if callable(get_provider_with_equalizer):
            equalizer_info = get_provider_with_equalizer(
                task_text=user_prompt,
                project_dir=project_dir,
                agent_name=agent_name,
            )
            if isinstance(equalizer_info, dict):
                preferred = str(equalizer_info.get("preferred_model", preferred))
        packaged = package_prompt(agent_name, user_prompt, project_dir)

        provider_name_map = {
            "codex-cli": "codex",
            "gemini-cli": "gemini",
            "kimi-cli": "kimi",
        }
        provider_name = provider_name_map.get(preferred)

        if provider_name and available.get(preferred, True):
            from runtime.cli_provider import get_provider

            provider = get_provider(provider_name)
            if provider and provider.detect():
                if _should_use_tmux():
                    return provider.invoke_tmux(packaged, project_dir)
                return provider.invoke(packaged, project_dir)

        if preferred == "codex-cli" and available.get("codex-cli"):
            if _should_use_tmux():
                return invoke_codex_tmux(packaged, project_dir)
            return invoke_codex(packaged, project_dir)
        if preferred == "gemini-cli" and available.get("gemini-cli"):
            if _should_use_tmux():
                return invoke_gemini_tmux(packaged, project_dir)
            return invoke_gemini(packaged, project_dir)
        # Fallback: use Claude native task() dispatch
        return {
            "fallback": "claude",
            "category": agent.get("task_category", "deep"),
            "skills": agent.get("skills", []),
            "model_version": agent.get("model_version", "unknown"),
        }
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



def _get_agent_cli_command(agent_name: str, prompt: str, project_dir: str) -> tuple[str, str]:
    """Determine CLI command and model name for an agent.

    Returns (cli_command, model_name) tuple.
    Falls back to codex if agent's preferred model is unavailable.
    """
    import sys as _sys

    _hooks_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks",
    )
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)

    try:
        import importlib

        agent_registry = importlib.import_module("_agent_registry")
        AGENT_REGISTRY = getattr(agent_registry, "AGENT_REGISTRY", {})
        detect_available_models = getattr(agent_registry, "detect_available_models", lambda: {"claude": True})

        agent_obj = AGENT_REGISTRY.get(agent_name)
        preferred = "codex-cli"
        if isinstance(agent_obj, dict):
            preferred = agent_obj.get("preferred_model", "codex-cli")

        available = detect_available_models()

        quoted_prompt = shlex.quote(prompt)
        env_prefix = build_release_env_prefix(project_dir)

        if preferred == "gemini-cli" and available.get("gemini-cli") and _check_tool_available("gemini"):
            return (f"{env_prefix}gemini -p {quoted_prompt}", "gemini-cli")

        if _check_tool_available("codex"):
            return (f"{env_prefix}codex exec --json {quoted_prompt}", "codex-cli")

        if _check_tool_available("gemini"):
            return (f"{env_prefix}gemini -p {quoted_prompt}", "gemini-cli")

    except Exception:
        pass

    # Fallback to codex command even if detection failed
    quoted_prompt = shlex.quote(prompt)
    return (f"{build_release_env_prefix(project_dir)}codex exec --json {quoted_prompt}", "codex-cli")


def dispatch_parallel_tmux(
    workers: list[dict[str, Any]],
    project_dir: str,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Execute workers in parallel using separate tmux sessions for each.

    Creates a tmux session per worker, sends the CLI command to each,
    polls for completion, and collects results. Falls back to regular
    execution if any session fails.

    Returns results in the same format as execute_agents_parallel().
    """
    mgr = _get_tmux_mgr()
    if not mgr.is_tmux_available():
        raise RuntimeError("tmux not available")

    # Sort workers by order for consistent result ordering
    indexed_workers: list[tuple[int, int, dict[str, Any]]] = [
        (idx, int(w.get("order", 0)), w) for idx, w in enumerate(workers)
    ]
    sorted_workers = sorted(indexed_workers, key=lambda x: (x[1], x[0]))
    if not sorted_workers:
        return []

    # idx -> (session_name, agent_name, model_name, worker)
    sessions: dict[int, tuple[str, str, str, dict[str, Any]]] = {}

    try:
        # Create sessions and send commands
        for idx, order, worker in sorted_workers:
            agent_name = str(worker.get("agent_name", "executor"))
            prompt = str(worker.get("prompt", ""))
            packaged = package_prompt(agent_name, prompt, project_dir)
            session_name = mgr.make_session_name(agent_name, unique_id=str(uuid.uuid4())[:8])
            try:
                session = mgr.get_or_create_session(session_name, cwd=project_dir)
            except RuntimeError as exc:
                _logger.warning("Failed to create tmux session %s: %s", session_name, exc)
                raise

            cli_cmd, model_name = _get_agent_cli_command(agent_name, packaged, project_dir)
            cmd = f"{cli_cmd}; printf '\\n{_TMUX_EXIT_MARKER}:%s\\n' \"$?\""

            # Send command (non-blocking, just sends keys)
            subprocess.run(
                ["tmux", "send-keys", "-t", session, cmd, "Enter"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            sessions[idx] = (session, agent_name, model_name, worker)

        # Poll all sessions for completion
        deadline = time.monotonic() + timeout
        results_by_idx: dict[int, dict[str, Any]] = {}
        pending_indices = set(sessions.keys())

        while pending_indices and time.monotonic() < deadline:
            for idx in list(pending_indices):
                session, agent_name, model_name, worker = sessions[idx]
                try:
                    captured = subprocess.run(
                        ["tmux", "capture-pane", "-t", session, "-p"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=10,
                    )
                    if captured.returncode == 0:
                        pane_output = captured.stdout
                        if _TMUX_EXIT_MARKER in pane_output:
                            # Command completed
                            output, exit_code = _parse_tmux_command_result(pane_output)
                            result: dict[str, Any] = {
                                "model": model_name,
                                "output": output,
                                "exit_code": exit_code,
                            }
                            order = int(worker.get("order", 0))
                            status = "completed" if exit_code == 0 else "failed"
                            results_by_idx[idx] = {
                                "agent": agent_name,
                                "order": order,
                                "status": status,
                                **result,
                            }
                            pending_indices.discard(idx)
                except Exception as exc:
                    _logger.warning("Error polling tmux session %s: %s", session, exc)

            if pending_indices:
                time.sleep(0.5)

        # Handle timeouts
        for idx in pending_indices:
            session, agent_name, model_name, worker = sessions[idx]
            order = int(worker.get("order", 0))
            results_by_idx[idx] = {
                "agent": agent_name,
                "order": order,
                "status": "error",
                "error": "tmux command timeout",
                "fallback": "claude",
            }

        # Return results in original order
        return [results_by_idx[idx] for idx, _, _ in sorted_workers]

    finally:
        # Cleanup all sessions
        for idx, (session, _, _, _) in sessions.items():
            try:
                mgr.kill_session(session)
            except Exception:
                pass


def execute_agents_sequentially(
    agent_tasks: list[dict[str, Any]],
    project_dir: str,
    timeout_per_agent: int = 120
) -> list[dict[str, Any]]:
    return execute_workers(
        cast(list[WorkerTask], agent_tasks),
        False,
        project_dir=project_dir,
        dispatch_fn=dispatch_to_model,
        timeout_per_worker=timeout_per_agent,
        resolve_workers_fn=lambda router_project_dir, requested_workers: resolve_parallel_workers(
            router_project_dir,
            requested_workers=requested_workers,
        ),
        thread_pool_cls=ThreadPoolExecutor,
    )


def execute_agents_parallel(
    agent_tasks: list[dict[str, Any]],
    project_dir: str,
    timeout_per_agent: int = 120,
) -> list[dict[str, Any]]:
    # Detect dispatch strategy (NF7e)
    strategy = detect_dispatch_strategy()

    # Try tmux-based parallel dispatch first (works in main thread)
    if strategy == DISPATCH_TMUX:
        try:
            results = dispatch_parallel_tmux(agent_tasks, project_dir, timeout=timeout_per_agent)
            for r in results:
                r["dispatch_strategy"] = strategy
            return results
        except Exception as exc:
            _logger.debug("tmux parallel dispatch failed, falling back to ThreadPoolExecutor: %s", exc)
            strategy = DISPATCH_THREAD

    # Fallback to existing ThreadPoolExecutor path
    results = execute_workers(
        cast(list[WorkerTask], agent_tasks),
        True,
        project_dir=project_dir,
        dispatch_fn=dispatch_to_model,
        timeout_per_worker=timeout_per_agent,
        resolve_workers_fn=lambda router_project_dir, requested_workers: resolve_parallel_workers(
            router_project_dir,
            requested_workers=requested_workers,
        ),
        thread_pool_cls=ThreadPoolExecutor,
    )
    for r in results:
        r["dispatch_strategy"] = strategy
    return results


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
    
    run_id = resolve_coordinator_run_id(project_dir=project_dir)
    kernel = get_exec_kernel(project_dir)
    if run_id:
        kernel.register_run(run_id, source="team_router.execute_crazy_mode", reason="crazy_mode")
    context_packet = _build_router_context_packet(
        project_dir=project_dir,
        run_id=run_id,
        summary=full_context,
        files=files,
    )
    clarification_status = _extract_clarification_status(context_packet)
    if clarification_status.get("requires_clarification") is True:
        return _build_clarification_blocked_result(
            mode="crazy",
            target_worker_count=5,
            run_id=run_id,
            clarification_status=clarification_status,
            problem=problem,
            project_dir=project_dir,
        )

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

    council_verdicts = run_critics(
        candidate={"output": synthesis_prompt},
        context_packet=context_packet,
        project_dir=project_dir,
    )
    _persist_council_verdicts(project_dir, run_id, council_verdicts)
    _update_post_council_state(project_dir=project_dir, run_id=run_id)
    council_status = _council_status(council_verdicts)

    model_mix = {
        "gpt": [r.get("agent") for r in results if r.get("model") == "codex-cli"],
        "gemini": [r.get("agent") for r in results if r.get("model") == "gemini-cli"],
        "claude": [r.get("agent") for r in results if r.get("fallback") == "claude"],
    }

    return {
        "status": "ok",
        "stages": list(_TEAM_STAGED_FLOW),
        "current_stage": "team-fix",
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
            f"Council status: {council_status}",
        ],
        "council_verdicts": council_verdicts,
        "exec_kernel": {
            "enabled": kernel.enabled,
            "run_id": run_id,
            "attach_log": kernel.attach_log(run_id) if run_id else "",
        },
    }


def execute_ccg_mode(
    problem: str,
    project_dir: str,
    context: str | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """CCG (Claude-Codex-Gemini) execution mode — 3-track parallel analysis.

    Track 1: backend-engineer (Codex path) — backend/code analysis
    Track 2: frontend-designer (Gemini path) — UI/UX analysis
    Track 3: architect (Claude path) — system architecture analysis
    Then synthesises all tracks into unified output.

    Creates and updates coordinator state throughout execution for shared
    memory across model switches (NF5b).
    """
    print("[CCG] Starting 3-track parallel agent execution...")
    print(f"[CCG] Problem: {problem[:100]}...")

    # Build context package
    context_parts: list[str] = []
    if context:
        context_parts.append(context)
    if files:
        context_parts.append(f"Focus files: {', '.join(files[:8])}")
    full_context = "\n\n".join(context_parts) if context_parts else ""

    run_id = resolve_coordinator_run_id(project_dir=project_dir)
    kernel = get_exec_kernel(project_dir)
    if run_id:
        kernel.register_run(run_id, source="team_router.execute_ccg_mode", reason="ccg_mode")
    context_packet = _build_router_context_packet(
        project_dir=project_dir,
        run_id=run_id,
        summary=full_context,
        files=files,
    )
    clarification_status = _extract_clarification_status(context_packet)
    if clarification_status.get("requires_clarification") is True:
        return _build_clarification_blocked_result(
            mode="ccg",
            target_worker_count=3,
            run_id=run_id,
            clarification_status=clarification_status,
            problem=problem,
            project_dir=project_dir,
        )

    # Generate task_id for coordinator state (use run_id or generate new)
    task_id = run_id or str(uuid.uuid4())[:12]

    # Create initial coordinator state (NF5b)
    initial_state: dict[str, Any] = {
        "decisions": [f"Starting CCG mode for: {problem[:100]}"],
        "files_touched": list(files or []),
        "evidence": {},
        "unsolved": [],
        "model_history": ["claude-orchestrator"],
        "problem": problem,
        "mode": "ccg",
    }
    coordinator_state_path = save_coordinator_state(project_dir, task_id, initial_state)

    worker_tasks = [
        {
            "agent_name": "backend-engineer",
            "prompt": (
                f"Backend implementation strategy for: {problem}\n\n"
                f"Focus: APIs, data flow, failure handling, performance, security.\n\n"
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
        {
            "agent_name": "architect",
            "prompt": (
                f"System architecture analysis for: {problem}\n\n"
                f"Focus: dependency graph, integration points, trade-offs, risks, rollback strategy.\n\n"
                f"Context:\n{full_context}"
            ),
            "order": 3,
        },
    ]

    results = execute_agents_parallel(worker_tasks, project_dir)

    # Extract dispatch strategy from results (NF7e)
    dispatch_strategy = results[0].get("dispatch_strategy") if results else detect_dispatch_strategy()

    # Update coordinator state after parallel execution (NF5b)
    track_decisions: list[str] = []
    track_models: list[str] = []
    track_evidence: dict[str, Any] = {}
    track_unsolved: list[str] = []

    for r in results:
        agent = r.get("agent", "unknown")
        status = r.get("status", "unknown")
        model = r.get("model", r.get("fallback", "unknown"))
        track_decisions.append(f"{agent} completed with status={status}")
        track_models.append(model)
        track_evidence[f"track_{agent}"] = {
            "status": status,
            "model": model,
            "exit_code": r.get("exit_code"),
        }
        if status == "failed" or status == "error":
            track_unsolved.append(f"{agent} track failed: {r.get('error', 'unknown error')}")

    update_coordinator_state(project_dir, task_id, {
        "decisions": track_decisions,
        "model_history": track_models,
        "evidence": track_evidence,
        "unsolved": track_unsolved,
    })

    result_blocks: list[str] = []
    for r in results:
        result_blocks.append(
            f"**{r.get('agent', 'unknown')} [{r.get('status', 'unknown')}]:**\n"
            f"{r.get('output', r.get('error', 'No output'))}"
        )

    synthesis_prompt = (
        "Synthesize results from three specialized CCG tracks:\n\n"
        + "\n\n".join(result_blocks)
        + "\n\nProvide a unified action plan merging backend, frontend, and architecture perspectives. "
        + "Resolve any conflicts using the architect track's dependency analysis as tiebreaker."
    )

    council_verdicts = run_critics(
        candidate={"output": synthesis_prompt},
        context_packet=context_packet,
        project_dir=project_dir,
    )
    _persist_council_verdicts(project_dir, run_id, council_verdicts)
    _update_post_council_state(project_dir=project_dir, run_id=run_id)
    council_status = _council_status(council_verdicts)

    # Final coordinator state update with council results
    update_coordinator_state(project_dir, task_id, {
        "decisions": [f"Council verdict: {council_status}"],
        "model_history": ["claude-synthesis"],
        "evidence": {"council_status": council_status},
    })

    model_mix = {
        "gpt": [r.get("agent") for r in results if r.get("model") == "codex-cli"],
        "gemini": [r.get("agent") for r in results if r.get("model") == "gemini-cli"],
        "claude": [r.get("agent") for r in results if r.get("fallback") == "claude" or (r.get("model") or "").startswith("claude")],
    }

    return {
        "status": "ok",
        "stages": list(_TEAM_STAGED_FLOW),
        "current_stage": "team-fix",
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
            {"phase": len(results) + 2, "agent": "claude-synthesis", "prompt": synthesis_prompt},
        ],
        "parallel_execution": True,
        "sequential_execution": False,
        "worker_count": len(results),
        "target_worker_count": 3,
        "model_mix": model_mix,
        "findings": [
            f"Workers launched: {len(results)}/3",
            f"GPT tracks: {len(model_mix['gpt'])}",
            f"Gemini tracks: {len(model_mix['gemini'])}",
            f"Claude tracks: {len(model_mix['claude'])}",
            f"Council status: {council_status}",
        ],
        "council_verdicts": council_verdicts,
        "dispatch_strategy": dispatch_strategy,
        "coordinator_state_path": coordinator_state_path,
        "exec_kernel": {
            "enabled": kernel.enabled,
            "run_id": run_id,
            "attach_log": kernel.attach_log(run_id) if run_id else "",
        },
    }


def _persist_question_state(
    project_dir: str,
    run_id: str,
    question_text: str,
    mode: str,
    problem: str,
) -> None:
    """Write minimal question state to the run-state directory.

    This is NOT a new schema — it is a flat file under .omg/state/ that
    records which question is pending so the session can resume or reject.
    """
    state_dir = Path(project_dir) / ".omg" / "state" / "pending_question"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "question_pending": True,
        "question_text": str(question_text).strip()[:500],
        "mode": mode,
        "problem": str(problem).strip()[:200],
        "run_id": run_id,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    target = state_dir / f"{run_id}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.rename(tmp, target)


def _build_clarification_blocked_result(
    *,
    mode: str,
    target_worker_count: int,
    run_id: str | None,
    clarification_status: dict[str, Any],
    problem: str,
    project_dir: str = "",
) -> dict[str, Any]:
    """Build a blocked result when clarification is required.

    The returned dict signals ``status='clarification_required'`` which
    guarantees the turn ends — no worker dispatch or tool action follows.
    Minimal question state is persisted via the run-state directory so the
    session can resume or reject the question later.
    """
    prompt = str(clarification_status.get("clarification_prompt", "")).strip()
    findings = [
        f"Staged flow halted at team-plan for {mode} routing",
        "Clarification unresolved before worker dispatch",
    ]
    if prompt:
        findings.append(f"Clarification request: {prompt}")

    # Persist minimal run-scoped question state for resume / reject
    if run_id and project_dir:
        _persist_question_state(project_dir, run_id, prompt, mode, problem)

    return {
        "status": "clarification_required",
        "stages": list(_TEAM_STAGED_FLOW),
        "current_stage": "team-plan",
        "parallel_execution": False,
        "sequential_execution": False,
        "worker_count": 0,
        "target_worker_count": target_worker_count,
        "findings": findings,
        "actions": [
            "Clarify intent and acceptance criteria",
            "Confirm required files and expected outcome",
            "Re-run /OMG:team once clarification is resolved",
        ],
        "clarification_status": clarification_status,
        "problem": problem,
        "run_id": run_id,
    }


def _build_router_context_packet(
    *,
    project_dir: str,
    run_id: str | None,
    summary: str,
    files: list[str] | None,
) -> dict[str, object]:
    if run_id:
        packet = ContextEngine(project_dir).build_packet(run_id=run_id, delta_only=True)
        if summary and not str(packet.get("summary", "")).strip():
            packet["summary"] = summary
        if _requires_clarification(packet):
            packet["routing_mode"] = _ROUTING_MODE_CLARIFICATION
        return packet
    return {
        "summary": summary,
        "artifact_pointers": [],
        "clarification_status": {
            "requires_clarification": False,
            "intent_class": "",
            "clarification_prompt": "",
            "confidence": 0.0,
        },
        "routing_mode": _ROUTING_MODE_DEFAULT,
        "files": list(files or []),
    }


def _extract_clarification_status(context_packet: dict[str, Any] | None) -> dict[str, Any]:
    status = _extract_clarification(context_packet)
    return {
        "requires_clarification": bool(status.get("requires_clarification") is True),
        "intent_class": str(status.get("intent_class", "")).strip(),
        "clarification_prompt": str(status.get("clarification_prompt", "")).strip(),
        "confidence": round(float(status.get("confidence", 0.0)), 2),
    }


def _requires_clarification(context_packet: dict[str, object]) -> bool:
    status = _extract_clarification_status(cast(dict[str, Any], context_packet))
    return bool(status.get("requires_clarification") is True)


def _persist_council_verdicts(project_dir: str, run_id: str | None, verdicts: dict[str, dict[str, Any]]) -> None:
    if not run_id:
        return

    payload: dict[str, object] = {
        "status": _council_status(verdicts),
        "verification_status": _council_status(verdicts),
        "verdicts": verdicts,
    }
    write_run_state(project_dir, "council_verdicts", run_id, payload)


def _update_post_council_state(*, project_dir: str, run_id: str | None) -> None:
    DefenseState(project_dir).update()
    compute_session_health(project_dir, run_id=run_id or "default")


def _council_status(verdicts: dict[str, dict[str, Any]]) -> str:
    verdict_tokens = {
        str(item.get("verdict", "")).strip().lower()
        for item in verdicts.values()
        if isinstance(item, dict)
    }
    if "fail" in verdict_tokens:
        return "blocked"
    if "warn" in verdict_tokens:
        return "running"
    if "pass" in verdict_tokens:
        return "ok"
    return "pending"


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
    except (ValueError, OSError, RuntimeError):
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
    except (ValueError, OSError, RuntimeError):
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
    except (ValueError, OSError, RuntimeError):
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
    except (ValueError, OSError, RuntimeError):
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
    }


# =============================================================================
# Coordinator State Management (NF5b: Shared Memory Across Model Switches)
# =============================================================================


def save_coordinator_state(project_dir: str, task_id: str, state: dict[str, Any]) -> str:
    """Save coordinator state to disk.

    Writes state to `.omg/state/coordinator/<task_id>.json`.
    State typically includes: decisions, files_touched, evidence, unsolved, model_history.

    Args:
        project_dir: Project root directory.
        task_id: Unique task identifier (e.g., run_id or UUID).
        state: State dict to persist.

    Returns:
        Absolute path to the saved state file.
    """
    state_dir = Path(project_dir) / ".omg" / "state" / "coordinator"
    state_dir.mkdir(parents=True, exist_ok=True)

    target = state_dir / f"{task_id}.json"
    tmp = target.with_suffix(".tmp")

    # Add metadata
    state_with_meta = dict(state)
    state_with_meta["_saved_at"] = datetime.now(timezone.utc).isoformat()
    state_with_meta["_task_id"] = task_id

    tmp.write_text(json.dumps(state_with_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    os.rename(tmp, target)

    return str(target)


def load_coordinator_state(project_dir: str, task_id: str) -> dict[str, Any] | None:
    """Load coordinator state from disk.

    Reads from `.omg/state/coordinator/<task_id>.json`.

    Args:
        project_dir: Project root directory.
        task_id: Unique task identifier.

    Returns:
        State dict if found and valid, None otherwise.
    """
    state_path = Path(project_dir) / ".omg" / "state" / "coordinator" / f"{task_id}.json"
    if not state_path.exists():
        return None

    try:
        content = state_path.read_text(encoding="utf-8")
        return json.loads(content)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def update_coordinator_state(project_dir: str, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into existing coordinator state.

    Loads current state, merges updates, adds timestamp to update_history,
    and persists the result.

    Args:
        project_dir: Project root directory.
        task_id: Unique task identifier.
        updates: Dict of updates to merge.

    Returns:
        Updated state dict.
    """
    existing = load_coordinator_state(project_dir, task_id)
    if existing is None:
        existing = {}

    # Merge updates into existing state
    merged = dict(existing)
    for key, value in updates.items():
        if key.startswith("_"):
            # Skip internal metadata keys from user updates
            continue
        if key in merged and isinstance(merged[key], list) and isinstance(value, list):
            # Extend lists rather than replace
            merged[key] = merged[key] + value
        elif key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            # Merge dicts recursively (shallow)
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    # Add timestamp to update_history
    update_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "keys_updated": list(updates.keys()),
    }
    if "update_history" not in merged:
        merged["update_history"] = []
    merged["update_history"].append(update_record)

    # Persist
    save_coordinator_state(project_dir, task_id, merged)

    return merged


def build_model_handoff_context(state: dict[str, Any], target_model: str) -> str:
    """Build a context string for model handoff.

    Formats state into a context string suitable for passing to the next model.
    Format varies based on target:
    - codex: terse, technical, bullet points
    - gemini: visual-focused, component-aware

    Args:
        state: Coordinator state dict.
        target_model: Target model name ("codex", "gemini", or other).

    Returns:
        Formatted context string for the target model.
    """
    decisions = state.get("decisions", [])
    files_touched = state.get("files_touched", [])
    evidence = state.get("evidence", {})
    unsolved = state.get("unsolved", [])
    model_history = state.get("model_history", [])

    if target_model == "codex":
        # Terse, technical format for Codex
        lines = ["# Coordinator Handoff (terse)"]

        if decisions:
            lines.append("## Decisions")
            for d in decisions[-5:]:  # Last 5 decisions
                lines.append(f"- {d}")

        if files_touched:
            lines.append("## Files")
            for f in files_touched[-10:]:
                lines.append(f"- {f}")

        if unsolved:
            lines.append("## Unsolved")
            for u in unsolved:
                lines.append(f"- {u}")

        if evidence:
            lines.append("## Evidence Keys")
            lines.append(f"- {', '.join(list(evidence.keys())[:10])}")

        if model_history:
            lines.append("## Prior Models")
            lines.append(f"- {' -> '.join(model_history[-5:])}")

        return "\n".join(lines)

    elif target_model == "gemini":
        # Visual-focused format for Gemini
        lines = ["# Coordinator Handoff (visual context)"]

        if decisions:
            lines.append("")
            lines.append("## Decisions Made")
            for d in decisions[-5:]:
                lines.append(f"  - {d}")

        if files_touched:
            lines.append("")
            lines.append("## Files to Review")
            ui_files = [f for f in files_touched if any(ext in f for ext in [".tsx", ".jsx", ".css", ".html", ".vue", ".svelte"])]
            other_files = [f for f in files_touched if f not in ui_files]
            if ui_files:
                lines.append("### UI Components")
                for f in ui_files[-8:]:
                    lines.append(f"  - {f}")
            if other_files:
                lines.append("### Other Files")
                for f in other_files[-5:]:
                    lines.append(f"  - {f}")

        if unsolved:
            lines.append("")
            lines.append("## Open Questions")
            for u in unsolved:
                lines.append(f"  - {u}")

        if evidence:
            lines.append("")
            lines.append("## Available Evidence")
            for key in list(evidence.keys())[:8]:
                lines.append(f"  - {key}")

        if model_history:
            lines.append("")
            lines.append("## Model Chain")
            lines.append(f"  {' -> '.join(model_history[-5:])} -> gemini")

        return "\n".join(lines)

    else:
        # Default format for other models (e.g., claude)
        lines = ["# Coordinator State Handoff"]

        if decisions:
            lines.append("")
            lines.append("## Decisions")
            for d in decisions:
                lines.append(f"- {d}")

        if files_touched:
            lines.append("")
            lines.append("## Files Touched")
            for f in files_touched:
                lines.append(f"- {f}")

        if unsolved:
            lines.append("")
            lines.append("## Unsolved Items")
            for u in unsolved:
                lines.append(f"- {u}")

        if evidence:
            lines.append("")
            lines.append("## Evidence")
            for key, val in list(evidence.items())[:10]:
                if isinstance(val, str) and len(val) < 100:
                    lines.append(f"- {key}: {val}")
                else:
                    lines.append(f"- {key}: (data)")

        if model_history:
            lines.append("")
            lines.append("## Model History")
            lines.append(f"- {' -> '.join(model_history)}")

        return "\n".join(lines)
