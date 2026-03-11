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


# -------------------------------------------------------------------
# MCP / MemoryStore failure-injection tests (blind-spot coverage)
# -------------------------------------------------------------------

from pathlib import Path
from unittest.mock import patch, MagicMock
from runtime.memory_store import MemoryStore, MemoryStoreFullError


class TestMemoryStoreCorruptedJsonFile:
    """MemoryStore JSON backend resilience against corrupted data on disk."""

    def test_corrupted_json_file_returns_empty_store(self, tmp_path: Path) -> None:
        store_path = str(tmp_path / "store.json")
        Path(store_path).write_text("{{{not valid json!!!", encoding="utf-8")
        store = MemoryStore(store_path=store_path)
        assert store.count() == 0

    def test_non_list_json_returns_empty_store(self, tmp_path: Path) -> None:
        store_path = str(tmp_path / "store.json")
        Path(store_path).write_text('{"key": "value"}', encoding="utf-8")
        store = MemoryStore(store_path=store_path)
        assert store.count() == 0

    def test_empty_file_returns_empty_store(self, tmp_path: Path) -> None:
        store_path = str(tmp_path / "store.json")
        Path(store_path).write_text("", encoding="utf-8")
        store = MemoryStore(store_path=store_path)
        assert store.count() == 0


class TestMemoryStoreDiskWriteFailure:
    """MemoryStore behavior when disk writes fail."""

    def test_add_raises_on_full_store(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store._items = [{"id": str(i)} for i in range(10_000)]
        with pytest.raises(MemoryStoreFullError, match="full"):
            store.add(key="overflow", content="data", source_cli="test")

    def test_save_to_readonly_dir_raises(self, tmp_path: Path) -> None:
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        store_path = str(readonly_dir / "deep" / "nested" / "store.json")
        store = MemoryStore(store_path=store_path)
        store._items.append({"id": "x", "key": "k"})
        import os
        readonly_dir.chmod(0o444)
        try:
            with pytest.raises(OSError):
                store._save_json_items()
        finally:
            readonly_dir.chmod(0o755)


class TestMemoryStoreSearchResilience:
    """MemoryStore search handles items with missing/malformed fields."""

    def test_search_with_missing_key_field(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store._items = [{"id": "1", "content": "hello world", "source_cli": "test", "tags": []}]
        results = store.search("hello")
        assert len(results) == 1

    def test_search_with_none_tags(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store._items = [{"id": "1", "key": "k", "content": "data", "source_cli": "test", "tags": None}]
        results = store.search("data")
        assert len(results) == 1

    def test_search_with_non_list_tags(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store._items = [{"id": "1", "key": "k", "content": "data", "source_cli": "test", "tags": "not-a-list"}]
        results = store.search("data")
        assert len(results) == 1

    def test_search_no_match_returns_empty(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store._items = [{"id": "1", "key": "k", "content": "data", "source_cli": "test", "tags": []}]
        results = store.search("nonexistent-query-xyzzy")
        assert results == []


class TestMemoryStoreImportEdgeCases:
    """MemoryStore import handles degenerate and duplicate items."""

    def test_import_skips_duplicate_ids(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store._items = [{"id": "existing", "key": "k1", "content": "c1"}]
        count = store.import_items([
            {"id": "existing", "key": "k2", "content": "c2"},
            {"id": "new-one", "key": "k3", "content": "c3"},
        ])
        assert count == 1
        assert store.count() == 2

    def test_import_skips_empty_id_items(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        count = store.import_items([
            {"id": "", "key": "k1", "content": "c1"},
            {"key": "k2", "content": "c2"},
        ])
        assert count == 0

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        assert store.delete("no-such-id") is False

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        assert store.get("no-such-id") is None

    def test_update_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        assert store.update("no-such-id", content="new") is None


@pytest.fixture()
def isolated_mcp_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _MCPMemoryServerModule:
    module = _load_module()
    monkeypatch.setenv("OMG_MEMORY_HOST", "memory.local")
    monkeypatch.setattr(module, "_store", MemoryStore(store_path=str(tmp_path / "isolated-store.json")))
    return module


class TestMemoryNamespaceRetentionAndPii:
    def test_namespace_isolation_for_list_and_search(self, isolated_mcp_module: _MCPMemoryServerModule) -> None:
        store_fn = getattr(isolated_mcp_module, "memory_store")
        list_fn = getattr(isolated_mcp_module, "memory_list")
        search_fn = getattr(isolated_mcp_module, "memory_search")

        _ = store_fn(key="k1", content="alpha content", source_cli="codex", namespace="team-a")
        _ = store_fn(key="k2", content="alpha content", source_cli="codex", namespace="team-b")

        team_a_items = list_fn(namespace="team-a")
        assert len(team_a_items) == 1
        assert team_a_items[0]["namespace"] == "memory.local:team-a"

        team_b_search = search_fn(query="alpha", namespace="team-b")
        assert len(team_b_search) == 1
        assert team_b_search[0]["namespace"] == "memory.local:team-b"

    def test_retention_metadata_roundtrips_export_import(
        self,
        isolated_mcp_module: _MCPMemoryServerModule,
        tmp_path: Path,
    ) -> None:
        store_fn = getattr(isolated_mcp_module, "memory_store")
        export_fn = getattr(isolated_mcp_module, "memory_export")

        stored = store_fn(
            key="retention-key",
            content="keep this",
            source_cli="codex",
            namespace="team-a",
            retention_days=14,
        )
        assert stored["retention_days"] == 14

        exported = export_fn()
        assert len(exported) == 1
        assert exported[0]["retention_days"] == 14
        assert exported[0]["namespace"] == "memory.local:team-a"

        mirror_store = MemoryStore(store_path=str(tmp_path / "mirror-store.json"))
        imported_count = mirror_store.import_items(exported)
        assert imported_count == 1

        mirror_items = mirror_store.export_all()
        assert len(mirror_items) == 1
        assert mirror_items[0]["retention_days"] == 14
        assert mirror_items[0]["namespace"] == "memory.local:team-a"

    def test_pii_redaction_happens_before_storage(self, isolated_mcp_module: _MCPMemoryServerModule) -> None:
        store_fn = getattr(isolated_mcp_module, "memory_store")
        list_fn = getattr(isolated_mcp_module, "memory_list")

        raw = "email a@b.com phone 415-555-1212 ssn 123-45-6789"
        result = store_fn(key="pii", content=raw, source_cli="codex", namespace="team-a")

        assert "a@b.com" not in result["content"]
        assert "415-555-1212" not in result["content"]
        assert "123-45-6789" not in result["content"]
        assert "[REDACTED:EMAIL]" in result["content"]
        assert "[REDACTED:PHONE]" in result["content"]
        assert "[REDACTED:SSN]" in result["content"]

        persisted = list_fn(namespace="team-a")
        assert len(persisted) == 1
        assert persisted[0]["content"] == result["content"]
