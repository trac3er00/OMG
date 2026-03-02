"""Internal team router for OAL standalone operation."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import os
import re
import shutil
import subprocess
from typing import Any

# --- Path resolution (never relies on CWD) ---
_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
_OAL_ROOT = os.path.dirname(_ROUTER_DIR)

_logger = logging.getLogger(__name__)

@dataclass
class TeamDispatchRequest:
    target: str  # codex | gemini | ccg | auto
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

    if ccg_kw or (gemini_kw and codex_kw):
        return "ccg"
    if gemini_kw:
        return "gemini"
    if codex_kw:
        return "codex"

    ui_signals = ["ui", "ux", "layout", "css", "visual", "responsive", "frontend"]
    code_signals = ["auth", "security", "backend", "debug", "performance", "algorithm"]
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
    ccg_hit = any(k in p for k in ccg_signals)

    if ccg_hit or (ui_hit and code_hit):
        return "ccg"
    if ui_hit:
        return "gemini"
    if code_hit:
        return "codex"
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
}

_INSTALL_HINTS: dict[str, str] = {
    "codex": "Install Codex CLI: npm install -g @openai/codex",
    "gemini": "Install Gemini CLI: npm install -g @google/gemini-cli",
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
    if target == "ccg":
        providers = ("codex", "gemini")
    elif target in ("codex", "gemini"):
        providers = (target,)
    else:
        providers = tuple()

    health: dict[str, dict[str, Any]] = {}
    for provider in providers:
        available = _check_tool_available(provider)
        auth_ok: bool | None = None
        auth_message = "CLI is not installed"
        if available:
            auth_ok, auth_message = _check_tool_auth(provider)
        live_connection = bool(available and auth_ok is True)
        health[provider] = {
            "available": available,
            "auth_ok": auth_ok,
            "live_connection": live_connection,
            "status_message": auth_message,
            "install_hint": _INSTALL_HINTS.get(provider, ""),
        }
    return health


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
    # Import here to avoid circular imports at module level
    import sys as _sys

    _hooks_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hooks",
    )
    if _hooks_dir not in _sys.path:
        _sys.path.insert(0, _hooks_dir)
    try:
        from _agent_registry import AGENT_REGISTRY  # pyright: ignore[reportMissingImports]

        agent = AGENT_REGISTRY.get(agent_name, {})
        description = agent.get("description", f"{agent_name} specialist")
        agent = AGENT_REGISTRY.get(agent_name, {})
        description = agent.get("description", f"{agent_name} specialist")
        model_version = agent.get("model_version", "not specified")
        return (
            f"You are a {description}\n\n"
            f"Model: {model_version}\n"
            f"Project: {project_dir}\n"
            f"Task: {user_prompt}\n\n"
            f"Constraints: Follow existing patterns. No hardcoded secrets. Verify changes."
        )
    except Exception:
        return f"Task: {user_prompt}\nProject: {project_dir}"


def invoke_codex(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke codex-cli as subprocess. Returns result dict with model/output/exit_code or error/fallback."""
    if not _check_tool_available("codex"):
        return {"error": "codex-cli not found", "fallback": "claude"}
    try:
        result = _run_tool(
            ["codex", "exec", "--json", prompt],
            timeout=timeout,
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


def invoke_gemini(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke gemini-cli as subprocess. Returns result dict with model/output/exit_code or error/fallback."""
    if not _check_tool_available("gemini"):
        return {"error": "gemini-cli not found", "fallback": "claude"}
    try:
        result = _run_tool(
            ["gemini", "-p", prompt],
            timeout=timeout,
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

        if preferred == "codex-cli" and available.get("codex-cli"):
            return invoke_codex(packaged, project_dir)
        if preferred == "gemini-cli" and available.get("gemini-cli"):
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
    sorted_tasks = sorted(agent_tasks, key=lambda x: x.get("order", 0))
    if not sorted_tasks:
        return []

    max_workers = min(len(sorted_tasks), 5)
    results_by_order: dict[int, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(
                dispatch_to_model,
                str(task.get("agent_name", "executor")),
                str(task.get("prompt", "")),
                project_dir,
            ): task
            for task in sorted_tasks
        }

        for future in as_completed(future_map):
            task = future_map[future]
            order = int(task.get("order", 0))
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

            results_by_order[order] = {
                "agent": agent_name,
                "order": order,
                "status": status,
                **result,
            }

    ordered_results = [results_by_order[int(task.get("order", 0))] for task in sorted_tasks]
    return ordered_results


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
