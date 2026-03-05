"""TDD tests for runtime.memory_parsers.gemini_import — Gemini Web paste-based memory import."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from runtime.memory_parsers.gemini_import import (
    EXTRACTION_PROMPT,
    import_from_paste,
    parse_gemini_paste,
)


class TestExtractionPrompt:
    """Test EXTRACTION_PROMPT constant."""

    def test_extraction_prompt_is_string(self) -> None:
        """EXTRACTION_PROMPT should be a non-empty string."""
        assert isinstance(EXTRACTION_PROMPT, str)
        assert len(EXTRACTION_PROMPT) > 0

    def test_extraction_prompt_contains_key_phrase(self) -> None:
        """EXTRACTION_PROMPT should ask for memories."""
        assert "remember" in EXTRACTION_PROMPT.lower() or "memory" in EXTRACTION_PROMPT.lower()


class TestParseGeminiPaste:
    """Test parse_gemini_paste function."""

    def test_parse_gemini_paste_bullet_points(self) -> None:
        """Should parse bullet point format."""
        text = "- User prefers dark mode\n- Likes Python\n- Works on AI projects"
        result = parse_gemini_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "User prefers dark mode"
        assert result[1]["content"] == "Likes Python"
        assert result[2]["content"] == "Works on AI projects"

    def test_parse_gemini_paste_numbered_list(self) -> None:
        """Should parse numbered list format."""
        text = "1. Prefers async/await\n2. Uses TypeScript\n3. Likes testing"
        result = parse_gemini_paste(text)
        assert len(result) == 3
        assert result[0]["content"] == "Prefers async/await"
        assert result[1]["content"] == "Uses TypeScript"
        assert result[2]["content"] == "Likes testing"

    def test_parse_gemini_paste_empty_input(self) -> None:
        """Should return empty list for empty input."""
        result = parse_gemini_paste("")
        assert result == []

    def test_parse_gemini_paste_whitespace_only(self) -> None:
        """Should return empty list for whitespace-only input."""
        result = parse_gemini_paste("   \n\n  \t  ")
        assert result == []

    def test_parse_gemini_paste_correct_source_cli(self) -> None:
        """Should set source_cli to 'gemini-web'."""
        text = "- Memory item"
        result = parse_gemini_paste(text)
        assert len(result) == 1
        assert result[0]["source_cli"] == "gemini-web"

    def test_parse_gemini_paste_correct_tags(self) -> None:
        """Should include 'gemini-web' and 'imported' in tags."""
        text = "- Memory item"
        result = parse_gemini_paste(text)
        assert len(result) == 1
        assert "gemini-web" in result[0]["tags"]
        assert "imported" in result[0]["tags"]

    def test_parse_gemini_paste_correct_key_format(self) -> None:
        """Should use 'gemini-memory-{i+1}' format for keys."""
        text = "- First\n- Second\n- Third"
        result = parse_gemini_paste(text)
        assert result[0]["key"] == "gemini-memory-1"
        assert result[1]["key"] == "gemini-memory-2"
        assert result[2]["key"] == "gemini-memory-3"

    def test_parse_gemini_paste_mixed_formats(self) -> None:
        """Should handle mixed bullet and numbered formats."""
        text = "- Bullet point\n1. Numbered item\n- Another bullet"
        result = parse_gemini_paste(text)
        # Should parse at least the bullet points
        assert len(result) >= 1

    def test_parse_gemini_paste_strips_whitespace(self) -> None:
        """Should strip leading/trailing whitespace from items."""
        text = "-   Item with spaces   \n-\tTabbed item\t"
        result = parse_gemini_paste(text)
        assert len(result) >= 1
        assert result[0]["content"] == "Item with spaces"


class TestImportFromPaste:
    """Test import_from_paste function."""

    def test_import_from_paste_returns_count(self) -> None:
        """Should return the number of items imported."""
        mock_store = MagicMock()
        mock_store.add.return_value = {"id": "test-id"}
        text = "- Item 1\n- Item 2\n- Item 3"
        result = import_from_paste(text, mock_store)
        assert result == 3

    def test_import_from_paste_adds_to_store(self) -> None:
        """Should call store.add for each parsed item."""
        mock_store = MagicMock()
        mock_store.add.return_value = {"id": "test-id"}
        text = "- Item 1\n- Item 2"
        import_from_paste(text, mock_store)
        assert mock_store.add.call_count == 2

    def test_import_from_paste_uses_correct_parameters(self) -> None:
        """Should call store.add with correct parameters."""
        mock_store = MagicMock()
        mock_store.add.return_value = {"id": "test-id"}
        text = "- Test memory"
        import_from_paste(text, mock_store)
        # Verify add was called with correct source_cli
        call_args = mock_store.add.call_args
        assert call_args is not None
        assert call_args.kwargs["source_cli"] == "gemini-web"
        assert "gemini-web" in call_args.kwargs["tags"]

    def test_import_from_paste_empty_text(self) -> None:
        """Should return 0 for empty text."""
        mock_store = MagicMock()
        result = import_from_paste("", mock_store)
        assert result == 0
        mock_store.add.assert_not_called()

    def test_import_from_paste_returns_zero_on_empty(self) -> None:
        """Should return 0 when no items parsed."""
        mock_store = MagicMock()
        result = import_from_paste("   \n\n  ", mock_store)
        assert result == 0
