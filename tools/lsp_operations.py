"""LSP operations — 11 high-level functions exposing LSP tools to agents.

Built on top of ``tools.lsp_client.LSPClient``.  Each function:
- Returns a graceful default (empty list / None / False / dict) when disabled or on error.
- Never raises exceptions to callers.
- Checks the ``OMG_LSP_TOOLS_ENABLED`` feature flag via env var or settings.json.

Feature flag: ``OMG_LSP_TOOLS_ENABLED`` (default: False / opt-in only).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from tools.lsp_client import LSPClient

_logger = logging.getLogger(__name__)
logger = _logger

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: LSPClient | None = None

# LSP diagnostic severity codes → human-readable names
_SEVERITY_MAP: dict[int, str] = {
    1: "error",
    2: "warning",
    3: "information",
    4: "hint",
}

# LSP SymbolKind enum → human-readable names
_SYMBOL_KIND_MAP: dict[int, str] = {
    1: "File", 2: "Module", 3: "Namespace", 4: "Package",
    5: "Class", 6: "Method", 7: "Property", 8: "Field",
    9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
    13: "Variable", 14: "Constant", 15: "String", 16: "Number",
    17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
    21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
    25: "Operator", 26: "TypeParameter",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_enabled() -> bool:
    """Check whether the LSP tools feature flag is on.

    Resolution order mirrors ``hooks/_common.get_feature_flag``:
    env var ``OMG_LSP_TOOLS_ENABLED`` → ``settings.json`` → default (False).
    """
    env_val = os.environ.get("OMG_LSP_TOOLS_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Slow path: try get_feature_flag for settings.json support
    try:
        import sys as _sys

        _hooks = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "hooks",
        )
        if _hooks not in _sys.path:
            _sys.path.insert(0, _hooks)
        from _common import get_feature_flag  # type: ignore[import-untyped]

        return get_feature_flag("LSP_TOOLS", default=False)
    except Exception:
        _logger.debug("Failed to resolve LSP feature flag", exc_info=True)
        return False


def _file_uri(file_path: str) -> str:
    """Convert a filesystem path to a ``file://`` URI."""
    return Path(file_path).resolve().as_uri()


def _position_params(file_path: str, line: int, character: int) -> dict[str, Any]:
    """Build ``TextDocumentPositionParams``."""
    return {
        "textDocument": {"uri": _file_uri(file_path)},
        "position": {"line": line, "character": character},
    }


def _normalize_locations(result: Any) -> list[dict]:
    """Normalize an LSP Location / Location[] / LocationLink[] result."""
    if result is None:
        return []
    if isinstance(result, dict):
        return [{"uri": result.get("uri", ""), "range": result.get("range", {})}]
    if isinstance(result, list):
        locations: list[dict] = []
        for item in result:
            if isinstance(item, dict):
                uri = item.get("uri", item.get("targetUri", ""))
                range_ = item.get("range", item.get("targetRange", {}))
                locations.append({"uri": uri, "range": range_})
        return locations
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_client() -> LSPClient:
    """Return the module-level LSP client singleton (lazy-init).

    Raises ``RuntimeError`` when ``OMG_LSP_TOOLS_ENABLED`` is False.
    """
    global _client
    if not _is_enabled():
        raise RuntimeError(
            "LSP tools are disabled — set OMG_LSP_TOOLS_ENABLED=1 to enable"
        )
    if _client is None:
        _client = LSPClient()
    return _client


# -- 1. Diagnostics --------------------------------------------------------

def lsp_diagnostics(file_path: str) -> list[dict]:
    """Pull diagnostics for *file_path*.

    Returns a list of ``{severity, message, range}`` dicts.
    """
    try:
        client = get_client()
        result = client.send_request(
            "textDocument/diagnostic",
            {"textDocument": {"uri": _file_uri(file_path)}},
        )
        if result is None:
            return []
        items = result.get("items", [])
        return [
            {
                "severity": _SEVERITY_MAP.get(d.get("severity", 1), "unknown"),
                "message": d.get("message", ""),
                "range": d.get("range", {}),
            }
            for d in items
            if isinstance(d, dict)
        ]
    except Exception:
        _logger.debug("Failed to fetch LSP diagnostics", exc_info=True)
        return []


# -- 2. Go to definition ---------------------------------------------------

def lsp_definition(file_path: str, line: int, character: int) -> list[dict]:
    """Go-to-definition at the given position.

    Returns a list of ``{uri, range}`` location dicts.
    """
    try:
        client = get_client()
        result = client.send_request(
            "textDocument/definition", _position_params(file_path, line, character),
        )
        return _normalize_locations(result)
    except Exception:
        _logger.debug("Failed to resolve LSP definition", exc_info=True)
        return []


# -- 3. Go to type definition ----------------------------------------------

def lsp_type_definition(file_path: str, line: int, character: int) -> list[dict]:
    """Go-to-type-definition at the given position.

    Returns a list of ``{uri, range}`` location dicts.
    """
    try:
        client = get_client()
        result = client.send_request(
            "textDocument/typeDefinition",
            _position_params(file_path, line, character),
        )
        return _normalize_locations(result)
    except Exception:
        _logger.debug("Failed to resolve LSP type definition", exc_info=True)
        return []


