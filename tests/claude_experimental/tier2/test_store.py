"""Tests for MemoryStore — SQLite-backed storage engine."""
from __future__ import annotations

import pytest

from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestMemoryStore:
    def test_wal_mode_enabled(self, tmp_path):
        """MemoryStore uses WAL journal mode."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        assert store.pragma("journal_mode").lower() == "wal"

    def test_schema_version_is_1(self, tmp_path):
        """Schema version defaults to 1."""
        store = MemoryStore(db_path=str(tmp_path / "test.db"))
        assert store.get_schema_version() == 1

    def test_save_and_search_round_trip(self, tmp_path):
        """Saved memory is retrievable via FTS5 search."""
        db = str(tmp_path / "test.db")
        store = MemoryStore(db_path=db)
        mid = store.save("auth bug was fixed", memory_type="episodic", importance=0.8)
        assert mid > 0

        results = store.search("auth", limit=5)
        assert len(results) >= 1
        assert any("auth" in str(r["content"]) for r in results)

    def test_fts5_multi_term_search(self, tmp_path):
        """FTS5 multi-term search uses implicit AND."""
        db = str(tmp_path / "test.db")
        store = MemoryStore(db_path=db)
        store.save("login authentication failure", memory_type="semantic", importance=0.7)
        store.save("database connection timeout", memory_type="semantic", importance=0.5)

        results = store.search("login authentication")
        assert len(results) >= 1
        assert all(
            "login" in str(r["content"]) and "authentication" in str(r["content"])
            for r in results
        )
        # Second item should not appear (doesn't match both terms)
        contents = [str(r["content"]) for r in results]
        assert not any("timeout" in c for c in contents)
