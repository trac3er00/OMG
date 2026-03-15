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
    return _selector_collect_cli_health(
        target,
        check_tool_available=_check_tool_available,
        check_tool_auth=_check_tool_auth,
        install_hints=_INSTALL_HINTS,
    )


def dispatch_team(req: TeamDispatchRequest) -> TeamDispatchResult:
    target = req.target.lower().strip()
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
    equalizer_decision = select_provider(
        task_text=req.problem,
        project_dir=_OMG_ROOT,
        context_packet={"summary": req.context},
    )
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
    return execute_workers(
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
    """CCG (Claude-Codex-Gemini) execution mode — 2-track parallel analysis.

    Track 1: backend-engineer (Codex path) — backend/code analysis
    Track 2: frontend-designer (Gemini path) — UI/UX analysis
    Then synthesises both tracks into unified output.
    """
    print("[CCG] Starting 2-track parallel agent execution...")
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
            target_worker_count=2,
            run_id=run_id,
            clarification_status=clarification_status,
            problem=problem,
            project_dir=project_dir,
        )

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
    for r in results:
        result_blocks.append(
            f"**{r.get('agent', 'unknown')} [{r.get('status', 'unknown')}]:**\n"
            f"{r.get('output', r.get('error', 'No output'))}"
        )

    synthesis_prompt = (
        "Synthesize results from two specialized CCG tracks:\n\n"
        + "\n\n".join(result_blocks)
        + "\n\nProvide a unified action plan merging backend and frontend perspectives."
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
            f"Council status: {council_status}",
        ],
        "council_verdicts": council_verdicts,
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
