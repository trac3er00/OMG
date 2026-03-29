from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator, cast

try:
    import tomlkit
    import tomlkit.exceptions
except ImportError:  # Portable runtime may run without third-party TOML support.
    tomlkit = None

from hooks.security_validators import (
    toml_quote_string,
    validate_server_name,
    validate_server_url,
)

if TYPE_CHECKING:
    from runtime.config_transaction import ConfigTransaction

_O_NOFOLLOW: int = getattr(os, "O_NOFOLLOW", 0)

_active_transaction: ConfigTransaction | None = None
_planned_content: dict[str, str] = {}
_last_receipt: dict[str, Any] | None = None
_logger = logging.getLogger(__name__)


def _require_tomlkit() -> None:
    if tomlkit is None:
        raise RuntimeError("tomlkit is required for Codex TOML config writes")


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
        except OSError as exc:
            _logger.debug("Failed to remove temporary config file after write failure: %s", exc, exc_info=True)
        raise
    else:
        os.close(fd)

    os.replace(str(tmp_path), str(path))
    _fsync_dir(path.parent)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_text_safe(path, content)


@contextlib.contextmanager
def transactional() -> Generator[ConfigTransaction, None, None]:
    """Batch all writer calls inside this context into a single ConfigTransaction.

    Writers detect the active transaction and plan into it instead of writing
    immediately.  The caller MUST call ``tx.execute()`` before leaving the
    block — the context manager only manages the ``_active_transaction``
    lifecycle, not the commit.
    """
    global _active_transaction  # noqa: PLW0603
    from runtime.config_transaction import ConfigTransaction as _CT

    if _active_transaction is not None:
        raise RuntimeError("nested transactions not supported")
    tx_lock_dir = Path(tempfile.mkdtemp(prefix="omg-tx-"))
    tx = _CT(lock_path=tx_lock_dir / "tx.lock", backup_root=tx_lock_dir / "backups")
    _active_transaction = tx
    _planned_content.clear()
    try:
        yield tx
    finally:
        _active_transaction = None
        _planned_content.clear()
        try:
            shutil.rmtree(tx_lock_dir, ignore_errors=True)
        except OSError as exc:
            _logger.debug("Failed to remove temporary transaction lock directory: %s", exc, exc_info=True)


def _get_current_content(path: Path) -> str:
    resolved_key = str(path.resolve())
    if _active_transaction is not None and resolved_key in _planned_content:
        return _planned_content[resolved_key]
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def _write_with_transaction(path: Path, content: str, *, mode: int = 0o600) -> None:
    global _last_receipt  # noqa: PLW0603

    resolved = str(path.resolve())

    if _active_transaction is not None:
        _active_transaction.plan(path, content, mode=mode)
        _planned_content[resolved] = content
        return

    _atomic_write_text_safe(path, content, mode=mode)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    _last_receipt = {
        "planned_writes": [{"path": resolved, "content_hash": content_hash}],
        "executed_writes": [{"path": resolved, "content_hash": content_hash, "executed": True}],
        "backup_path": "",
        "verification": {resolved: "ok"},
        "executed": True,
        "rollback": None,
    }


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


def _load_json_content(raw: str) -> dict[str, object]:
    if not raw.strip():
        return {}
    try:
        parsed = cast(object, json.loads(raw))
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _write_json(path: Path, data: dict[str, object]) -> None:
    _write_with_transaction(path, json.dumps(data, indent=2) + "\n")


def _write_json_mcp_server(path: Path, server_name: str, payload: dict[str, object]) -> None:
    existing = _get_current_content(path)
    config = _load_json_content(existing)
    mcp_servers = config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
        config["mcpServers"] = mcp_servers
    mcp_servers[server_name] = payload
    _write_json(path, config)


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


def _compute_codex_toml_http(target_path: Path, server_url: str, server_name: str) -> str:
    _require_tomlkit()
    existing = _get_current_content(target_path)
    try:
        doc = tomlkit.parse(existing) if existing else tomlkit.document()
    except tomlkit.exceptions.ParseError as exc:
        raise ValueError(f"Malformed TOML in {target_path}: {exc}") from exc

    if "mcp_servers" not in doc:
        doc.add("mcp_servers", tomlkit.table(is_super_table=True))

    entry = tomlkit.table()
    entry.add("type", "http")
    entry.add("url", toml_quote_string(server_url))
    doc["mcp_servers"][server_name] = entry

    return tomlkit.dumps(doc)


def _compute_codex_toml_stdio(target_path: Path, command: str, args: list[str], server_name: str) -> str:
    _require_tomlkit()
    existing = _get_current_content(target_path)
    try:
        doc = tomlkit.parse(existing) if existing else tomlkit.document()
    except tomlkit.exceptions.ParseError as exc:
        raise ValueError(f"Malformed TOML in {target_path}: {exc}") from exc

    if "mcp_servers" not in doc:
        doc.add("mcp_servers", tomlkit.table(is_super_table=True))

    entry = tomlkit.table()
    entry.add("command", toml_quote_string(command))
    entry.add("args", [toml_quote_string(a) for a in args])
    doc["mcp_servers"][server_name] = entry

    return tomlkit.dumps(doc)


def write_codex_mcp_config(
    server_url: str,
    server_name: str = "memory-server",
    *,
    config_path: str | Path | None = None,
) -> None:
    server_url, server_name = _validated_server_input(server_url, server_name)
    target_path = Path(config_path) if config_path is not None else Path.home() / ".codex" / "config.toml"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = _compute_codex_toml_http(target_path, server_url, server_name)
    _write_with_transaction(target_path, content)


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
    content = _compute_codex_toml_stdio(target_path, command, args, server_name)
    _write_with_transaction(target_path, content)


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
