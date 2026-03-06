from __future__ import annotations

import json
import os
import ipaddress
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

_MCP_IMPORT_ERROR: ModuleNotFoundError | None = None

try:
    from fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse
except ModuleNotFoundError as exc:
    _MCP_IMPORT_ERROR = exc
    Request = Any

    class JSONResponse(dict):
        def __init__(self, content: dict[str, Any]):
            super().__init__(content)

    def _passthrough_decorator(*_args: Any, **_kwargs: Any):
        def decorator(func: Any) -> Any:
            return func

        return decorator

    class FastMCP:  # type: ignore[override]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._import_error = _MCP_IMPORT_ERROR

        custom_route = staticmethod(_passthrough_decorator)
        tool = staticmethod(_passthrough_decorator)
        resource = staticmethod(_passthrough_decorator)

        def run(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("fastmcp and starlette are required to run the OMG memory server") from self._import_error

from runtime.memory_store import MemoryStore, MemoryStoreFullError


_store = MemoryStore()


def _is_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_host(host: str) -> str:
    normalized = host.strip()
    if normalized == "localhost":
        return normalized
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            return normalized
    except ValueError:
        pass
    if _is_truthy_env("OMG_MEMORY_UNSAFE_BIND"):
        return normalized
    raise ValueError(
        "Memory server must bind to a loopback host unless OMG_MEMORY_UNSAFE_BIND=true"
    )


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


mcp = FastMCP("OMG Memory Server", lifespan=lifespan)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "1.0.0"})


@mcp.tool()
def memory_store(
    key: str,
    content: str,
    source_cli: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    try:
        return _store.add(key=key, content=content, source_cli=source_cli, tags=tags)
    except MemoryStoreFullError as exc:
        return {"error": str(exc)}


@mcp.tool()
def memory_search(query: str, source_cli: str | None = None) -> list[dict[str, Any]]:
    return _store.search(query=query, source_cli=source_cli)


@mcp.tool()
def memory_list(source_cli: str | None = None) -> list[dict[str, Any]]:
    return _store.list_all(source_cli=source_cli)


@mcp.tool()
def memory_delete(item_id: str) -> dict[str, Any]:
    deleted = _store.delete(item_id)
    return {"deleted": deleted, "id": item_id}


@mcp.tool()
def memory_import(items: list[dict[str, Any]]) -> dict[str, int]:
    return {"imported": _store.import_items(items)}


@mcp.tool()
def memory_export() -> list[dict[str, Any]]:
    return _store.export_all()


@mcp.resource("memory://all")
def memory_all_resource() -> str:
    return json.dumps(_store.list_all())


def get_host() -> str:
    return _validate_host(os.environ.get("OMG_MEMORY_HOST", "127.0.0.1"))


def get_port() -> int:
    return int(os.environ.get("OMG_MEMORY_PORT", "8765"))


def run_server() -> None:
    mcp.run(transport="http", host=get_host(), port=get_port())


if __name__ == "__main__":
    run_server()
