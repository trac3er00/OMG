"""Tests for runtime.memory_parsers.chatgpt_parser — ChatGPT conversations.json parser."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from runtime.memory_parsers.chatgpt_parser import (
    conversations_to_memory_items,
    extract_linear_conversation,
    parse_conversations_file,
)


# ---------------------------------------------------------------------------
# Helpers — build ChatGPT conversation fixtures
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    role: str,
    text: str,
    parent: str | None,
    children: list[str],
    create_time: float | None = 1700000000.0,
) -> dict[str, Any]:
    """Build a single mapping node in ChatGPT export format."""
    message = None
    if role and text is not None:
        parts = [text] if text != "" else [""]
        message = {
            "id": node_id,
            "author": {"role": role},
            "content": {"content_type": "text", "parts": parts},
            "create_time": create_time,
        }
    return {
        "id": node_id,
        "message": message,
        "parent": parent,
        "children": children,
    }


def _make_conversation(
    conv_id: str = "conv-1",
    title: str = "Test Conversation",
    mapping: dict[str, Any] | None = None,
    current_node: str = "node-3",
    create_time: float = 1700000000.0,
    update_time: float = 1700001000.0,
) -> dict[str, Any]:
    """Build a full conversation dict."""
    if mapping is None:
        mapping = {
            "node-1": _make_node("node-1", "system", "", None, ["node-2"]),
            "node-2": _make_node(
                "node-2", "user", "Hello", "node-1", ["node-3"], 1700000001.0
            ),
            "node-3": _make_node(
                "node-3",
                "assistant",
                "Hi there!",
                "node-2",
                [],
                1700000002.0,
            ),
        }
    return {
        "id": conv_id,
        "title": title,
        "create_time": create_time,
        "update_time": update_time,
        "mapping": mapping,
        "current_node": current_node,
    }


# ===========================================================================
# extract_linear_conversation
# ===========================================================================


class TestExtractLinearConversation:
    """Tests for extract_linear_conversation()."""

    def test_simple_three_node_chain(self) -> None:
        """3-node chain (system->user->assistant) returns user+assistant in order."""
        mapping = {
            "n1": _make_node("n1", "system", "", None, ["n2"]),
            "n2": _make_node("n2", "user", "Hello, what is Python?", "n1", ["n3"], 1700000001.0),
            "n3": _make_node(
                "n3", "assistant", "Python is a programming language...", "n2", [], 1700000002.0
            ),
        }
        result = extract_linear_conversation(mapping, "n3")
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello, what is Python?"
        assert result[0]["timestamp"] == 1700000001.0
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "Python is a programming language..."
        assert result[1]["timestamp"] == 1700000002.0

    def test_skips_system_messages(self) -> None:
        """System role messages are filtered out."""
        mapping = {
            "n1": _make_node("n1", "system", "You are a helpful assistant.", None, ["n2"]),
            "n2": _make_node("n2", "user", "Hi", "n1", [], 1700000001.0),
        }
        result = extract_linear_conversation(mapping, "n2")
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_skips_empty_content(self) -> None:
        """Nodes with null/empty message content are skipped."""
        mapping = {
            "n1": _make_node("n1", "user", "Hi", None, ["n2"], 1700000001.0),
            "n2": {
                "id": "n2",
                "message": None,
                "parent": "n1",
                "children": ["n3"],
            },
            "n3": _make_node("n3", "assistant", "Hello!", "n2", [], 1700000003.0),
        }
        result = extract_linear_conversation(mapping, "n3")
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_handles_circular_reference(self) -> None:
        """Circular parent pointers don't cause infinite loops."""
        mapping = {
            "n1": _make_node("n1", "user", "A", "n2", ["n2"], 1700000001.0),
            "n2": _make_node("n2", "assistant", "B", "n1", [], 1700000002.0),
        }
        # Should terminate without hanging
        result = extract_linear_conversation(mapping, "n2")
        assert isinstance(result, list)
        # Should have at most 2 messages (no infinite loop)
        assert len(result) <= 2

    def test_single_node(self) -> None:
        """Single user message node returns one-element list."""
        mapping = {
            "n1": _make_node("n1", "user", "Solo message", None, [], 1700000001.0),
        }
        result = extract_linear_conversation(mapping, "n1")
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Solo message"

    def test_skips_empty_parts(self) -> None:
        """Node with empty string in parts is skipped."""
        mapping = {
            "n1": _make_node("n1", "user", "", None, ["n2"]),
            "n2": _make_node("n2", "assistant", "Response", "n1", [], 1700000002.0),
        }
        result = extract_linear_conversation(mapping, "n2")
        # n1 has empty content -> should be skipped
        assert len(result) == 1
        assert result[0]["role"] == "assistant"

    def test_missing_current_node(self) -> None:
        """If current_node not in mapping, returns empty list."""
        mapping = {
            "n1": _make_node("n1", "user", "Hello", None, [], 1700000001.0),
        }
        result = extract_linear_conversation(mapping, "nonexistent")
        assert result == []

    def test_timestamp_none_when_missing(self) -> None:
        """Timestamp is None when create_time is missing from message."""
        mapping = {
            "n1": _make_node("n1", "user", "Hello", None, [], None),
        }
        result = extract_linear_conversation(mapping, "n1")
        assert len(result) == 1
        assert result[0]["timestamp"] is None


# ===========================================================================
# parse_conversations_file
# ===========================================================================


