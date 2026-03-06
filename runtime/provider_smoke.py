"""Live smoke helpers for external CLI-backed providers."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any

from runtime.cli_provider import get_provider
from runtime.mcp_lifecycle import check_memory_server, ensure_memory_server
from runtime.team_router import (
    _invoke_provider,
    _normalize_provider_error,
    get_host_execution_profile,
)


_RUNTIME_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _RUNTIME_DIR.parent
_SUPPORTED_PROVIDERS = ("codex", "gemini", "kimi")


def _resolve_host_mode(provider_name: str, host_mode: str) -> str:
    if host_mode == "native":
        return f"{provider_name}_native"
    return host_mode


def get_host_runtime_paths(host_mode: str, project_dir: str) -> dict[str, str]:
    """Return OMG runtime/bootstrap paths relevant for a host mode."""
    profile = get_host_execution_profile(host_mode)
    if profile is None:
        raise ValueError(f"unknown host mode: {host_mode}")

    provider_name = str(profile.get("provider", ""))
    host_config = ""
    if provider_name == "claude":
        host_config = str(Path.home() / ".claude" / "settings.json")
    else:
        provider = get_provider(provider_name)
        if provider is not None:
            host_config = provider.get_config_path()

    return {
        "host_mode": host_mode,
        "host_config": host_config,
        "project_mcp": str(Path(project_dir) / ".mcp.json"),
        "bootstrap_root": str(Path(project_dir) / ".omg"),
        "omg_entrypoint": str(_ROOT_DIR / "scripts" / "omg.py"),
    }


def _build_bootstrap_state(runtime_paths: dict[str, str]) -> dict[str, bool]:
    host_config = runtime_paths.get("host_config", "").strip()
    project_mcp = runtime_paths.get("project_mcp", "").strip()
    return {
        "host_config_exists": bool(host_config and Path(host_config).exists()),
        "project_mcp_exists": bool(project_mcp and Path(project_mcp).exists()),
    }


def _prepare_runtime_dependencies(profile: dict[str, Any], runtime_paths: dict[str, str]) -> tuple[str, dict[str, Any], dict[str, bool]]:
    bootstrap_state = _build_bootstrap_state(runtime_paths)
    mcp_required = bool(profile.get("mcp_supported"))
    server_state = check_memory_server()
    if not mcp_required:
        server_state = dict(server_state)
        server_state["required"] = False
        return "not_required", server_state, bootstrap_state

    ensure_result = ensure_memory_server()
    server_state = check_memory_server()
    server_state = dict(server_state)
    server_state["required"] = True
    server_state["ensure_status"] = ensure_result.get("status", "unknown")
    if ensure_result.get("message"):
        server_state["ensure_message"] = ensure_result.get("message")
    dependency_state = "ready" if server_state.get("running") and server_state.get("health_ok") else "startup_failed"
    return dependency_state, server_state, bootstrap_state


def _classify_blocking_state(smoke_status: str, dependency_state: str) -> tuple[str, bool, str]:
    if smoke_status == "success":
        return "ready", True, "none"
    if smoke_status == "mcp_unreachable" and dependency_state != "ready":
        return "mcp_dependency_unavailable", True, "start_omg_memory_server"
    if smoke_status == "service_disabled":
        return "service_disabled", False, "appeal_provider_account"
    if smoke_status == "missing_env":
        return "environment_missing", True, "set_required_environment"
    if smoke_status == "missing_model":
        return "configuration_missing", True, "configure_default_model"
    if smoke_status == "auth_required":
        return "authentication_required", True, "login_to_provider"
    return "provider_error", True, "inspect_provider_logs"


def run_provider_live_smoke(
    provider_name: str,
    project_dir: str,
    *,
    host_mode: str = "claude_dispatch",
    prompt: str = "Reply with OK.",
    timeout: int = 45,
) -> dict[str, Any]:
    """Run a live smoke invocation for a provider in a specific OMG host mode."""
    if provider_name not in _SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider_name}")

    resolved_host_mode = _resolve_host_mode(provider_name, host_mode)
    profile = get_host_execution_profile(resolved_host_mode)
    if profile is None:
        raise ValueError(f"unknown host mode: {resolved_host_mode}")

    provider = get_provider(provider_name)
    binary_path = shutil.which(provider_name)
    binary_available = bool(binary_path) if provider is None else provider.detect()
    runtime_paths = get_host_runtime_paths(resolved_host_mode, project_dir)
    dependency_state, mcp_server, bootstrap_state = _prepare_runtime_dependencies(profile, runtime_paths)

    if provider is None:
        normalized = {
            "provider": provider_name,
            "host_mode": resolved_host_mode,
            "fallback": "claude",
            "error": "provider not registered",
            "error_code": "provider_missing",
        }
    elif resolved_host_mode == "claude_dispatch":
        normalized = _invoke_provider(provider_name, prompt, project_dir, timeout=timeout)
    else:
        normalized = _normalize_provider_error(
            provider_name,
            provider.invoke(prompt, project_dir, timeout=timeout),
        )
        normalized["host_mode"] = resolved_host_mode

    smoke_status = str(normalized.get("error_code", "success"))
    blocking_class, retryable, recovery_action = _classify_blocking_state(smoke_status, dependency_state)
    environment: dict[str, Any] = {
        "binary_path": binary_path or "",
        "gemini_api_key_present": bool(os.environ.get("GEMINI_API_KEY")) if provider_name == "gemini" else None,
    }

    return {
        "schema": "ProviderSmokeResult",
        "status": "ok",
        "provider": provider_name,
        "host_mode": resolved_host_mode,
        "policy_mode": profile["policy_mode"],
        "native_omg_supported": bool(profile["native_omg_supported"]),
        "claude_call_supported": bool(profile["claude_call_supported"]),
        "binary_available": binary_available,
        "smoke_status": smoke_status,
        "dependency_state": dependency_state,
        "blocking_class": blocking_class,
        "retryable": retryable,
        "recovery_action": recovery_action,
        "warning_codes": list(normalized.get("warning_codes", [])),
        "warning_messages": list(normalized.get("warning_messages", [])),
        "additional_recovery_actions": list(normalized.get("additional_recovery_actions", [])),
        "mcp_server": mcp_server,
        "bootstrap_state": bootstrap_state,
        "runtime_paths": runtime_paths,
        "environment": environment,
        "result": normalized,
    }


def run_provider_smoke_matrix(
    providers: list[str] | None,
    project_dir: str,
    *,
    host_mode: str = "claude_dispatch",
    prompt: str = "Reply with OK.",
    timeout: int = 45,
) -> dict[str, Any]:
    """Run live smoke for one or more providers and return a stable matrix payload."""
    resolved_providers = providers or list(_SUPPORTED_PROVIDERS)
    results = [
        run_provider_live_smoke(
            provider_name,
            project_dir,
            host_mode=host_mode,
            prompt=prompt,
            timeout=timeout,
        )
        for provider_name in resolved_providers
    ]
    return {
        "schema": "ProviderSmokeMatrix",
        "status": "ok",
        "host_mode": host_mode,
        "count": len(results),
        "results": results,
    }


__all__ = [
    "get_host_runtime_paths",
    "run_provider_live_smoke",
    "run_provider_smoke_matrix",
]
