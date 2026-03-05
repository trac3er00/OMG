"""Tests for migrate_markdown_memories — legacy migration utility."""
from __future__ import annotations

import pytest

from claude_experimental.memory.migrate import migrate_markdown_memories
from claude_experimental.memory.store import MemoryStore

pytestmark = pytest.mark.experimental


class TestMigration:
    def test_migrate_markdown_memories(self, tmp_path):
        """Markdown files are migrated to SQLite store."""
        memory_dir = tmp_path / ".omg" / "state" / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "2024-01-15-auth-fix.md").write_text(
            "Fixed auth bypass vulnerability"
        )
        (memory_dir / "2024-01-16-deploy.md").write_text(
            "Deployment procedure updated"
        )

        store = MemoryStore(db_path=str(tmp_path / "migration.db"))
        result = migrate_markdown_memories(str(tmp_path), target_store=store)

        assert result["files_found"] == 2
        assert result["memories_migrated"] == 2
        assert result["errors"] == 0
        assert result["skipped_duplicates"] == 0

    def test_migration_idempotency(self, tmp_path):
        """Running migration twice skips already-migrated files."""
        memory_dir = tmp_path / ".omg" / "state" / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "2024-03-01-note.md").write_text(
            "Important observation about caching"
        )

        store = MemoryStore(db_path=str(tmp_path / "migration.db"))

        r1 = migrate_markdown_memories(str(tmp_path), target_store=store)
        assert r1["memories_migrated"] == 1

        r2 = migrate_markdown_memories(str(tmp_path), target_store=store)
        assert r2["memories_migrated"] == 0
        assert r2["skipped_duplicates"] == 1

    def test_migration_no_directory(self, tmp_path):
        """Missing memory directory returns zero counts."""
        store = MemoryStore(db_path=str(tmp_path / "migration.db"))
        result = migrate_markdown_memories(str(tmp_path), target_store=store)

        assert result["files_found"] == 0
        assert result["memories_migrated"] == 0
        assert result["errors"] == 0