class TestParseConversationsFile:
    """Tests for parse_conversations_file()."""

    def test_valid_file(self, tmp_path: Path) -> None:
        """Parse a sample file with 2 conversations, correct count."""
        conv1 = _make_conversation(conv_id="c1", title="Conv 1", current_node="node-3")
        conv2 = _make_conversation(conv_id="c2", title="Conv 2", current_node="node-3")
        fpath = tmp_path / "conversations.json"
        fpath.write_text(json.dumps([conv1, conv2]))

        result = parse_conversations_file(str(fpath))
        assert len(result) == 2
        assert result[0]["id"] == "c1"
        assert result[0]["title"] == "Conv 1"
        assert result[0]["source"] == "chatgpt"
        assert isinstance(result[0]["messages"], list)
        assert result[1]["id"] == "c2"

    def test_file_not_found(self) -> None:
        """Returns empty list on file not found."""
        result = parse_conversations_file("/nonexistent/path/conversations.json")
        assert result == []

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Returns empty list on invalid JSON."""
        fpath = tmp_path / "conversations.json"
        fpath.write_text("not valid json {{{{")

        result = parse_conversations_file(str(fpath))
        assert result == []

    def test_malformed_conversation(self, tmp_path: Path) -> None:
        """Skips bad conversations, returns the rest."""
        good_conv = _make_conversation(conv_id="good", title="Good")
        bad_conv = {"id": "bad"}  # Missing mapping, current_node
        fpath = tmp_path / "conversations.json"
        fpath.write_text(json.dumps([good_conv, bad_conv]))

        result = parse_conversations_file(str(fpath))
        assert len(result) == 1
        assert result[0]["id"] == "good"

    def test_empty_array(self, tmp_path: Path) -> None:
        """Returns empty list for empty JSON array."""
        fpath = tmp_path / "conversations.json"
        fpath.write_text(json.dumps([]))

        result = parse_conversations_file(str(fpath))
        assert result == []

    def test_conversation_create_time(self, tmp_path: Path) -> None:
        """Conversation create_time is preserved."""
        conv = _make_conversation(create_time=1700099999.0)
        fpath = tmp_path / "conversations.json"
        fpath.write_text(json.dumps([conv]))

        result = parse_conversations_file(str(fpath))
        assert result[0]["create_time"] == 1700099999.0


# ===========================================================================
# conversations_to_memory_items
# ===========================================================================


class TestConversationsToMemoryItems:
    """Tests for conversations_to_memory_items()."""

    def test_basic_conversion(self) -> None:
        """Correct key/content/source_cli/tags."""
        conversations = [
            {
                "id": "abcdef12-3456-7890-abcd-ef1234567890",
                "title": "Test Title",
                "messages": [
                    {"role": "user", "content": "Hello", "timestamp": 1700000001.0},
                    {"role": "assistant", "content": "Hi!", "timestamp": 1700000002.0},
                ],
                "create_time": 1700000000.0,
                "source": "chatgpt",
            }
        ]
        result = conversations_to_memory_items(conversations)
        assert len(result) == 1
        item = result[0]
        assert "id" in item
        assert item["key"] == "chatgpt-abcdef12"
        assert item["source_cli"] == "chatgpt"
        assert item["tags"] == ["chatgpt", "imported"]
        assert "# Test Title" in item["content"]
        assert "**user**: Hello" in item["content"]
        assert "**assistant**: Hi!" in item["content"]

    def test_truncates_long_content(self) -> None:
        """Content is truncated to 5000 chars max."""
        long_msg = "x" * 6000
        conversations = [
            {
                "id": "longid00-0000-0000-0000-000000000000",
                "title": "Long",
                "messages": [
                    {"role": "user", "content": long_msg, "timestamp": 1700000001.0},
                ],
                "create_time": 1700000000.0,
                "source": "chatgpt",
            }
        ]
        result = conversations_to_memory_items(conversations)
        assert len(result) == 1
        assert len(result[0]["content"]) <= 5000

    def test_empty_input(self) -> None:
        """Returns empty list for empty input."""
        result = conversations_to_memory_items([])
        assert result == []

    def test_no_messages_skipped(self) -> None:
        """Conversation with no messages is skipped."""
        conversations = [
            {
                "id": "empty000-0000-0000-0000-000000000000",
                "title": "Empty",
                "messages": [],
                "create_time": 1700000000.0,
                "source": "chatgpt",
            }
        ]
        result = conversations_to_memory_items(conversations)
        assert result == []

    def test_multiple_conversations(self) -> None:
        """Multiple conversations each become one memory item."""
        conversations = [
            {
                "id": f"conv{i}000-0000-0000-0000-000000000000",
                "title": f"Conv {i}",
                "messages": [
                    {"role": "user", "content": f"Message {i}", "timestamp": 1700000001.0},
                ],
                "create_time": 1700000000.0,
                "source": "chatgpt",
            }
            for i in range(3)
        ]
        result = conversations_to_memory_items(conversations)
        assert len(result) == 3


# ===========================================================================
# Full pipeline
# ===========================================================================


class TestFullPipeline:
    """End-to-end: file -> parse -> convert -> verify memory items."""

    def test_full_pipeline(self, tmp_path: Path) -> None:
        """File -> parse -> convert -> verify memory items."""
        conv = _make_conversation(
            conv_id="pipeline-test-uuid-1234",
            title="Pipeline Test",
        )
        fpath = tmp_path / "conversations.json"
        fpath.write_text(json.dumps([conv]))

        parsed = parse_conversations_file(str(fpath))
        assert len(parsed) == 1
        assert parsed[0]["source"] == "chatgpt"

        items = conversations_to_memory_items(parsed)
        assert len(items) == 1
        item = items[0]
        assert item["key"] == "chatgpt-pipeline"
        assert item["source_cli"] == "chatgpt"
        assert "chatgpt" in item["tags"]
        assert "imported" in item["tags"]
        assert "# Pipeline Test" in item["content"]
        assert "**user**: Hello" in item["content"]
        assert "**assistant**: Hi there!" in item["content"]
