from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from runtime.adoption import PRESET_LEVEL
from runtime.config_transaction import ConfigTransactionError
from runtime.mcp_config_writers import transactional


InstallActionKind = Literal["write_mcp_config", "write_settings", "write_cli_config"]

_MCP_ID_ALIASES: dict[str, str] = {
    "file-system": "filesystem",
    "file_system": "filesystem",
    "grep": "grep-app",
    "grep_app": "grep-app",
}

_DEFAULT_MCP_SPECS: dict[str, dict[str, Any]] = {
    "context7": {"command": "npx", "args": ["@upstash/context7-mcp@2.1.3"]},
    "filesystem": {
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem@2026.1.14", "."],
    },
    "websearch": {"command": "npx", "args": ["@zhafron/mcp-web-search@1.2.2"]},
    "chrome-devtools": {"command": "npx", "args": ["chrome-devtools-mcp@0.19.0"]},
    "omg-memory": {"type": "http", "url": "http://127.0.0.1:8765/mcp"},
    "omg-control": {"command": "python3", "args": ["-m", "runtime.omg_mcp_server"]},
    "grep-app": {"command": "npx", "args": ["grep-app-mcp"]},
}

_MCP_MIN_PRESET: dict[str, str] = {
    "filesystem": "safe",
    "omg-control": "safe",
    "context7": "balanced",
    "websearch": "interop",
    "omg-memory": "interop",
    "chrome-devtools": "labs",
}

_HOST_CONFIG_PATHS: dict[str, tuple[str, ...]] = {
    "codex": (".codex", "config.toml"),
    "gemini": (".gemini", "settings.json"),
    "kimi": (".kimi", "mcp.json"),
}


@dataclass
class InstallAction:
    host: str
    target_path: str
    description: str
    kind: InstallActionKind
    content: str
    mode: int = 0o600


@dataclass
class InstallPlan:
    actions: list[InstallAction]
    pre_checks: list[str]
    post_checks: list[str]
    source_root: str


class InstallResult(TypedDict):
    executed: bool
    actions_completed: list[str]
    actions_skipped: list[str]
    receipt: Any
    errors: list[str]


def _normalize_selected_ids(selected_ids: list[str] | None) -> list[str]:
    if selected_ids is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in selected_ids:
        candidate = _MCP_ID_ALIASES.get(item, item)
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _default_selected_ids_for_preset(preset: str) -> list[str]:
    level = PRESET_LEVEL.get(preset, 0)
    return [
        server_id
        for server_id, min_preset in _MCP_MIN_PRESET.items()
        if PRESET_LEVEL.get(min_preset, -1) <= level
    ]


