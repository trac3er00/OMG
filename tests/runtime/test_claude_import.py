"""Tests for Claude.ai paste-based memory import."""

import pytest
from runtime.memory_parsers.claude_import import (
    EXTRACTION_PROMPT,
    parse_claude_paste,
    import_from_paste,
)
from runtime.memory_store import MemoryStore


class TestExtractionPrompt:
    """Test EXTRACTION_PROMPT constant."""

    def test_extraction_prompt_is_string(self):
        """EXTRACTION_PROMPT should be a non-empty string."""
        assert isinstance(EXTRACTION_PROMPT, str)
        assert len(EXTRACTION_PROMPT) > 0


class TestParseClaudePaste:
    """Test parse_claude_paste() function."""

    def test_parse_claude_paste_bullet_points(self):
        """Parse bullet points with '- ' prefix."""
        text = "- I prefer Python over JavaScript\n- My name is Alex\n- I work at Acme Corp"
        result = parse_claude_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "I prefer Python over JavaScript"
        assert result[1]["content"] == "My name is Alex"
        assert result[2]["content"] == "I work at Acme Corp"

    def test_parse_claude_paste_asterisk_bullets(self):
        """Parse bullet points with '* ' prefix."""
        text = "* First memory\n* Second memory\n* Third memory"
        result = parse_claude_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "First memory"
        assert result[1]["content"] == "Second memory"
        assert result[2]["content"] == "Third memory"

    def test_parse_claude_paste_numbered_list(self):
        """Parse numbered list format."""
        text = "1. First item\n2. Second item\n3. Third item"
        result = parse_claude_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "First item"
        assert result[1]["content"] == "Second item"
        assert result[2]["content"] == "Third item"

    def test_parse_claude_paste_plain_paragraphs(self):
        """Parse plain text, one per line."""
        text = "I prefer Python over JavaScript.\nMy name is Alex.\nI work at Acme Corp."
        result = parse_claude_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "I prefer Python over JavaScript."
        assert result[1]["content"] == "My name is Alex."
        assert result[2]["content"] == "I work at Acme Corp."

    def test_parse_claude_paste_empty_input(self):
        """Empty input returns empty list."""
        result = parse_claude_paste("")
        assert result == []

    def test_parse_claude_paste_whitespace_only(self):
        """Whitespace-only input returns empty list."""
        result = parse_claude_paste("   \n\n  \t  \n")
        assert result == []

    def test_parse_claude_paste_mixed_formats(self):
        """Handle mixed bullet styles in same input."""
        text = "- First item\n* Second item\n3. Third item\nFourth item"
        result = parse_claude_paste(text)
        assert len(result) == 4
        assert result[0]["content"] == "First item"
        assert result[1]["content"] == "Second item"
        assert result[2]["content"] == "Third item"
        assert result[3]["content"] == "Fourth item"

    def test_parse_claude_paste_strips_whitespace(self):
        """Leading and trailing whitespace stripped from items."""
        text = "-   Item with spaces   \n*  Another item  \n  Plain text  "
        result = parse_claude_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "Item with spaces"
        assert result[1]["content"] == "Another item"
        assert result[2]["content"] == "Plain text"

    def test_parse_claude_paste_returns_correct_structure(self):
        """Each item has correct dict structure."""
        text = "- Test memory"
        result = parse_claude_paste(text)
        assert len(result) == 1
        item = result[0]
        assert "key" in item
        assert "content" in item
        assert "source_cli" in item
        assert "tags" in item
        assert item["source_cli"] == "claude-web"
        assert "claude-web" in item["tags"]
        assert "imported" in item["tags"]

    def test_parse_claude_paste_sequential_keys(self):
        """Keys are sequential: claude-memory-1, claude-memory-2, etc."""
        text = "- First\n- Second\n- Third"
        result = parse_claude_paste(text)
        assert result[0]["key"] == "claude-memory-1"
        assert result[1]["key"] == "claude-memory-2"
        assert result[2]["key"] == "claude-memory-3"


class TestImportFromPaste:
    """Test import_from_paste() function."""

    def test_import_from_paste_returns_count(self):
        """import_from_paste returns count of items added."""
        text = "- Item 1\n- Item 2\n- Item 3"
        store = MemoryStore(store_path=":memory:")
        count = import_from_paste(text, store)
        assert count == 3

    def test_import_from_paste_adds_to_store(self, tmp_path):
        """Items are actually added to the store."""
        text = "- Memory 1\n- Memory 2"
        store_path = str(tmp_path / "store.json")
        store = MemoryStore(store_path=store_path)
        count = import_from_paste(text, store)
        assert count == 2
        assert store.count() == 2
        items = store.list_all()
        assert items[0]["content"] == "Memory 1"
        assert items[1]["content"] == "Memory 2"

    def test_import_from_paste_skips_empty_items(self):
        """Empty items are skipped."""
        text = "- Item 1\n\n- Item 2\n   \n- Item 3"
        store = MemoryStore(store_path=":memory:")
        count = import_from_paste(text, store)
        assert count == 3

    def test_import_from_paste_empty_input(self):
        """Empty input returns 0."""
        store = MemoryStore(store_path=":memory:")
        count = import_from_paste("", store)
        assert count == 0

    def test_import_from_paste_items_have_source_cli(self, tmp_path):
        """Imported items have source_cli set to 'claude-web'."""
        text = "- Test memory"
        store_path = str(tmp_path / "store.json")
        store = MemoryStore(store_path=store_path)
        import_from_paste(text, store)
        items = store.list_all()
        assert items[0]["source_cli"] == "claude-web"

    def test_import_from_paste_items_have_tags(self, tmp_path):
        """Imported items have correct tags."""
        text = "- Test memory"
        store_path = str(tmp_path / "store.json")
        store = MemoryStore(store_path=store_path)
        import_from_paste(text, store)
        items = store.list_all()
        assert "claude-web" in items[0]["tags"]
        assert "imported" in items[0]["tags"]
