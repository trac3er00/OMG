"""TDD tests for runtime.memory_store — MemoryStore CRUD + JSON persistence."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.memory_store import MemoryStore, MemoryStoreFullError


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_path(self) -> None:
        store = MemoryStore()
        expected = str(Path.home() / ".omg" / "shared-memory" / "store.json")
        assert store.store_path == expected

    def test_custom_path(self, tmp_path: Path) -> None:
        custom = str(tmp_path / "custom" / "data.json")
        store = MemoryStore(store_path=custom)
        assert store.store_path == custom

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "store.json"
        store = MemoryStore(store_path=str(deep))
        # Adding an item forces parent dir creation
        store.add(key="test", content="hello", source_cli="claude")
        assert deep.parent.exists()


# ---------------------------------------------------------------------------
# add tests
# ---------------------------------------------------------------------------


class TestAdd:
    def test_creates_item_with_correct_schema(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(
            key="project-context",
            content="This is the project context",
            source_cli="codex",
            tags=["context", "important"],
        )
        assert isinstance(item, dict)
        assert "id" in item
        assert item["key"] == "project-context"
        assert item["content"] == "This is the project context"
        assert item["source_cli"] == "codex"
        assert item["tags"] == ["context", "important"]
        assert "created_at" in item
        assert "updated_at" in item

    def test_id_is_uuid4(self, tmp_path: Path) -> None:
        import uuid

        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude")
        # Should not raise
        parsed = uuid.UUID(item["id"], version=4)
        assert str(parsed) == item["id"]

    def test_timestamps_are_iso8601(self, tmp_path: Path) -> None:
        from datetime import datetime, timezone

        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude")
        # Should parse without error
        created = datetime.fromisoformat(item["created_at"])
        updated = datetime.fromisoformat(item["updated_at"])
        assert created.tzinfo is not None or "Z" in item["created_at"] or "+" in item["created_at"]
        assert updated.tzinfo is not None or "Z" in item["updated_at"] or "+" in item["updated_at"]

    def test_default_tags_empty_list(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude")
        assert item["tags"] == []

    def test_raises_memory_store_full_error(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        # Mock internal count to simulate full store
        with patch.object(store, "count", return_value=10_000):
            with pytest.raises(MemoryStoreFullError):
                store.add(key="k", content="c", source_cli="claude")


# ---------------------------------------------------------------------------
# get tests
# ---------------------------------------------------------------------------


class TestGet:
    def test_returns_item_by_id(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude")
        fetched = store.get(item["id"])
        assert fetched is not None
        assert fetched["id"] == item["id"]
        assert fetched["key"] == "k"
        assert fetched["content"] == "c"

    def test_returns_none_for_missing_id(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        assert store.get("nonexistent-id") is None


# ---------------------------------------------------------------------------
# update tests
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_updates_content(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="old", source_cli="claude")
        updated = store.update(item["id"], content="new")
        assert updated is not None
        assert updated["content"] == "new"
        assert updated["key"] == "k"  # unchanged

    def test_updates_tags(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude", tags=["old"])
        updated = store.update(item["id"], tags=["new", "tags"])
        assert updated is not None
        assert updated["tags"] == ["new", "tags"]

    def test_updates_updated_at(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude")
        original_updated = item["updated_at"]
        time.sleep(0.01)  # ensure timestamp differs
        updated = store.update(item["id"], content="new")
        assert updated is not None
        assert updated["updated_at"] != original_updated

    def test_returns_none_for_missing_id(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        assert store.update("nonexistent", content="x") is None


# ---------------------------------------------------------------------------
# delete tests
# ---------------------------------------------------------------------------


class TestDelete:
    def test_returns_true_on_success(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        item = store.add(key="k", content="c", source_cli="claude")
        assert store.delete(item["id"]) is True
        assert store.get(item["id"]) is None

    def test_returns_false_for_missing_id(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        assert store.delete("nonexistent") is False


# ---------------------------------------------------------------------------
# search tests
# ---------------------------------------------------------------------------


class TestSearch:
    @pytest.fixture()
    def populated_store(self, tmp_path: Path) -> MemoryStore:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        store.add(key="project-context", content="Python web application", source_cli="codex", tags=["python", "web"])
        store.add(key="api-notes", content="REST API design patterns", source_cli="gemini", tags=["api", "design"])
        store.add(key="debug-log", content="Fixed authentication bug", source_cli="claude", tags=["bug", "auth"])
        return store

    def test_finds_by_content_keyword(self, populated_store: MemoryStore) -> None:
        results = populated_store.search("authentication")
        assert len(results) == 1
        assert results[0]["key"] == "debug-log"

    def test_finds_by_key_keyword(self, populated_store: MemoryStore) -> None:
        results = populated_store.search("api-notes")
        assert len(results) == 1
        assert results[0]["key"] == "api-notes"

    def test_finds_by_tag_keyword(self, populated_store: MemoryStore) -> None:
        results = populated_store.search("python")
        assert len(results) == 1
        assert results[0]["key"] == "project-context"

    def test_case_insensitive(self, populated_store: MemoryStore) -> None:
        results = populated_store.search("PYTHON")
        assert len(results) == 1
        assert results[0]["key"] == "project-context"

    def test_filters_by_source_cli(self, populated_store: MemoryStore) -> None:
        # "design" appears in gemini item
        results = populated_store.search("design", source_cli="gemini")
        assert len(results) == 1
        assert results[0]["source_cli"] == "gemini"

        # Same keyword but filtered to codex -> no match
        results = populated_store.search("design", source_cli="codex")
        assert len(results) == 0

    def test_returns_empty_for_no_match(self, populated_store: MemoryStore) -> None:
        results = populated_store.search("nonexistent-query-xyz")
        assert results == []


# ---------------------------------------------------------------------------
# list_all tests
# ---------------------------------------------------------------------------


class TestListAll:
    def test_returns_all_items(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        store.add(key="a", content="x", source_cli="codex")
        store.add(key="b", content="y", source_cli="gemini")
        items = store.list_all()
        assert len(items) == 2

    def test_filters_by_source_cli(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        store.add(key="a", content="x", source_cli="codex")
        store.add(key="b", content="y", source_cli="gemini")
        store.add(key="c", content="z", source_cli="codex")
        items = store.list_all(source_cli="codex")
        assert len(items) == 2
        assert all(i["source_cli"] == "codex" for i in items)


# ---------------------------------------------------------------------------
# export_all tests
# ---------------------------------------------------------------------------


class TestExportAll:
    def test_returns_all_items_as_list(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        store.add(key="a", content="x", source_cli="codex")
        store.add(key="b", content="y", source_cli="gemini")
        exported = store.export_all()
        assert isinstance(exported, list)
        assert len(exported) == 2


# ---------------------------------------------------------------------------
# import_items tests
# ---------------------------------------------------------------------------


class TestImportItems:
    def test_adds_items_returns_count(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        items_to_import = [
            {"id": "id-1", "key": "k1", "content": "c1", "source_cli": "codex", "tags": [], "created_at": "2025-01-01T00:00:00+00:00", "updated_at": "2025-01-01T00:00:00+00:00"},
            {"id": "id-2", "key": "k2", "content": "c2", "source_cli": "gemini", "tags": [], "created_at": "2025-01-01T00:00:00+00:00", "updated_at": "2025-01-01T00:00:00+00:00"},
        ]
        count = store.import_items(items_to_import)
        assert count == 2
        assert store.count() == 2

    def test_skips_items_with_existing_ids(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        existing = store.add(key="existing", content="c", source_cli="claude")
        items_to_import = [
            {"id": existing["id"], "key": "dup", "content": "dup", "source_cli": "codex", "tags": [], "created_at": "2025-01-01T00:00:00+00:00", "updated_at": "2025-01-01T00:00:00+00:00"},
            {"id": "new-id", "key": "new", "content": "new", "source_cli": "gemini", "tags": [], "created_at": "2025-01-01T00:00:00+00:00", "updated_at": "2025-01-01T00:00:00+00:00"},
        ]
        count = store.import_items(items_to_import)
        assert count == 1  # only new-id added
        assert store.count() == 2


# ---------------------------------------------------------------------------
# count tests
# ---------------------------------------------------------------------------


class TestCount:
    def test_returns_correct_count(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        assert store.count() == 0
        store.add(key="a", content="x", source_cli="codex")
        assert store.count() == 1
        store.add(key="b", content="y", source_cli="gemini")
        assert store.count() == 2


# ---------------------------------------------------------------------------
# clear tests
# ---------------------------------------------------------------------------


class TestClear:
    def test_deletes_all_returns_count(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        store.add(key="a", content="x", source_cli="codex")
        store.add(key="b", content="y", source_cli="gemini")
        store.add(key="c", content="z", source_cli="claude")
        deleted = store.clear()
        assert deleted == 3
        assert store.count() == 0


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_data_survives_across_instances(self, tmp_path: Path) -> None:
        path = str(tmp_path / "s.json")
        store1 = MemoryStore(store_path=path)
        item = store1.add(key="persist-key", content="persist-value", source_cli="codex", tags=["persist"])

        # Create a new instance pointing to same file
        store2 = MemoryStore(store_path=path)
        fetched = store2.get(item["id"])
        assert fetched is not None
        assert fetched["key"] == "persist-key"
        assert fetched["content"] == "persist-value"
        assert fetched["tags"] == ["persist"]

    def test_json_file_is_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        store = MemoryStore(store_path=str(path))
        store.add(key="k", content="c", source_cli="claude")

        # Read and parse the file directly
        raw = json.loads(path.read_text())
        assert isinstance(raw, list)
        assert len(raw) == 1
        assert raw[0]["key"] == "k"


# ---------------------------------------------------------------------------
# Atomic write tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_uses_tmp_file_and_replace(self, tmp_path: Path) -> None:
        path = str(tmp_path / "s.json")
        store = MemoryStore(store_path=path)

        with patch("runtime.memory_store.os.replace", wraps=os.replace) as mock_replace:
            store.add(key="k", content="c", source_cli="claude")
            mock_replace.assert_called_once()
            # First arg should be the .tmp file
            call_args = mock_replace.call_args[0]
            assert str(call_args[0]).endswith(".tmp")
            assert str(call_args[1]) == path