def _resolve_selected_servers(
    *,
    selected_ids: list[str] | None,
    preset: str,
    selected_servers: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if selected_servers is not None:
        return selected_servers
    normalized_ids = _normalize_selected_ids(selected_ids)
    if not normalized_ids:
        normalized_ids = _default_selected_ids_for_preset(preset)
    return {
        server_id: cast(dict[str, Any], _DEFAULT_MCP_SPECS[server_id])
        for server_id in normalized_ids
        if server_id in _DEFAULT_MCP_SPECS
    }


def normalize_detected_clis(
    detected_clis: dict[str, Any] | None,
    *,
    home_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    home = home_path or Path.home()
    payload = detected_clis if isinstance(detected_clis, dict) else {}

    for host, raw_state in payload.items():
        state = dict(raw_state) if isinstance(raw_state, dict) else {}
        detected = bool(state.get("detected", False))
        configured_raw = state.get("configured")
        configured: bool
        if isinstance(configured_raw, bool):
            configured = configured_raw
        elif host in _HOST_CONFIG_PATHS:
            configured = (home / Path(*_HOST_CONFIG_PATHS[host])).exists()
        else:
            configured = False
        state["detected"] = detected
        state["configured"] = configured
        normalized[host] = state

    for host, rel_parts in _HOST_CONFIG_PATHS.items():
        if host in normalized:
            continue
        normalized[host] = {
            "detected": False,
            "configured": (home / Path(*rel_parts)).exists(),
        }

    return normalized


def _load_json_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return cast(dict[str, Any], parsed)


def _codex_header_candidates(server_name: str) -> set[str]:
    return {
        f"[mcp_servers.{server_name}]",
        f"[mcp_servers.\"{server_name}\"]",
    }


def _replace_codex_block(existing: str, block: list[str], server_name: str) -> str:
    lines = existing.splitlines(keepends=True)
    headers = _codex_header_candidates(server_name)
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() in headers:
            start_idx = idx
            break

    if start_idx is None:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        return existing + "".join(block)

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    return "".join(lines[:start_idx] + block + lines[end_idx:])


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    return escaped


def _apply_codex_http(existing: str, server_url: str, server_name: str) -> str:
    block = [
        f"[mcp_servers.{server_name}]\n",
        'type = "http"\n',
        f'url = "{_toml_quote(server_url)}"\n',
        "\n",
    ]
    return _replace_codex_block(existing, block, server_name)


def _apply_codex_stdio(existing: str, command: str, args: list[str], server_name: str) -> str:
    args_text = ", ".join(f'"{_toml_quote(arg)}"' for arg in args)
    block = [
        f"[mcp_servers.{server_name}]\n",
        f'command = "{_toml_quote(command)}"\n',
        f"args = [{args_text}]\n",
        "\n",
    ]
    return _replace_codex_block(existing, block, server_name)


def _compute_claude_content(
    *,
    project_dir: Path,
    selected_servers: dict[str, dict[str, Any]],
    managed_server_ids: set[str],
    http_memory_allowed: bool,
    server_url: str,
    server_name: str,
    control_command: str,
    control_args: list[str],
    control_server_name: str,
) -> str:
    config_path = project_dir / ".mcp.json"
    claude_config = _load_json_path(config_path)
    existing_servers = claude_config.get("mcpServers")
    if not isinstance(existing_servers, dict):
        existing_servers = {}

    for managed_server_id in managed_server_ids:
        existing_servers.pop(managed_server_id, None)
    existing_servers.pop(server_name, None)
    existing_servers.pop(control_server_name, None)

    for selected_server_name, payload in selected_servers.items():
        if selected_server_name == "omg-memory":
            if not http_memory_allowed:
                continue
            target_name = server_name
            target_payload: dict[str, Any] = {"type": "http", "url": server_url}
        elif selected_server_name == "omg-control":
            target_name = control_server_name
            target_payload = {"command": control_command, "args": control_args}
        else:
            target_name = selected_server_name
            target_payload = payload
        existing_servers[target_name] = target_payload

    claude_config["mcpServers"] = existing_servers
    return json.dumps(claude_config, indent=2, ensure_ascii=True) + "\n"


def _compute_json_host_content(
    *,
    host: str,
    target_path: Path,
    selected_servers: dict[str, dict[str, Any]],
    http_memory_allowed: bool,
    server_url: str,
    server_name: str,
    control_command: str,
    control_args: list[str],
    control_server_name: str,
) -> str:
    data = _load_json_path(target_path)
    mcp_servers = data.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}

    for selected_server_name, payload in selected_servers.items():
        if selected_server_name == "omg-memory":
            if not http_memory_allowed:
                continue
            if host == "gemini":
                mcp_servers[server_name] = {"httpUrl": server_url}
            else:
                mcp_servers[server_name] = {"type": "http", "url": server_url}
            continue

        if selected_server_name == "omg-control":
            mcp_servers[control_server_name] = {
                "command": control_command,
                "args": control_args,
            }
            continue

        if payload.get("type") == "http":
            url = str(payload.get("url", ""))
            if host == "gemini":
                mcp_servers[selected_server_name] = {"httpUrl": url}
            else:
                mcp_servers[selected_server_name] = {"type": "http", "url": url}
            continue

        mcp_servers[selected_server_name] = {
            "command": str(payload.get("command", "")),
            "args": [str(arg) for arg in cast(list[Any], payload.get("args", []))],
        }

    data["mcpServers"] = mcp_servers
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"


def _compute_codex_content(
    *,
    target_path: Path,
    selected_servers: dict[str, dict[str, Any]],
    http_memory_allowed: bool,
    server_url: str,
    server_name: str,
    control_command: str,
    control_args: list[str],
    control_server_name: str,
) -> str:
    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    content = existing
    for selected_server_name, payload in selected_servers.items():
        if selected_server_name == "omg-memory":
            if not http_memory_allowed:
                continue
            content = _apply_codex_http(content, server_url, server_name)
            continue

        if selected_server_name == "omg-control":
            content = _apply_codex_stdio(content, control_command, control_args, control_server_name)
            continue

        if payload.get("type") == "http":
            content = _apply_codex_http(content, str(payload.get("url", "")), selected_server_name)
            continue

        content = _apply_codex_stdio(
            content,
            str(payload.get("command", "")),
            [str(arg) for arg in cast(list[Any], payload.get("args", []))],
            selected_server_name,
        )
    return content


def compute_install_plan(
    project_dir: str,
    detected_clis: dict[str, Any],
    preset: str,
    mode: str,
    selected_ids: list[str] | None,
    *,
    server_url: str = "http://127.0.0.1:8765/mcp",
    server_name: str = "omg-memory",
    control_command: str = "python3",
    control_args: list[str] | None = None,
    control_server_name: str = "omg-control",
    selected_servers: dict[str, dict[str, Any]] | None = None,
    source_root: str | Path | None = None,
    include_claude_action: bool = True,
) -> InstallPlan:
    del mode

    project_path = Path(project_dir)
    normalized_clis = normalize_detected_clis(detected_clis)
    resolved_control_args = list(control_args or ["-m", "runtime.omg_mcp_server"])
    selected = _resolve_selected_servers(
        selected_ids=selected_ids,
        preset=preset,
        selected_servers=selected_servers,
    )
    source = Path(source_root) if source_root is not None else Path(__file__).resolve().parent.parent
    http_memory_allowed = PRESET_LEVEL.get(preset, 0) >= PRESET_LEVEL.get("interop", 2)
    managed_server_ids = set(_DEFAULT_MCP_SPECS)

    actions: list[InstallAction] = []

    if include_claude_action:
        claude_target = project_path / ".mcp.json"
        claude_content = _compute_claude_content(
            project_dir=project_path,
            selected_servers=selected,
            managed_server_ids=managed_server_ids,
            http_memory_allowed=http_memory_allowed,
            server_url=server_url,
            server_name=server_name,
            control_command=control_command,
            control_args=resolved_control_args,
            control_server_name=control_server_name,
        )
        actions.append(
            InstallAction(
                host="claude",
                target_path=str(claude_target),
                description="Write project MCP server config",
                kind="write_mcp_config",
                content=claude_content,
            )
        )

    home = Path.home()
    host_targets: dict[str, Path] = {
        "codex": home / ".codex" / "config.toml",
        "gemini": home / ".gemini" / "settings.json",
        "kimi": home / ".kimi" / "mcp.json",
    }

    for host, target_path in host_targets.items():
        cli_info = normalized_clis.get(host)
        if not isinstance(cli_info, dict) or not bool(cli_info.get("detected", False)):
            continue

        if host == "codex":
            content = _compute_codex_content(
                target_path=target_path,
                selected_servers=selected,
                http_memory_allowed=http_memory_allowed,
                server_url=server_url,
                server_name=server_name,
                control_command=control_command,
                control_args=resolved_control_args,
                control_server_name=control_server_name,
            )
        else:
            content = _compute_json_host_content(
                host=host,
                target_path=target_path,
                selected_servers=selected,
                http_memory_allowed=http_memory_allowed,
                server_url=server_url,
                server_name=server_name,
                control_command=control_command,
                control_args=resolved_control_args,
                control_server_name=control_server_name,
            )

        actions.append(
            InstallAction(
                host=host,
                target_path=str(target_path),
                description=f"Write {host} MCP config",
                kind="write_cli_config",
                content=content,
            )
        )

    return InstallPlan(
        actions=actions,
        pre_checks=["verify_install_integrity"],
        post_checks=["post_install_validation"],
        source_root=str(source),
    )


def _verify_install_integrity(source_root: Path) -> list[str]:
    manifest = source_root / "INSTALL_INTEGRITY.sha256"
    if not manifest.exists():
        return []

    errors: list[str] = []
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_hash, rel_path = parts
        target = source_root / rel_path
        if not target.exists() or not target.is_file():
            errors.append(f"integrity failure: {rel_path} not found")
            continue
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            errors.append(
                f"integrity failure: {rel_path} hash mismatch (expected {expected_hash}, got {actual_hash})"
            )
    return errors


def execute_plan(plan: InstallPlan, *, dry_run: bool = False) -> InstallResult:
    errors: list[str] = []
    completed: list[str] = []
    skipped: list[str] = []
    receipt: Any = None

    if "verify_install_integrity" in plan.pre_checks:
        errors.extend(_verify_install_integrity(Path(plan.source_root)))

    if errors:
        skipped = [action.target_path for action in plan.actions]
        return {
            "executed": False,
            "actions_completed": completed,
            "actions_skipped": skipped,
            "receipt": receipt,
            "errors": errors,
        }

    with transactional() as tx:
        for action in plan.actions:
            if not dry_run:
                Path(action.target_path).parent.mkdir(parents=True, exist_ok=True)
            tx.plan(Path(action.target_path), action.content, mode=action.mode)
            completed.append(action.target_path)

        try:
            if dry_run:
                receipt = cast(Any, tx.dry_run())
            else:
                receipt = cast(Any, tx.execute())
        except ConfigTransactionError as exc:
            if exc.receipt is not None:
                receipt = cast(Any, exc.receipt)
            errors.append(str(exc))

    if errors:
        return {
            "executed": False,
            "actions_completed": [],
            "actions_skipped": [action.target_path for action in plan.actions],
            "receipt": receipt,
            "errors": errors,
        }

    return {
        "executed": not dry_run,
        "actions_completed": completed,
        "actions_skipped": skipped,
        "receipt": receipt,
        "errors": errors,
    }
