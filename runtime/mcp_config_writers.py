from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from hooks.security_validators import (
    toml_quote_string,
    validate_server_name,
    validate_server_url,
)

# O_NOFOLLOW is available on macOS/Linux but not on Windows.
_O_NOFOLLOW: int = getattr(os, "O_NOFOLLOW", 0)


def _fsync_dir(path: Path | str) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_text_safe(
    path: Path,
    content: str,
    *,
    mode: int = 0o600,
) -> None:
    """Write *content* to *path* atomically with full durability guarantees.

    Contract:
    1. Writes to a temp file in the same directory as *path* (same-filesystem).
    2. Uses ``os.open`` with ``O_CREAT | O_WRONLY | O_TRUNC`` and explicit *mode*.
    3. Rejects symlink targets and symlink tmp paths (raises ``OSError``).
    4. Calls ``os.fsync(fd)`` before ``os.replace`` (data durable).
    5. Calls ``_fsync_dir`` after ``os.replace`` (directory entry durable).
    6. Cleans up the temp file on any failure before rename.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() or path.is_symlink():
        st = os.lstat(path)
        import stat as stat_mod
        if stat_mod.S_ISLNK(st.st_mode):
            raise OSError(f"Refusing to write through symlink target: {path}")

    tmp_path = path.with_name(f"{path.name}.tmp")
    if tmp_path.exists() or tmp_path.is_symlink():
        st = os.lstat(tmp_path)
        import stat as stat_mod
        if stat_mod.S_ISLNK(st.st_mode):
            raise OSError(f"Refusing to write through symlink tmp path: {tmp_path}")
        # Not a symlink — remove stale tmp file
        tmp_path.unlink()

    open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW
    fd = os.open(str(tmp_path), open_flags, mode)
    try:
        data = content.encode("utf-8")
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    else:
        os.close(fd)

    os.replace(str(tmp_path), str(path))
    _fsync_dir(path.parent)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_text_safe(path, content)


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


def get_managed_python_path(claude_config_dir: str | None = None) -> str:
    """Return the absolute path to the managed OMG venv Python interpreter.

    Falls back to ``CLAUDE_CONFIG_DIR`` env var, then ``~/.claude``.
    """
    if claude_config_dir is None:
        claude_config_dir = os.environ.get(
            "CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")
        )
    return str(Path(claude_config_dir) / "omg-runtime" / ".venv" / "bin" / "python")


def _validated_server_input(server_url: str, server_name: str) -> tuple[str, str]:
    return validate_server_url(server_url), validate_server_name(server_name)


def _validated_stdio_input(command: str, args: list[str], server_name: str) -> tuple[str, list[str], str]:
    normalized_name = validate_server_name(server_name)
    normalized_command = str(command).strip()
    if not normalized_command or "\n" in normalized_command or "\r" in normalized_command:
        raise ValueError("Invalid command: newline characters are not allowed")
    normalized_args = [str(arg) for arg in args]
    for arg in normalized_args:
        if "\n" in arg or "\r" in arg:
            raise ValueError("Invalid args: newline characters are not allowed")
    return normalized_command, normalized_args, normalized_name


def _write_json_mcp_server(path: Path, server_name: str, payload: dict[str, object]) -> None:
    config = _load_json(path)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = payload
    _write_json(path, config)


def write_claude_mcp_config(project_dir: str, server_url: str, server_name: str = "memory-server") -> None:
    server_url, server_name = _validated_server_input(server_url, server_name)
    config_path = Path(project_dir) / ".mcp.json"
    _write_json_mcp_server(config_path, server_name, {"type": "http", "url": server_url})


def write_claude_mcp_stdio_config(
    project_dir: str,
    *,
    command: str,
    args: list[str],
    server_name: str = "omg-control",
) -> None:
    command, args, server_name = _validated_stdio_input(command, args, server_name)
    config_path = Path(project_dir) / ".mcp.json"
    _write_json_mcp_server(config_path, server_name, {"command": command, "args": args})


def write_codex_mcp_config(
    server_url: str,
    server_name: str = "memory-server",
    *,
    config_path: str | Path | None = None,
) -> None:
    server_url, server_name = _validated_server_input(server_url, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".codex" / "config.toml"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    existing = target_path.read_text() if target_path.exists() else ""
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
        f'url = "{toml_quote_string(server_url)}"\n',
        "\n",
    ]

    if start_idx is None:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        content = existing + "".join(block)
        _atomic_write_text(target_path, content)
        return

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    updated_lines = lines[:start_idx] + block + lines[end_idx:]
    _atomic_write_text(target_path, "".join(updated_lines))


def write_codex_mcp_stdio_config(
    *,
    command: str,
    args: list[str],
    server_name: str = "omg-control",
    config_path: str | Path | None = None,
) -> None:
    command, args, server_name = _validated_stdio_input(command, args, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".codex" / "config.toml"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    existing = target_path.read_text() if target_path.exists() else ""
    lines = existing.splitlines(keepends=True)
    header_unquoted = f"[mcp_servers.{server_name}]"
    header_quoted = f"[mcp_servers.\"{server_name}\"]"
    headers = {header_unquoted, header_quoted}

    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() in headers:
            start_idx = idx
            break

    args_text = ", ".join(f'"{toml_quote_string(arg)}"' for arg in args)
    block = [
        f"{header_unquoted}\n",
        f'command = "{toml_quote_string(command)}"\n',
        f"args = [{args_text}]\n",
        "\n",
    ]

    if start_idx is None:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        _atomic_write_text(target_path, existing + "".join(block))
        return

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_idx = idx
            break

    updated_lines = lines[:start_idx] + block + lines[end_idx:]
    _atomic_write_text(target_path, "".join(updated_lines))


def write_gemini_mcp_config(
    server_url: str,
    server_name: str = "memory-server",
    *,
    config_path: str | Path | None = None,
) -> None:
    server_url, server_name = _validated_server_input(server_url, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".gemini" / "settings.json"
    _write_json_mcp_server(target_path, server_name, {"httpUrl": server_url})


def write_gemini_mcp_stdio_config(
    *,
    command: str,
    args: list[str],
    server_name: str = "omg-control",
    config_path: str | Path | None = None,
) -> None:
    command, args, server_name = _validated_stdio_input(command, args, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".gemini" / "settings.json"
    _write_json_mcp_server(target_path, server_name, {"command": command, "args": args})


def write_kimi_mcp_config(
    server_url: str,
    server_name: str = "memory-server",
    *,
    config_path: str | Path | None = None,
) -> None:
    server_url, server_name = _validated_server_input(server_url, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".kimi" / "mcp.json"
    _write_json_mcp_server(target_path, server_name, {"type": "http", "url": server_url})


def write_kimi_mcp_stdio_config(
    *,
    command: str,
    args: list[str],
    server_name: str = "omg-control",
    config_path: str | Path | None = None,
) -> None:
    command, args, server_name = _validated_stdio_input(command, args, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".kimi" / "mcp.json"
    _write_json_mcp_server(target_path, server_name, {"command": command, "args": args})
