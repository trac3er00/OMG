"""TDD tests for runtime.memory_store — MemoryStore CRUD + JSON persistence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import inspect
import runtime.memory_store as memory_store_module
import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from cryptography.fernet import Fernet

from runtime.memory_store import (
    MemoryStore,
    MemoryStoreFullError,
    project_preference_signals,
)


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_path(self) -> None:
        store = MemoryStore()
        expected = str(Path.home() / ".omg" / "shared-memory" / "store.sqlite3")
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
        assert (
            created.tzinfo is not None
            or "Z" in item["created_at"]
            or "+" in item["created_at"]
        )
        assert (
            updated.tzinfo is not None
            or "Z" in item["updated_at"]
            or "+" in item["updated_at"]
        )

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
        store.add(
            key="project-context",
            content="Python web application",
            source_cli="codex",
            tags=["python", "web"],
        )
        store.add(
            key="api-notes",
            content="REST API design patterns",
            source_cli="gemini",
            tags=["api", "design"],
        )
        store.add(
            key="debug-log",
            content="Fixed authentication bug",
            source_cli="claude",
            tags=["bug", "auth"],
        )
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
            {
                "id": "id-1",
                "key": "k1",
                "content": "c1",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "id-2",
                "key": "k2",
                "content": "c2",
                "source_cli": "gemini",
                "tags": [],
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
        ]
        count = store.import_items(items_to_import)
        assert count == 2
        assert store.count() == 2

    def test_skips_items_with_existing_ids(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "s.json"))
        existing = store.add(key="existing", content="c", source_cli="claude")
        items_to_import = [
            {
                "id": existing["id"],
                "key": "dup",
                "content": "dup",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "new-id",
                "key": "new",
                "content": "new",
                "source_cli": "gemini",
                "tags": [],
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
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
        item = store1.add(
            key="persist-key",
            content="persist-value",
            source_cli="codex",
            tags=["persist"],
        )

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


class TestProjectPreferenceSignals:
    def test_returns_only_project_scoped_signals_and_bounds_results(
        self, tmp_path: Path
    ) -> None:
        store_path = tmp_path / "shared" / "store.json"
        store = MemoryStore(store_path=str(store_path))
        project_a = str(tmp_path / "project-a")
        project_b = str(tmp_path / "project-b")

        for idx in range(20):
            payload = {
                "field": "preferences.architecture_requests",
                "value": f"arch-{idx}",
                "source": "inferred_observation",
                "confidence": 0.9,
                "project_scope": project_a,
                "run_id": f"run-{idx}",
            }
            store.add(
                key="pref-signal",
                content=json.dumps(payload),
                source_cli="claude",
                tags=[f"project_scope:{project_a}"],
            )

        store.add(
            key="pref-signal",
            content=json.dumps(
                {
                    "field": "preferences.architecture_requests",
                    "value": "wrong-project",
                    "source": "explicit_user",
                    "confidence": 1.0,
                    "project_scope": project_b,
                    "run_id": "run-other",
                }
            ),
            source_cli="claude",
            tags=[f"project_scope:{project_b}"],
        )

        signals = project_preference_signals(
            project_a, store_path=str(store_path), max_signals=50
        )

        assert len(signals) == 12
        assert all(
            signal["project_scope"] == os.path.realpath(project_a) for signal in signals
        )
        assert all(signal["value"] != "wrong-project" for signal in signals)

    def test_ignores_non_whitelisted_and_non_json_payloads(
        self, tmp_path: Path
    ) -> None:
        store_path = tmp_path / "shared" / "store.json"
        store = MemoryStore(store_path=str(store_path))
        project_dir = str(tmp_path / "project")

        store.add(
            key="pref-signal",
            content="not-json",
            source_cli="claude",
            tags=[f"project_scope:{project_dir}"],
        )
        store.add(
            key="pref-signal",
            content=json.dumps(
                {
                    "field": "preferences.random_blob",
                    "value": "should-not-pass",
                    "source": "explicit_user",
                    "confidence": 1.0,
                    "project_scope": project_dir,
                }
            ),
            source_cli="claude",
            tags=[f"project_scope:{project_dir}"],
        )
        store.add(
            key="pref-signal",
            content=json.dumps(
                {
                    "field": "preferences.constraints.api_cost",
                    "value": "  minimize   spend  ",
                    "source": "explicit_user",
                    "confidence": 2.0,
                    "project_scope": project_dir,
                }
            ),
            source_cli="claude",
            tags=[f"project_scope:{project_dir}"],
        )

        signals = project_preference_signals(
            project_dir, store_path=str(store_path), max_signals=10
        )

        assert len(signals) == 1
        assert signals[0]["field"] == "preferences.constraints.api_cost"
        assert signals[0]["value"] == "minimize spend"
        assert signals[0]["confidence"] == 1.0


class TestSQLiteScopedStorage:
    def test_scoped_query_filters_run_id_and_profile_id(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "memory.sqlite3"))
        store.add(
            key="design",
            content="use adapter boundary",
            source_cli="codex",
            tags=["architecture"],
            run_id="run-a",
            profile_id="profile-a",
        )
        store.add(
            key="design",
            content="use strict governance",
            source_cli="codex",
            tags=["security"],
            run_id="run-b",
            profile_id="profile-a",
        )

        rows = store.query_scoped(
            query="design", run_id="run-a", profile_id="profile-a"
        )

        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-a"
        assert rows[0]["profile_id"] == "profile-a"

    def test_hybrid_retrieve_is_scoped_and_ranked(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "memory.sqlite3"))
        store.add(
            key="storage",
            content="sqlite fts retrieval for lineage",
            source_cli="claude",
            tags=["sqlite", "fts"],
            run_id="run-hybrid",
            profile_id="profile-main",
        )
        store.add(
            key="storage",
            content="irrelevant other run",
            source_cli="claude",
            tags=["other"],
            run_id="run-other",
            profile_id="profile-main",
        )

        rows = store.hybrid_retrieve(
            "sqlite retrieval", run_id="run-hybrid", profile_id="profile-main"
        )

        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-hybrid"
        assert rows[0]["score"] > 0

    def test_artifact_queries_return_handles_not_payloads(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "memory.sqlite3"))
        handle = store.index_artifact(
            run_id="run-a",
            profile_id="profile-z",
            kind="trace_zip",
            path=".omg/artifacts/run-a/trace.zip",
            summary="playwright trace archive",
            size_bytes=2048,
            metadata={"payload": "x" * 4000, "suite": "browser"},
        )

        rows = store.query_artifacts(run_id="run-a", profile_id="profile-z")

        assert len(rows) == 1
        assert rows[0]["artifact_id"] == handle["artifact_id"]
        assert rows[0]["path"] == ".omg/artifacts/run-a/trace.zip"
        assert rows[0]["summary"] == "playwright trace archive"
        assert "payload" not in rows[0]
        assert rows[0]["metadata"]["suite"] == "browser"
        assert rows[0]["metadata"]["omitted_payload"] is True


class TestEncryptionHardening:
    def test_xor_path_unreachable(self) -> None:
        assert not hasattr(MemoryStore, "_xor_cipher")
        source = inspect.getsource(memory_store_module)
        assert "OMG_MEMORY_ENCRYPTION_DISABLED" not in source
        assert "XOR-based encryption fallback" not in source

    def test_fernet_only_encryption(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "memory.sqlite3"))
        item = store.add(key="fernet", content="secret payload", source_cli="claude")

        raw = (
            store._sqlite_conn()
            .execute("SELECT content FROM memories WHERE id = ?", (item["id"],))
            .fetchone()
        )
        assert raw is not None
        encrypted_text = str(raw["content"])
        assert encrypted_text.startswith("enc:v1:")

        payload = encrypted_text[len("enc:v1:") :]
        key_bytes = store._derive_key_bytes(purpose="sqlite-content")
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        decrypted = Fernet(fernet_key).decrypt(payload.encode("utf-8")).decode("utf-8")
        assert decrypted == "secret payload"

    def test_xor_to_fernet_migration(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "memory.sqlite3"))
        item = store.add(key="legacy", content="needs migration", source_cli="claude")

        key_bytes = store._derive_key_bytes(purpose="sqlite-content")
        plaintext = "needs migration".encode("utf-8")
        legacy_cipher = bytes(
            byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(plaintext)
        )
        legacy_payload = base64.urlsafe_b64encode(legacy_cipher).decode("ascii")
        legacy_encrypted = f"enc:v1:{legacy_payload}"
        store._sqlite_conn().execute(
            "UPDATE memories SET content = ? WHERE id = ?",
            (legacy_encrypted, item["id"]),
        )
        store._sqlite_conn().commit()

        fetched = store.get(item["id"])
        assert fetched is not None
        assert fetched["content"] == "needs migration"

        row = (
            store._sqlite_conn()
            .execute("SELECT content FROM memories WHERE id = ?", (item["id"],))
            .fetchone()
        )
        assert row is not None
        migrated_encrypted = str(row["content"])
        assert migrated_encrypted.startswith("enc:v1:")
        assert migrated_encrypted != legacy_encrypted

        migrated_payload = migrated_encrypted[len("enc:v1:") :]
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        assert (
            Fernet(fernet_key).decrypt(migrated_payload.encode("utf-8")).decode("utf-8")
            == "needs migration"
        )

    def test_migration_empty_database(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "empty.sqlite3"))
        report = store.migrate_all()
        assert report["total"] == 0
        assert report["migrated"] == 0
        assert report["already_fernet"] == 0
        assert report["corrupted"] == 0
        assert report["errors"] == []

    def test_migration_already_fernet_skipped(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "fernet.sqlite3"))
        store.add(key="a", content="already fernet", source_cli="claude")
        store.add(key="b", content="also fernet", source_cli="codex")

        report = store.migrate_all()
        assert report["total"] == 2
        assert report["already_fernet"] == 2
        assert report["migrated"] == 0
        assert report["corrupted"] == 0

    def test_migration_corrupted_entry_skipped(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "corrupt.sqlite3"))
        item = store.add(key="bad", content="will corrupt", source_cli="claude")

        garbage = base64.urlsafe_b64encode(b"\xff\xfe\xfd\x00\x01").decode("ascii")
        store._sqlite_conn().execute(
            "UPDATE memories SET content = ? WHERE id = ?",
            (f"enc:v1:{garbage}", item["id"]),
        )
        store._sqlite_conn().commit()

        report = store.migrate_all()
        assert report["total"] == 1
        assert report["corrupted"] == 1
        assert report["migrated"] == 0
        assert len(report["errors"]) == 1
        assert item["id"] in report["errors"][0]

    def test_migration_batch_commit(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "batch.sqlite3"))
        key_bytes = store._derive_key_bytes(purpose="sqlite-content")
        ids = []
        for i in range(5):
            item = store.add(key=f"k{i}", content=f"val{i}", source_cli="claude")
            plaintext = f"val{i}".encode("utf-8")
            legacy_cipher = bytes(
                byte ^ key_bytes[idx % len(key_bytes)]
                for idx, byte in enumerate(plaintext)
            )
            legacy_payload = base64.urlsafe_b64encode(legacy_cipher).decode("ascii")
            store._sqlite_conn().execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                (f"enc:v1:{legacy_payload}", item["id"]),
            )
            ids.append(item["id"])
        store._sqlite_conn().commit()

        report = store.migrate_all(batch_size=2)
        assert report["total"] == 5
        assert report["migrated"] == 5
        assert report["corrupted"] == 0

        for item_id in ids:
            fetched = store.get(item_id)
            assert fetched is not None
            assert fetched["content"].startswith("val")

    def test_migration_mixed_entries(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "mixed.sqlite3"))
        key_bytes = store._derive_key_bytes(purpose="sqlite-content")

        fernet_item = store.add(
            key="fernet", content="already secure", source_cli="claude"
        )

        xor_item = store.add(key="xor", content="needs migration", source_cli="claude")
        plaintext = "needs migration".encode("utf-8")
        legacy_cipher = bytes(
            byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(plaintext)
        )
        legacy_payload = base64.urlsafe_b64encode(legacy_cipher).decode("ascii")
        store._sqlite_conn().execute(
            "UPDATE memories SET content = ? WHERE id = ?",
            (f"enc:v1:{legacy_payload}", xor_item["id"]),
        )

        corrupt_item = store.add(
            key="corrupt", content="will corrupt", source_cli="claude"
        )
        garbage = base64.urlsafe_b64encode(b"\xff\xfe\xfd").decode("ascii")
        store._sqlite_conn().execute(
            "UPDATE memories SET content = ? WHERE id = ?",
            (f"enc:v1:{garbage}", corrupt_item["id"]),
        )
        store._sqlite_conn().commit()

        report = store.migrate_all()
        assert report["total"] == 3
        assert report["already_fernet"] == 1
        assert report["migrated"] == 1
        assert report["corrupted"] == 1

        fernet_fetched = store.get(fernet_item["id"])
        assert fernet_fetched is not None
        assert fernet_fetched["content"] == "already secure"
        xor_fetched = store.get(xor_item["id"])
        assert xor_fetched is not None
        assert xor_fetched["content"] == "needs migration"

    def test_migration_dry_run_no_changes(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "dryrun.sqlite3"))
        key_bytes = store._derive_key_bytes(purpose="sqlite-content")
        item = store.add(key="xor", content="original", source_cli="claude")

        plaintext = "original".encode("utf-8")
        legacy_cipher = bytes(
            byte ^ key_bytes[idx % len(key_bytes)] for idx, byte in enumerate(plaintext)
        )
        legacy_payload = base64.urlsafe_b64encode(legacy_cipher).decode("ascii")
        legacy_encrypted = f"enc:v1:{legacy_payload}"
        store._sqlite_conn().execute(
            "UPDATE memories SET content = ? WHERE id = ?",
            (legacy_encrypted, item["id"]),
        )
        store._sqlite_conn().commit()

        report = store.migrate_all(dry_run=True)
        assert report["dry_run"] is True
        assert report["migrated"] == 1

        row = (
            store._sqlite_conn()
            .execute("SELECT content FROM memories WHERE id = ?", (item["id"],))
            .fetchone()
        )
        assert str(row["content"]) == legacy_encrypted

    def test_migration_json_backend_noop(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "store.json"))
        store.add(key="a", content="hello", source_cli="claude")
        report = store.migrate_all()
        assert report["total"] == 1
        assert report["already_fernet"] == 1
        assert report["migrated"] == 0

    def test_migration_data_readable_after(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "readable.sqlite3"))
        key_bytes = store._derive_key_bytes(purpose="sqlite-content")
        test_values = ["hello world", "日本語テスト", "special chars: <>&\"'"]
        ids = []
        for val in test_values:
            item = store.add(key="test", content=val, source_cli="claude")
            plaintext = val.encode("utf-8")
            legacy_cipher = bytes(
                byte ^ key_bytes[idx % len(key_bytes)]
                for idx, byte in enumerate(plaintext)
            )
            legacy_payload = base64.urlsafe_b64encode(legacy_cipher).decode("ascii")
            store._sqlite_conn().execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                (f"enc:v1:{legacy_payload}", item["id"]),
            )
            ids.append(item["id"])
        store._sqlite_conn().commit()

        store.migrate_all()

        for item_id, expected in zip(ids, test_values):
            fetched = store.get(item_id)
            assert fetched is not None
            assert fetched["content"] == expected

    def test_migration_cli_entrypoint(self, tmp_path: Path) -> None:
        store = MemoryStore(store_path=str(tmp_path / "cli.sqlite3"))
        store.add(key="cli-test", content="via cli", source_cli="claude")
        store.close()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "runtime.memory_migrate",
                "--store-path",
                str(tmp_path / "cli.sqlite3"),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        report = json.loads(result.stdout)
        assert report["total"] == 1
        assert report["already_fernet"] == 1

    def test_importerror_on_missing_cryptography(self) -> None:
        module_path = (
            Path(__file__).resolve().parents[2] / "runtime" / "memory_store.py"
        )
        script = "\n".join(
            [
                "import builtins",
                "import runpy",
                "_orig_import = builtins.__import__",
                "def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):",
                "    if name.startswith('cryptography'):",
                "        raise ModuleNotFoundError(\"No module named 'cryptography'\")",
                "    return _orig_import(name, globals, locals, fromlist, level)",
                "builtins.__import__ = _blocked_import",
                f"runpy.run_path({str(module_path)!r})",
            ]
        )
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True
        )
        assert proc.returncode != 0
        assert "ModuleNotFoundError" in proc.stderr
        assert "cryptography" in proc.stderr


def test_cmms_tier_enum() -> None:
    MemoryTier = __import__("runtime.memory_schema", fromlist=["MemoryTier"]).MemoryTier

    assert MemoryTier.AUTO == "auto"
    assert MemoryTier.MICRO == "micro"
    assert MemoryTier.SHIP == "ship"


def test_cmms_micro_default(tmp_path: Path) -> None:
    store = MemoryStore(str(tmp_path / "mem.db"))

    store.set("test-key", {"value": "test"})

    result = store.get("test-key")
    assert result is not None


def test_cmms_auto_tier(tmp_path: Path) -> None:
    MemoryTier = __import__("runtime.memory_schema", fromlist=["MemoryTier"]).MemoryTier

    store = MemoryStore(str(tmp_path / "mem.db"))

    store.set("hot-data", {"value": "fast"}, tier=MemoryTier.AUTO)

    result = store.get("hot-data")
    assert result is not None


def test_cmms_ship_persistence(tmp_path: Path) -> None:
    MemoryTier = __import__("runtime.memory_schema", fromlist=["MemoryTier"]).MemoryTier

    store = MemoryStore(str(tmp_path / "mem.db"))
    store.set("project-knowledge", {"value": "important"}, tier=MemoryTier.SHIP)

    del store
    store2 = MemoryStore(str(tmp_path / "mem.db"))

    result = store2.get("project-knowledge")
    assert result is not None


def test_cmms_auto_promotion(tmp_path: Path) -> None:
    MemoryTier = __import__("runtime.memory_schema", fromlist=["MemoryTier"]).MemoryTier

    store = MemoryStore(str(tmp_path / "mem.db"))
    store.set("hot-data", {"value": "test"}, tier=MemoryTier.MICRO)

    for _ in range(4):
        store.get("hot-data")

    tier = store._get_tier("hot-data")
    assert tier == MemoryTier.AUTO


def test_cmms_backward_compat(tmp_path: Path) -> None:
    store = MemoryStore(str(tmp_path / "mem.db"))

    store.set("existing-key", {"value": "existing"})

    result = store.get("existing-key")
    assert result is not None
