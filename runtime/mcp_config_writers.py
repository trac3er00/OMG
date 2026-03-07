from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    _ = tmp_path.write_text(content)
    _ = os.replace(tmp_path, path)


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        parsed = cast(object, json.loads(path.read_text()))
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _write_json(path: Path, data: dict[str, object]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def write_claude_mcp_config(project_dir: str, server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path(project_dir) / ".mcp.json"
    config = _load_json(config_path)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = {"type": "http", "url": server_url}
    _write_json(config_path, config)


def write_codex_mcp_config(server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path.home() / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing = config_path.read_text() if config_path.exists() else ""
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
        if existing and not existing.endswith("\n"):
            existing += "\n"
        content = existing + "".join(block)
        _atomic_write_text(config_path, content)
        return

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    updated_lines = lines[:start_idx] + block + lines[end_idx:]
    _atomic_write_text(config_path, "".join(updated_lines))


def write_gemini_mcp_config(server_url: str, server_name: str = "memory-server") -> None:
    config_path = Path.home() / ".gemini" / "settings.json"
    config = _load_json(config_path)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = {"httpUrl": server_url}
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
