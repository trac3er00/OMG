"""Tests for memory export to markdown format."""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from runtime.memory_parsers.export import (
    export_to_markdown,
    export_to_file,
    export_from_store,
)
from runtime.memory_store import MemoryStore


class TestExportToMarkdown:
    """Test export_to_markdown() function."""

    def test_export_to_markdown_empty_items(self):
        """Returns markdown with header and 'Total items: 0' for empty list."""
        result = export_to_markdown([])
        assert isinstance(result, str)
        assert "# OMG Shared Memory Export" in result
        assert "Total items: 0" in result
        assert "Generated:" in result

    def test_export_to_markdown_single_item(self):
        """Correct format for one item."""
        items = [
            {
                "id": "test-id-1",
                "key": "project-context",
                "content": "This is the memory content here.",
                "source_cli": "codex",
                "tags": ["codex", "project"],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        result = export_to_markdown(items)
        assert "## Memory 1: project-context" in result
        assert "This is the memory content here." in result
        assert "Total items: 1" in result

    def test_export_to_markdown_multiple_items(self):
        """Correct count and all items present."""
        items = [
            {
                "id": "id-1",
                "key": "memory-1",
                "content": "Content 1",
                "source_cli": "codex",
                "tags": ["tag1"],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            },
            {
                "id": "id-2",
                "key": "memory-2",
                "content": "Content 2",
                "source_cli": "gemini",
                "tags": ["tag2"],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            },
            {
                "id": "id-3",
                "key": "memory-3",
                "content": "Content 3",
                "source_cli": "claude",
                "tags": ["tag3"],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            },
        ]
        result = export_to_markdown(items)
        assert "Total items: 3" in result
        assert "## Memory 1: memory-1" in result
        assert "## Memory 2: memory-2" in result
        assert "## Memory 3: memory-3" in result
        assert "Content 1" in result
        assert "Content 2" in result
        assert "Content 3" in result

    def test_export_to_markdown_includes_source_cli(self):
        """source_cli is included in output."""
        items = [
            {
                "id": "id-1",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        result = export_to_markdown(items)
        assert "**Source**: codex" in result

    def test_export_to_markdown_includes_tags(self):
        """tags are included in output."""
        items = [
            {
                "id": "id-1",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "codex",
                "tags": ["tag1", "tag2", "tag3"],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        result = export_to_markdown(items)
        assert "**Tags**: tag1, tag2, tag3" in result

    def test_export_to_markdown_includes_timestamps(self):
        """created_at and updated_at are included in output."""
        items = [
            {
                "id": "id-1",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        result = export_to_markdown(items)
        assert "**Created**: 2026-03-04T10:00:00+00:00" in result
        assert "**Updated**: 2026-03-04T11:00:00+00:00" in result

    def test_export_to_markdown_has_generated_timestamp(self):
        """Output includes a Generated timestamp."""
        items = []
        result = export_to_markdown(items)
        assert "Generated:" in result
        # Should have ISO format timestamp
        assert "T" in result  # ISO format includes T

    def test_export_to_markdown_has_separator_lines(self):
        """Output includes separator lines between items."""
        items = [
            {
                "id": "id-1",
                "key": "memory-1",
                "content": "Content 1",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            },
            {
                "id": "id-2",
                "key": "memory-2",
                "content": "Content 2",
                "source_cli": "gemini",
                "tags": [],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            },
        ]
        result = export_to_markdown(items)
        # Should have separator lines (---)
        assert "---" in result


class TestExportToFile:
    """Test export_to_file() function."""

    def test_export_to_file_creates_file(self, tmp_path):
        """File exists after call."""
        items = [
            {
                "id": "id-1",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        output_path = tmp_path / "export.md"
        export_to_file(items, str(output_path))
        assert output_path.exists()
        assert output_path.is_file()

    def test_export_to_file_creates_parent_dirs(self, tmp_path):
        """Parent directories are created if missing."""
        items = [
            {
                "id": "id-1",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "codex",
                "tags": [],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        output_path = tmp_path / "nested" / "deep" / "export.md"
        export_to_file(items, str(output_path))
        assert output_path.exists()
        assert output_path.parent.exists()

    def test_export_to_file_content_matches_markdown(self, tmp_path):
        """File content matches export_to_markdown output."""
        items = [
            {
                "id": "id-1",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "codex",
                "tags": ["tag1"],
                "created_at": "2026-03-04T10:00:00+00:00",
                "updated_at": "2026-03-04T11:00:00+00:00",
            }
        ]
        output_path = tmp_path / "export.md"
        export_to_file(items, str(output_path))
        
        file_content = output_path.read_text()
        # Verify file has expected content (not comparing exact timestamp)
        assert "# OMG Shared Memory Export" in file_content
        assert "Test content" in file_content
        assert "**Source**: codex" in file_content
        assert "**Tags**: tag1" in file_content


class TestExportFromStore:
    """Test export_from_store() function."""

    def test_export_from_store_returns_markdown(self, tmp_path):
        """Returns markdown string."""
        store_path = tmp_path / "store.json"
        store = MemoryStore(str(store_path))
        store.add("key1", "content1", "codex", ["tag1"])
        
        result = export_from_store(store)
        assert isinstance(result, str)
        assert "# OMG Shared Memory Export" in result
        assert "Total items: 1" in result

    def test_export_from_store_writes_file_when_path_given(self, tmp_path):
        """File is written when output_path is provided."""
        store_path = tmp_path / "store.json"
        store = MemoryStore(str(store_path))
        store.add("key1", "content1", "codex", ["tag1"])
        
        output_path = tmp_path / "export.md"
        result = export_from_store(store, str(output_path))
        
        assert output_path.exists()
        assert isinstance(result, str)
        assert "# OMG Shared Memory Export" in result

    def test_export_from_store_no_file_when_no_path(self, tmp_path):
        """No file is created when output_path is None."""
        store_path = tmp_path / "store.json"
        store = MemoryStore(str(store_path))
        store.add("key1", "content1", "codex", ["tag1"])
        
        export_dir = tmp_path / "exports"
        export_dir.mkdir()
        
        result = export_from_store(store, None)
        
        assert isinstance(result, str)
        assert "# OMG Shared Memory Export" in result
        # No files should be created in export_dir
        assert len(list(export_dir.iterdir())) == 0

    def test_export_from_store_returns_markdown_both_cases(self, tmp_path):
        """Returns markdown string in both cases (with and without path)."""
        store_path = tmp_path / "store.json"
        store = MemoryStore(str(store_path))
        store.add("key1", "content1", "codex", ["tag1"])
        
        # With path
        output_path = tmp_path / "export.md"
        result_with_path = export_from_store(store, str(output_path))
        
        # Without path
        result_without_path = export_from_store(store, None)
        
        assert isinstance(result_with_path, str)
        assert isinstance(result_without_path, str)
        # Both should have the same structure (timestamps differ slightly due to timing)
        assert "# OMG Shared Memory Export" in result_with_path
        assert "# OMG Shared Memory Export" in result_without_path
        assert "content1" in result_with_path
        assert "content1" in result_without_path

    def test_export_from_store_empty_store(self, tmp_path):
        """Handles empty store correctly."""
        store_path = tmp_path / "store.json"
        store = MemoryStore(str(store_path))
        
        result = export_from_store(store)
        assert "Total items: 0" in result
        assert "# OMG Shared Memory Export" in result
