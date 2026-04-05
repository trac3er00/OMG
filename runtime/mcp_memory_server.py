from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

_MCP_IMPORT_ERROR: ModuleNotFoundError | None = None

try:
    from fastmcp import FastMCP as FastMCPImpl
    from starlette.requests import Request as RequestImpl
    from starlette.responses import JSONResponse as JSONResponseImpl
except ModuleNotFoundError as exc:
    _MCP_IMPORT_ERROR = exc
    RequestImpl = Any

    class JSONResponseFallback(dict):
        def __init__(self, content: dict[str, Any]):
            super().__init__(content)

    def _passthrough_decorator(*_args: Any, **_kwargs: Any):
        def decorator(func: Any) -> Any:
            return func

        return decorator

    class FastMCPFallback:  # type: ignore[override]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._import_error = _MCP_IMPORT_ERROR

        custom_route = staticmethod(_passthrough_decorator)
        tool = staticmethod(_passthrough_decorator)
        resource = staticmethod(_passthrough_decorator)

        def run(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError(
                "fastmcp and starlette are required to run the OMG memory server"
            ) from self._import_error

    FastMCPFallback.__module__ = "fastmcp"
    FastMCPImpl = FastMCPFallback
    JSONResponseImpl = JSONResponseFallback

from runtime.memory_store import MemoryStore, MemoryStoreFullError

_store = MemoryStore(
    store_path=str(Path.home() / ".omg" / "shared-memory" / "store.json")
)


class _HybridExportBundle(list[dict[str, Any]]):
    def __init__(self, items: list[dict[str, Any]], bundle: dict[str, Any]) -> None:
        super().__init__(items)
        self._bundle = bundle

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return self._bundle[key]
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._bundle.get(key, default)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self._bundle
        return super().__contains__(item)


def _load_state() -> None:
    return None


def _save_state() -> None:
    return None


@asynccontextmanager
async def lifespan(_: object) -> AsyncIterator[None]:
    _load_state()
    try:
        yield
    finally:
        _save_state()


mcp = FastMCPImpl("OMG Memory Server", lifespan=lifespan)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Any) -> Any:
    return JSONResponseImpl({"status": "ok", "version": "2.0.8"})


@mcp.tool(
    description="Store a durable memory entry with source, tags, namespace, and optional retention window. Use after key decisions so later planning can recover context without re-reading full transcripts."
)
def memory_store(
    key: str,
    content: str,
    source_cli: str,
    tags: list[str] | None = None,
    namespace: str = "default",
    retention_days: int | None = None,
) -> dict[str, Any]:
    try:
        return _store.add(
            key=key,
            content=content,
            source_cli=source_cli,
            tags=tags,
            namespace=namespace,
            retention_days=retention_days,
        )
    except MemoryStoreFullError as exc:
        return {"error": str(exc)}
    except ValueError as exc:
        return {"error": str(exc)}


@mcp.tool(
    description="Search memory entries by query text, optionally filtered by source CLI or namespace. Use in planning to quickly retrieve prior fixes, decisions, and known constraints for the same domain."
)
def memory_search(
    query: str,
    source_cli: str | None = None,
    namespace: str | None = None,
) -> list[dict[str, Any]]:
    return _store.search(query=query, source_cli=source_cli, namespace=namespace)


@mcp.tool(
    description="List memory entries with optional source and namespace filters. Use for memory inventory, quality review, or selecting records to export, delete, or promote during maintenance workflows."
)
def memory_list(
    source_cli: str | None = None,
    namespace: str | None = None,
) -> list[dict[str, Any]]:
    return _store.list_all(source_cli=source_cli, namespace=namespace)


@mcp.tool(
    description="Delete a memory item by ID and report whether removal succeeded. Use to clean stale, incorrect, or sensitive entries that should no longer influence future planning and retrieval."
)
def memory_delete(item_id: str) -> dict[str, Any]:
    deleted = _store.delete(item_id)
    return {"deleted": deleted, "id": item_id}


@mcp.tool(
    description="Import trusted plain memory items in bulk without quarantine. Use for controlled migrations where entries are already validated and should become immediately searchable and usable."
)
def memory_import(items: list[dict[str, Any]]) -> dict[str, int]:
    count = _store.import_items(items, quarantined=False)
    return {"imported": count}


@mcp.tool(
    description="Import an encrypted omg.memory.export.v1 bundle with integrity verification, decrypt, and quarantine. Use when moving memory across environments and you need tamper checks before activation."
)
def memory_import_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if str(bundle.get("format", "")) != "omg.memory.export.v1":
        return {"imported": 0, "error": "bundle format is invalid"}
    payload = str(bundle.get("encrypted_payload", ""))
    integrity = bundle.get("integrity", {})
    expected_sha = ""
    if isinstance(integrity, dict):
        expected_sha = str(integrity.get("sha256", ""))
    if (
        not payload
        or hashlib.sha256(payload.encode("utf-8")).hexdigest() != expected_sha
    ):
        return {"imported": 0, "error": "bundle integrity check failed"}
    if not payload.startswith("enc:v1:"):
        return {"imported": 0, "error": "bundle payload must be encrypted"}
    decoded = _store._decrypt_text(payload, purpose="export-bundle")  # noqa: SLF001
    if not decoded:
        return {"imported": 0, "error": "bundle decryption failed"}
    try:
        raw_items = json.loads(decoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"imported": 0, "error": "bundle payload is not valid JSON"}
    if not isinstance(raw_items, list):
        return {"imported": 0, "error": "bundle payload must be a list"}
    count = _store.import_items(raw_items, quarantined=True)
    return {"imported": count, "quarantined": count}


@mcp.tool(
    description="Export namespace memory into an encrypted omg.memory.export.v1 bundle with SHA-256 integrity metadata. Use for backup, transfer, and auditable handoff between sessions or hosts."
)
def memory_export(
    namespace: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    items = _store.list_all(namespace=namespace)
    serialized = json.dumps(items, separators=(",", ":"), ensure_ascii=True)
    encrypted_payload = _store._encrypt_text(serialized, purpose="export-bundle")  # noqa: SLF001
    bundle = {
        "format": "omg.memory.export.v1",
        "encrypted_payload": encrypted_payload,
        "integrity": {
            "sha256": hashlib.sha256(encrypted_payload.encode("utf-8")).hexdigest(),
            "algorithm": "sha256",
        },
        "metadata": {
            "count": len(items),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "namespace": namespace,
        },
    }
    return _HybridExportBundle(items, bundle)


@mcp.tool(
    description="Migrate legacy memory records to current storage/security format, with dry-run support for safe previews. Use before upgrades to estimate impact and execute bounded conversion batches."
)
def memory_migrate(dry_run: bool = True, batch_size: int = 100) -> dict[str, Any]:
    return _store.migrate_all(batch_size=batch_size, dry_run=dry_run)


@mcp.tool(
    description="Promote a quarantined memory item into active searchable memory after manual review. Use after validating imported entries so only trusted records influence downstream planning."
)
def memory_promote(item_id: str) -> dict[str, Any]:
    promoted = _store.promote_item(item_id)
    return {"promoted": promoted, "id": item_id}


@mcp.resource("memory://all")
def memory_all_resource() -> str:
    return json.dumps(_store.list_all())


def get_host() -> str:
    return os.environ.get("OMG_MEMORY_HOST", "127.0.0.1")


def get_port() -> int:
    return int(os.environ.get("OMG_MEMORY_PORT", "8765"))


def run_server() -> None:
    mcp.run(transport="http", host=get_host(), port=get_port())


if __name__ == "__main__":
    run_server()
