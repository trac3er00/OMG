from __future__ import annotations

import json
import os
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

    FastMCP.__module__ = "fastmcp"

from runtime.memory_store import MemoryStore, MemoryStoreFullError

_store = MemoryStore()


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
    return JSONResponse({"status": "ok", "version": "2.0.8"})


@mcp.tool()
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


@mcp.tool()
def memory_search(
    query: str,
    source_cli: str | None = None,
    namespace: str | None = None,
) -> list[dict[str, Any]]:
    return _store.search(query=query, source_cli=source_cli, namespace=namespace)


@mcp.tool()
def memory_list(
    source_cli: str | None = None,
    namespace: str | None = None,
) -> list[dict[str, Any]]:
    return _store.list_all(source_cli=source_cli, namespace=namespace)


@mcp.tool()
def memory_delete(item_id: str) -> dict[str, Any]:
    deleted = _store.delete(item_id)
    return {"deleted": deleted, "id": item_id}


@mcp.tool()
def memory_import(items: list[dict[str, Any]]) -> dict[str, int]:
    count = _store.import_items(items)
    return {"imported": count}


@mcp.tool()
def memory_export() -> list[dict[str, Any]]:
    return _store.export_all()


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
