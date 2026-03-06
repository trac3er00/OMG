from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone
from typing import cast


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    _ = tmp_path.write_text(content, encoding="utf-8")
    _ = os.replace(tmp_path, path)


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return {}
    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else {}


def _write_json(path: Path, data: dict[str, object]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def _backup_file(path: Path) -> str:
    if not path.exists():
        return ""
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{path.name}.{timestamp}.bak"
    shutil.copy2(path, backup_path)
    return str(backup_path)


def _remove_codex_incompatible_feature_flags(existing: str) -> tuple[str, list[str]]:
    lines = existing.splitlines(keepends=True)
    cleaned: list[str] = []
    removed_keys: list[str] = []
    current_section = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped
            cleaned.append(line)
            continue

        if current_section == "[features]":
            match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
            if match:
                key = match.group(1)
                if key == "rmcp_client":
                    if key not in removed_keys:
                        removed_keys.append(key)
                    continue

        cleaned.append(line)

    return "".join(cleaned), removed_keys


def _upsert_codex_mcp_block(existing: str, server_url: str, server_name: str) -> str:
    lines = existing.splitlines(keepends=True)

    header_unquoted = f"[mcp_servers.{server_name}]"
    header_quoted = f"[mcp_servers.\"{server_name}\"]"
    headers = {header_unquoted, header_quoted}

    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() in headers:
            start_idx = idx
            break

    block = [
        f"{header_unquoted}\n",
        'type = "http"\n',
        f'url = "{server_url}"\n',
        "\n",
    ]

    if start_idx is None:
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        return prefix + "".join(block)

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    updated_lines = lines[:start_idx] + block + lines[end_idx:]
    return "".join(updated_lines)


def write_claude_mcp_config(project_dir: str, server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path(project_dir) / ".mcp.json"
    config = _load_json(config_path)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = {"type": "http", "url": server_url}
    _write_json(config_path, config)


def write_codex_mcp_config(server_url: str, server_name: str = "memory-server") -> dict[str, object]:
    config_path = Path.home() / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    repaired, removed_keys = _remove_codex_incompatible_feature_flags(existing)
    updated = _upsert_codex_mcp_block(repaired, server_url, server_name)
    changed = updated != existing
    backup_path = _backup_file(config_path) if changed and config_path.exists() else ""
    if changed or not config_path.exists():
        _atomic_write_text(config_path, updated)
    return {
        "config_path": str(config_path),
        "backup_path": backup_path,
        "changed": changed,
        "removed_keys": removed_keys,
    }


def write_gemini_mcp_config(server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path.home() / ".gemini" / "settings.json"
    config = _load_json(config_path)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = {"httpUrl": server_url}
    _write_json(config_path, config)


def write_opencode_mcp_config(server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path.home() / ".config" / "opencode" / "opencode.json"
    config = _load_json(config_path)
    mcp_servers = config.get("mcp")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcp"] = mcp_servers
    mcp_servers[server_name] = {"type": "remote", "url": server_url}
    _write_json(config_path, config)


def write_kimi_mcp_config(server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path.home() / ".kimi" / "mcp.json"
    config = _load_json(config_path)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = {"type": "http", "url": server_url}
    _write_json(config_path, config)


__all__ = [
    "write_claude_mcp_config",
    "write_codex_mcp_config",
    "write_gemini_mcp_config",
    "write_opencode_mcp_config",
    "write_kimi_mcp_config",
]
