from __future__ import annotations

import importlib
import sys
from typing import Protocol, cast

import pytest


class _MCPMemoryServerModule(Protocol):
    mcp: object

    def get_host(self) -> str: ...

    def get_port(self) -> int: ...


def _load_module() -> _MCPMemoryServerModule:
    original_sys_path = list(sys.path)
    sys.path[:] = [path for path in sys.path if not path.endswith("/omg_natives")]

    try:
        _ = sys.modules.pop("html", None)
        _ = sys.modules.pop("runtime.mcp_memory_server", None)
        module = importlib.import_module("runtime.mcp_memory_server")
        return cast(_MCPMemoryServerModule, cast(object, module))
    finally:
        sys.path[:] = original_sys_path


def test_get_host_defaults_to_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.delenv("OMG_MEMORY_HOST", raising=False)

    assert module.get_host() == "127.0.0.1"


def test_get_host_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("OMG_MEMORY_HOST", "localhost")

    assert module.get_host() == "localhost"


def test_get_host_rejects_non_loopback_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("OMG_MEMORY_HOST", "0.0.0.0")
    monkeypatch.delenv("OMG_MEMORY_UNSAFE_BIND", raising=False)

    with pytest.raises(ValueError, match="loopback"):
        module.get_host()


def test_get_host_allows_non_loopback_with_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("OMG_MEMORY_HOST", "0.0.0.0")
    monkeypatch.setenv("OMG_MEMORY_UNSAFE_BIND", "true")

    assert module.get_host() == "0.0.0.0"


def test_get_port_defaults_to_8765(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.delenv("OMG_MEMORY_PORT", raising=False)

    assert module.get_port() == 8765


def test_get_port_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("OMG_MEMORY_PORT", "9876")

    assert module.get_port() == 9876


def test_mcp_is_fastmcp_instance() -> None:
    module = _load_module()
    mcp_cls = module.mcp.__class__

    assert mcp_cls.__name__ == "FastMCP"
    assert mcp_cls.__module__.startswith("fastmcp")


def test_default_binding_is_localhost_only(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.delenv("OMG_MEMORY_HOST", raising=False)

    assert module.get_host() != "0.0.0.0"
    assert module.get_host() == "127.0.0.1"


# -------------------------------------------------------------------
# T20 — MCP tool / resource integration tests
# -------------------------------------------------------------------

import json


@pytest.fixture()
def mcp_module(tmp_path: object) -> _MCPMemoryServerModule:
    module = _load_module()
    store = getattr(module, "_store")
    store.store_path = str(tmp_path / "store.json")  # type: ignore[operator]
    store._items.clear()
    return module


# -- memory_store tool -------------------------------------------------


def test_memory_store_tool_adds_item(mcp_module: _MCPMemoryServerModule) -> None:
    fn = getattr(mcp_module, "memory_store")
    result = fn(key="greeting", content="hello world", source_cli="codex")
    assert isinstance(result, dict)
    assert result["key"] == "greeting"
    assert result["content"] == "hello world"
    assert result["source_cli"] == "codex"
    assert "id" in result
    assert "created_at" in result


def test_memory_store_tool_returns_error_on_full(
    mcp_module: _MCPMemoryServerModule,
) -> None:
    fn = getattr(mcp_module, "memory_store")
    store = getattr(mcp_module, "_store")

    store._items = [{"id": str(i)} for i in range(10_000)]

    result = fn(key="k", content="c", source_cli="claude")
    assert isinstance(result, dict)
    assert "error" in result


# -- memory_search tool ------------------------------------------------


def test_memory_search_tool_returns_results(mcp_module: _MCPMemoryServerModule) -> None:
    store_fn = getattr(mcp_module, "memory_store")
    search_fn = getattr(mcp_module, "memory_search")

    store_fn(key="topic", content="python async patterns", source_cli="codex")
    results = search_fn(query="python")
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["content"] == "python async patterns"


def test_memory_search_tool_empty_results(mcp_module: _MCPMemoryServerModule) -> None:
    search_fn = getattr(mcp_module, "memory_search")

    results = search_fn(query="nonexistent-xyzzy")
    assert results == []


# -- memory_list tool --------------------------------------------------


def test_memory_list_tool_returns_all(mcp_module: _MCPMemoryServerModule) -> None:
    store_fn = getattr(mcp_module, "memory_store")
    list_fn = getattr(mcp_module, "memory_list")

    store_fn(key="a", content="aa", source_cli="codex")
    store_fn(key="b", content="bb", source_cli="gemini")

    items = list_fn()
    assert isinstance(items, list)
    assert len(items) == 2


def test_memory_list_tool_filters_by_source_cli(mcp_module: _MCPMemoryServerModule) -> None:
    store_fn = getattr(mcp_module, "memory_store")
    list_fn = getattr(mcp_module, "memory_list")

    store_fn(key="a", content="aa", source_cli="codex")
    store_fn(key="b", content="bb", source_cli="gemini")

    items = list_fn(source_cli="codex")
    assert len(items) == 1
    assert items[0]["source_cli"] == "codex"


# -- memory_delete tool ------------------------------------------------


def test_memory_delete_tool_returns_true(mcp_module: _MCPMemoryServerModule) -> None:
    store_fn = getattr(mcp_module, "memory_store")
    delete_fn = getattr(mcp_module, "memory_delete")

    item = store_fn(key="x", content="y", source_cli="codex")
    result = delete_fn(item_id=item["id"])
    assert result == {"deleted": True, "id": item["id"]}


def test_memory_delete_tool_returns_false_for_missing(
    mcp_module: _MCPMemoryServerModule,
) -> None:
    delete_fn = getattr(mcp_module, "memory_delete")

    result = delete_fn(item_id="nonexistent-id")
    assert result == {"deleted": False, "id": "nonexistent-id"}


# -- memory_import / memory_export tools --------------------------------


def test_memory_import_tool_returns_count(mcp_module: _MCPMemoryServerModule) -> None:
    import_fn = getattr(mcp_module, "memory_import")

    items = [
        {"id": "imp-1", "key": "k1", "content": "c1", "source_cli": "codex", "tags": []},
        {"id": "imp-2", "key": "k2", "content": "c2", "source_cli": "codex", "tags": []},
    ]
    result = import_fn(items=items)
    assert result == {"imported": 2}


def test_memory_export_tool_returns_all(mcp_module: _MCPMemoryServerModule) -> None:
    store_fn = getattr(mcp_module, "memory_store")
    export_fn = getattr(mcp_module, "memory_export")

    store_fn(key="e1", content="c1", source_cli="codex")
    store_fn(key="e2", content="c2", source_cli="gemini")

    exported = export_fn()
    assert isinstance(exported, list)
    assert len(exported) == 2


# -- memory://all resource ---------------------------------------------


def test_memory_all_resource_returns_json(mcp_module: _MCPMemoryServerModule) -> None:
    store_fn = getattr(mcp_module, "memory_store")
    resource_fn = getattr(mcp_module, "memory_all_resource")

    store_fn(key="r1", content="c1", source_cli="codex")

    raw = resource_fn()
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["key"] == "r1"