# -- 4. Go to implementation -----------------------------------------------

def lsp_implementation(file_path: str, line: int, character: int) -> list[dict]:
    """Find implementations at the given position.

    Returns a list of ``{uri, range}`` location dicts.
    """
    try:
        client = get_client()
        result = client.send_request(
            "textDocument/implementation",
            _position_params(file_path, line, character),
        )
        return _normalize_locations(result)
    except Exception:
        _logger.debug("Failed to resolve LSP implementations", exc_info=True)
        return []


# -- 5. Find references ----------------------------------------------------

def lsp_references(
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
) -> list[dict]:
    """Find all references to the symbol at the given position.

    Returns a list of ``{uri, range}`` location dicts.
    """
    try:
        client = get_client()
        params = _position_params(file_path, line, character)
        params["context"] = {"includeDeclaration": include_declaration}
        result = client.send_request("textDocument/references", params)
        return _normalize_locations(result)
    except Exception:
        _logger.debug("Failed to resolve LSP references", exc_info=True)
        return []


# -- 6. Hover --------------------------------------------------------------

def lsp_hover(file_path: str, line: int, character: int) -> str | None:
    """Hover information at the given position.

    Returns the hover text as a string, or ``None``.
    """
    try:
        client = get_client()
        result = client.send_request(
            "textDocument/hover", _position_params(file_path, line, character),
        )
        if result is None:
            return None
        contents = result.get("contents", "")
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            return contents.get("value", str(contents))
        if isinstance(contents, list):
            parts: list[str] = []
            for part in contents:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.append(part.get("value", str(part)))
            return "\n".join(parts)
        return str(contents)
    except Exception:
        _logger.debug("Failed to fetch LSP hover data", exc_info=True)
        return None


# -- 7. Document symbols ----------------------------------------------------

def lsp_symbols(file_path: str) -> list[dict]:
    """Document symbols for *file_path*.

    Returns a list of ``{name, kind, range}`` dicts.
    """
    try:
        client = get_client()
        result = client.send_request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": _file_uri(file_path)}},
        )
        if result is None:
            return []
        if not isinstance(result, list):
            return []
        return [
            {
                "name": sym.get("name", ""),
                "kind": _SYMBOL_KIND_MAP.get(sym.get("kind", 0), "Unknown"),
                "range": sym.get("range", sym.get("location", {}).get("range", {})),
            }
            for sym in result
            if isinstance(sym, dict)
        ]
    except Exception:
        _logger.debug("Failed to fetch LSP document symbols", exc_info=True)
        return []


# -- 8. Rename --------------------------------------------------------------

def lsp_rename(
    file_path: str, line: int, character: int, new_name: str,
) -> dict:
    """Rename the symbol at the given position.

    Returns a workspace-edit dict (``{changes, documentChanges}``).
    """
    try:
        client = get_client()
        params = _position_params(file_path, line, character)
        params["newName"] = new_name
        result = client.send_request("textDocument/rename", params)
        if result is None:
            return {}
        return result
    except Exception:
        _logger.debug("Failed to execute LSP rename", exc_info=True)
        return {}


# -- 9. Code actions --------------------------------------------------------

def lsp_code_actions(file_path: str, line: int, character: int) -> list[dict]:
    """Available code actions at the given position.

    Returns a list of ``{title, kind}`` dicts.
    """
    try:
        client = get_client()
        pos = {"line": line, "character": character}
        result = client.send_request(
            "textDocument/codeAction",
            {
                "textDocument": {"uri": _file_uri(file_path)},
                "range": {"start": pos, "end": pos},
                "context": {"diagnostics": []},
            },
        )
        if result is None:
            return []
        if not isinstance(result, list):
            return []
        return [
            {
                "title": action.get("title", ""),
                "kind": action.get("kind", ""),
            }
            for action in result
            if isinstance(action, dict)
        ]
    except Exception:
        _logger.debug("Failed to fetch LSP code actions", exc_info=True)
        return []


# -- 10. Status -------------------------------------------------------------

def lsp_status() -> dict:
    """Return the current LSP client status.

    Returns ``{connected: bool, server_name: str | None, capabilities: dict}``.
    """
    try:
        if not _is_enabled():
            return {"connected": False, "server_name": None, "capabilities": {}}
        if _client is None:
            return {"connected": False, "server_name": None, "capabilities": {}}
        return {
            "connected": _client.is_connected(),
            "server_name": getattr(_client, "_server_name", None),
            "capabilities": getattr(_client, "_capabilities", {}),
        }
    except Exception:
        _logger.debug("Failed to read LSP status", exc_info=True)
        return {"connected": False, "server_name": None, "capabilities": {}}


# -- 11. Reload -------------------------------------------------------------

def lsp_reload() -> bool:
    """Restart the LSP client singleton.

    Shuts down any existing client, creates a fresh one.
    Returns ``True`` on success, ``False`` on failure or disabled.
    """
    global _client
    try:
        if not _is_enabled():
            return False
        if _client is not None:
            try:
                _client.shutdown()
            except Exception:
                _logger.debug("Failed to shutdown existing LSP client", exc_info=True)
        _client = LSPClient()
        return True
    except Exception:
        _logger.debug("Failed to reload LSP client", exc_info=True)
        return False
