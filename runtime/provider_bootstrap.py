"""Provider status/bootstrap helpers for native-host OMG parity."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.cli_provider import get_provider, list_available_providers
from runtime.mcp_config_writers import (
    write_claude_mcp_config,
    write_codex_mcp_config,
    write_gemini_mcp_config,
    write_kimi_mcp_config,
    write_opencode_mcp_config,
)
from runtime.mcp_lifecycle import check_memory_server, ensure_memory_server, get_server_url
from runtime.provider_smoke import get_host_runtime_paths, run_provider_live_smoke
from runtime.team_router import get_host_execution_profile, get_provider_host_parity
import runtime.providers  # noqa: F401  # Ensure provider registry is populated for CLI entrypoints.


_WRITERS = {
    "codex": write_codex_mcp_config,
    "gemini": write_gemini_mcp_config,
    "opencode": write_opencode_mcp_config,
    "kimi": write_kimi_mcp_config,
}

_PROVIDER_SIDE_ACTIONS = {
    "login_to_provider",
    "appeal_provider_account",
}

_LOCAL_REASON_MAP = {
    "bootstrap_host_config": "host_config_missing",
    "bootstrap_project_mcp": "project_mcp_missing",
    "set_required_environment": "required_environment_missing",
    "configure_default_model": "default_model_missing",
    "remove_incompatible_feature_flags": "provider_config_incompatible",
    "start_omg_memory_server": "mcp_dependency_unavailable",
}

_PROVIDER_REASON_MAP = {
    "login_to_provider": "provider_login_required",
    "appeal_provider_account": "provider_service_disabled",
}


def _resolve_providers(providers: list[str] | None) -> list[str]:
    available = list_available_providers()
    if not providers:
        return available
    resolved = [provider for provider in providers if provider and provider != "all" and provider in available]
    return resolved or available


def _bootstrap_state(runtime_paths: dict[str, str]) -> dict[str, bool]:
    host_config = runtime_paths.get("host_config", "").strip()
    project_mcp = runtime_paths.get("project_mcp", "").strip()
    return {
        "host_config_exists": bool(host_config and Path(host_config).exists()),
        "project_mcp_exists": bool(project_mcp and Path(project_mcp).exists()),
    }


def _manual_steps(
    provider_name: str,
    *,
    detected: bool,
    auth_ok: bool | None,
    bootstrap_state: dict[str, bool],
) -> list[str]:
    steps: list[str] = []
    if not detected:
        steps.append(f"install_{provider_name}_cli")
    if auth_ok is False:
        steps.append("login_to_provider")
    if not bootstrap_state["host_config_exists"]:
        steps.append("bootstrap_host_config")
    if not bootstrap_state["project_mcp_exists"]:
        steps.append("bootstrap_project_mcp")
    return steps


def _classify_step(step: str) -> str:
    if step in _PROVIDER_SIDE_ACTIONS:
        return "provider"
    return "local"


def _split_steps(steps: list[str]) -> tuple[list[str], list[str]]:
    local_steps: list[str] = []
    provider_steps: list[str] = []
    for step in steps:
        if _classify_step(step) == "provider":
            if step not in provider_steps:
                provider_steps.append(step)
        elif step not in local_steps:
            local_steps.append(step)
    return local_steps, provider_steps


def _reason_for_step(step: str) -> str:
    if step.startswith("install_") and step.endswith("_cli"):
        return "provider_cli_missing"
    if step in _LOCAL_REASON_MAP:
        return _LOCAL_REASON_MAP[step]
    if step in _PROVIDER_REASON_MAP:
        return _PROVIDER_REASON_MAP[step]
    return "runtime_action_required"


def _build_readiness_reasons(
    *,
    local_steps: list[str],
    provider_steps: list[str],
) -> tuple[list[str], list[str]]:
    native_ready_reasons = [_reason_for_step(step) for step in local_steps + provider_steps]
    dispatch_ready_reasons = [_reason_for_step(step) for step in provider_steps]
    dispatch_ready_reasons.extend(
        _reason_for_step(step)
        for step in local_steps
        if step in {"set_required_environment", "configure_default_model", "start_omg_memory_server", "remove_incompatible_feature_flags"}
        or step.startswith("install_")
    )
    return native_ready_reasons, dispatch_ready_reasons


def _build_entrypoints(
    provider_name: str,
    *,
    project_dir: str,
    native_host_mode: str,
    native_runtime_paths: dict[str, str],
    native_ready: bool,
    native_ready_reasons: list[str],
    dispatch_ready: bool,
    dispatch_ready_reasons: list[str],
) -> dict[str, dict[str, Any]]:
    dispatch_host_mode = "claude_dispatch"
    dispatch_runtime_paths = get_host_runtime_paths(dispatch_host_mode, project_dir)
    return {
        "native": {
            "provider": provider_name,
            "host_mode": native_host_mode,
            "ready": native_ready,
            "ready_reasons": list(native_ready_reasons),
            "runtime_paths": dict(native_runtime_paths),
        },
        "dispatch": {
            "provider": provider_name,
            "host_mode": dispatch_host_mode,
            "ready": dispatch_ready,
            "ready_reasons": list(dispatch_ready_reasons),
            "runtime_paths": dict(dispatch_runtime_paths),
        },
    }


def _derive_parity_state(native_ready: bool, dispatch_ready: bool) -> str:
    if native_ready:
        return "native_ready"
    if dispatch_ready:
        return "dispatch_ready"
    return "blocked"


def _build_host_capabilities(provider_name: str) -> dict[str, Any]:
    parity = get_provider_host_parity(provider_name)
    return {
        "provider": provider_name,
        "native": dict(parity.get("native_host", {})),
        "dispatch": dict(parity.get("dispatch_host", {})),
    }


def _derive_fallback_policy(
    provider_name: str,
    *,
    native_ready: bool,
    dispatch_ready: bool,
    local_steps: list[str],
    provider_steps: list[str],
    live_smoke: dict[str, Any] | None,
) -> tuple[str, str, str, str, str, str]:
    if native_ready and dispatch_ready:
        return "", "", "", "", "", ""

    live_smoke = dict(live_smoke or {})
    fallback_provider = str(live_smoke.get("fallback_provider", "")).strip()
    fallback_reason = str(live_smoke.get("fallback_reason", "")).strip()
    fallback_mode = str(live_smoke.get("fallback_mode", "")).strip()
    fallback_trigger_class = str(live_smoke.get("fallback_trigger_class", "")).strip()
    fallback_execution_path = str(live_smoke.get("fallback_execution_path", "")).strip()
    fallback_decision_source = str(live_smoke.get("fallback_decision_source", "")).strip()
    if fallback_provider:
        return (
            fallback_provider,
            fallback_reason,
            fallback_mode,
            fallback_trigger_class,
            fallback_execution_path,
            fallback_decision_source,
        )

    blocking_class = str(live_smoke.get("blocking_class", "")).strip()
    if blocking_class == "service_disabled" and provider_name == "gemini":
        return "claude", "provider_service_disabled", "provider_failover", "hard_failure", "claude_native", "provider_bootstrap"
    if blocking_class == "authentication_required":
        return "claude", "provider_login_required", "provider_failover", "hard_failure", "claude_native", "provider_bootstrap"
    if "remove_incompatible_feature_flags" in local_steps:
        return "claude", "provider_config_incompatible", "provider_failover", "hard_failure", "claude_native", "provider_bootstrap"
    if "appeal_provider_account" in provider_steps:
        return "claude", "provider_service_disabled", "provider_failover", "hard_failure", "claude_native", "provider_bootstrap"
    return "", "", "", "", "", ""


def normalize_provider_status_matrix(project_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    providers_value = normalized.get("providers")
    if not isinstance(providers_value, list):
        return normalized

    rows: list[dict[str, Any]] = []
    for raw_row in providers_value:
        if not isinstance(raw_row, dict):
            rows.append({"provider": "", "status": "invalid"})
            continue
        row = dict(raw_row)
        provider_name = str(row.get("provider", "")).strip()
        native_host_mode = str(row.get("host_mode") or f"{provider_name}_native")
        native_runtime_paths = row.get("runtime_paths")
        if not isinstance(native_runtime_paths, dict):
            native_runtime_paths = get_host_runtime_paths(native_host_mode, project_dir)
            row["runtime_paths"] = native_runtime_paths

        native_ready = bool(row.get("native_ready"))
        dispatch_ready = bool(row.get("dispatch_ready"))
        local_steps = [str(step) for step in row.get("local_steps", []) if str(step).strip()]
        provider_steps = [str(step) for step in row.get("provider_steps", []) if str(step).strip()]
        native_ready_reasons = [str(reason) for reason in row.get("native_ready_reasons", []) if str(reason).strip()]
        dispatch_ready_reasons = [str(reason) for reason in row.get("dispatch_ready_reasons", []) if str(reason).strip()]
        row.setdefault("manual_steps", local_steps + [step for step in provider_steps if step not in local_steps])
        row.setdefault("host_capabilities", _build_host_capabilities(provider_name))
        row.setdefault(
            "entrypoints",
            _build_entrypoints(
                provider_name,
                project_dir=project_dir,
                native_host_mode=native_host_mode,
                native_runtime_paths=dict(native_runtime_paths),
                native_ready=native_ready,
                native_ready_reasons=native_ready_reasons,
                dispatch_ready=dispatch_ready,
                dispatch_ready_reasons=dispatch_ready_reasons,
            ),
        )
        row.setdefault("parity_state", _derive_parity_state(native_ready, dispatch_ready))
        row.setdefault("fallback_provider", "")
        row.setdefault("fallback_reason", "")
        row.setdefault("fallback_mode", "")
        row.setdefault("fallback_trigger_class", "")
        row.setdefault("fallback_execution_path", "")
        row.setdefault("fallback_decision_source", "")
        rows.append(row)

    normalized["providers"] = rows
    return normalized


def collect_provider_status(
    project_dir: str,
    providers: list[str] | None = None,
    *,
    include_smoke: bool = False,
    smoke_host_mode: str = "claude_dispatch",
) -> dict[str, Any]:
    return collect_provider_status_with_options(
        project_dir,
        providers=providers,
        include_smoke=include_smoke,
        smoke_host_mode=smoke_host_mode,
    )


def collect_provider_status_with_options(
    project_dir: str,
    *,
    providers: list[str] | None = None,
    include_smoke: bool = False,
    smoke_host_mode: str = "claude_dispatch",
) -> dict[str, Any]:
    resolved_providers = _resolve_providers(providers)
    mcp_server = check_memory_server()
    rows: list[dict[str, Any]] = []

    for provider_name in resolved_providers:
        provider = get_provider(provider_name)
        detected = False
        auth_ok: bool | None = None
        auth_message = "provider not registered"
        if provider is not None:
            try:
                detected = provider.detect()
            except Exception as exc:
                auth_message = f"detect failed: {exc}"
            else:
                try:
                    auth_ok, auth_message = provider.check_auth()
                except Exception as exc:
                    auth_message = f"auth check failed: {exc}"

        host_mode = f"{provider_name}_native"
        profile = get_host_execution_profile(host_mode) or {}
        runtime_paths = get_host_runtime_paths(host_mode, project_dir)
        bootstrap_state = _bootstrap_state(runtime_paths)
        native_ready = bool(
            detected
            and bootstrap_state["host_config_exists"]
            and bootstrap_state["project_mcp_exists"]
            and auth_ok is not False
        )
        dispatch_ready = bool(detected and auth_ok is not False)
        live_smoke: dict[str, Any] | None = None
        manual_steps = _manual_steps(
            provider_name,
            detected=detected,
            auth_ok=auth_ok,
            bootstrap_state=bootstrap_state,
        )
        if include_smoke and detected:
            live_smoke = run_provider_live_smoke(provider_name, project_dir, host_mode=smoke_host_mode)
            recovery_action = str(live_smoke.get("recovery_action", "")).strip()
            if recovery_action and recovery_action != "none" and recovery_action not in manual_steps:
                manual_steps.append(recovery_action)
            for action in live_smoke.get("additional_recovery_actions", []):
                if action and action not in manual_steps:
                    manual_steps.append(str(action))
        local_steps, provider_steps = _split_steps(manual_steps)
        native_ready_reasons, dispatch_ready_reasons = _build_readiness_reasons(
            local_steps=local_steps,
            provider_steps=provider_steps,
        )
        native_ready = native_ready and not native_ready_reasons
        dispatch_ready = dispatch_ready and not dispatch_ready_reasons
        (
            fallback_provider,
            fallback_reason,
            fallback_mode,
            fallback_trigger_class,
            fallback_execution_path,
            fallback_decision_source,
        ) = _derive_fallback_policy(
            provider_name,
            native_ready=native_ready,
            dispatch_ready=dispatch_ready,
            local_steps=local_steps,
            provider_steps=provider_steps,
            live_smoke=live_smoke,
        )

        rows.append(
            {
                "provider": provider_name,
                "host_mode": host_mode,
                "policy_mode": profile.get("policy_mode", "unknown"),
                "detected": detected,
                "auth_ok": auth_ok,
                "auth_message": auth_message,
                "runtime_paths": runtime_paths,
                "bootstrap_state": bootstrap_state,
                "native_ready": native_ready,
                "dispatch_ready": dispatch_ready,
                "local_steps": local_steps,
                "provider_steps": provider_steps,
                "native_ready_reasons": native_ready_reasons,
                "dispatch_ready_reasons": dispatch_ready_reasons,
                "manual_steps": manual_steps,
                "live_smoke": live_smoke,
                "host_capabilities": _build_host_capabilities(provider_name),
                "entrypoints": _build_entrypoints(
                    provider_name,
                    project_dir=project_dir,
                    native_host_mode=host_mode,
                    native_runtime_paths=runtime_paths,
                    native_ready=native_ready,
                    native_ready_reasons=native_ready_reasons,
                    dispatch_ready=dispatch_ready,
                    dispatch_ready_reasons=dispatch_ready_reasons,
                ),
                "parity_state": _derive_parity_state(native_ready, dispatch_ready),
                "fallback_provider": fallback_provider,
                "fallback_reason": fallback_reason,
                "fallback_mode": fallback_mode,
                "fallback_trigger_class": fallback_trigger_class,
                "fallback_execution_path": fallback_execution_path,
                "fallback_decision_source": fallback_decision_source,
            }
        )

    payload = {
        "schema": "ProviderStatusMatrix",
        "status": "ok",
        "project_dir": project_dir,
        "mcp_server": mcp_server,
        "providers": rows,
    }
    return normalize_provider_status_matrix(project_dir, payload)


def bootstrap_provider_hosts(
    project_dir: str,
    *,
    providers: list[str] | None = None,
    server_url: str | None = None,
    server_name: str = "omg-memory",
) -> dict[str, Any]:
    resolved_providers = _resolve_providers(providers)
    ensured = ensure_memory_server()
    mcp_server = dict(check_memory_server())
    mcp_server["ensure_status"] = ensured.get("status", "unknown")
    if ensured.get("message"):
        mcp_server["ensure_message"] = ensured.get("message")

    resolved_server_url = server_url or str(ensured.get("url") or mcp_server.get("url") or get_server_url())

    write_claude_mcp_config(project_dir, resolved_server_url, server_name)
    written_paths = [str(Path(project_dir) / ".mcp.json")]
    configured: list[str] = []
    repairs: dict[str, dict[str, Any]] = {}

    for provider_name in resolved_providers:
        writer = _WRITERS.get(provider_name)
        provider = get_provider(provider_name)
        if writer is None or provider is None:
            continue
        writer_result = writer(resolved_server_url, server_name)
        configured.append(provider_name)
        config_path = provider.get_config_path()
        if config_path:
            written_paths.append(config_path)
        if isinstance(writer_result, dict):
            repairs[provider_name] = dict(writer_result)

    status = collect_provider_status_with_options(project_dir, providers=resolved_providers, include_smoke=False)
    manual_steps = {
        entry["provider"]: entry["manual_steps"]
        for entry in status["providers"]
        if entry["manual_steps"]
    }
    return {
        "schema": "ProviderBootstrapResult",
        "status": "ok",
        "project_dir": project_dir,
        "server_url": resolved_server_url,
        "configured": configured,
        "written_paths": written_paths,
        "repairs": repairs,
        "mcp_server": mcp_server,
        "providers": status["providers"],
        "manual_steps": manual_steps,
    }


def repair_provider_hosts(
    project_dir: str,
    *,
    providers: list[str] | None = None,
    server_url: str | None = None,
    server_name: str = "omg-memory",
) -> dict[str, Any]:
    resolved_providers = _resolve_providers(providers)
    resolved_server_url = server_url or get_server_url()
    repairs: dict[str, dict[str, Any]] = {}
    manual_steps: dict[str, list[str]] = {}

    for provider_name in resolved_providers:
        if provider_name == "codex":
            repair = dict(write_codex_mcp_config(resolved_server_url, server_name))
            repairs[provider_name] = repair
            next_steps: list[str] = []
            if repair.get("removed_keys"):
                next_steps.append("login_to_provider")
            manual_steps[provider_name] = next_steps
            continue

        provider = get_provider(provider_name)
        repairs[provider_name] = {
            "config_path": provider.get_config_path() if provider is not None else "",
            "backup_path": "",
            "changed": False,
            "removed_keys": [],
        }
        manual_steps[provider_name] = []

    return {
        "schema": "ProviderRepairResult",
        "status": "ok",
        "project_dir": project_dir,
        "server_url": resolved_server_url,
        "providers": resolved_providers,
        "repairs": repairs,
        "manual_steps": manual_steps,
    }


__all__ = [
    "bootstrap_provider_hosts",
    "collect_provider_status",
    "collect_provider_status_with_options",
    "normalize_provider_status_matrix",
    "repair_provider_hosts",
]
