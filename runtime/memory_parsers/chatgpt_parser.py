"""ChatGPT conversations.json parser for OMG shared memory import.

Parses the ChatGPT data export format (``conversations.json``) and converts
conversations into OMG memory items compatible with :class:`MemoryStore`.

Functions:
    extract_linear_conversation — traverse mapping tree to ordered message list
    parse_conversations_file   — read + parse the export JSON file
    conversations_to_memory_items — convert parsed conversations to memory items
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum traversal depth to guard against circular parent references.
_MAX_DEPTH = 10_000

# Maximum content length per memory item (chars).
_MAX_CONTENT_LENGTH = 5_000


# ---------------------------------------------------------------------------
# extract_linear_conversation
# ---------------------------------------------------------------------------


def extract_linear_conversation(
    mapping: dict[str, Any],
    current_node: str,
) -> list[dict[str, Any]]:
    """Walk *current_node* back to root via ``parent`` pointers.

    Returns a chronologically ordered list (root -> leaf) of message dicts::

        {"role": str, "content": str, "timestamp": float | None}

    * Skips nodes whose ``message`` is ``None`` or has empty text.
    * Skips ``system`` role messages.
    * Guards against circular references with a depth limit of 10 000.
    """
    if current_node not in mapping:
        return []

    # Collect nodes from current_node back to root.
    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    node_id: str | None = current_node

    depth = 0
    while node_id is not None and depth < _MAX_DEPTH:
        if node_id in visited:
            break
        visited.add(node_id)

        node = mapping.get(node_id)
        if node is None:
            break

        chain.append(node)
        node_id = node.get("parent")
        depth += 1

    # Reverse so root comes first (chronological order).
    chain.reverse()

    messages: list[dict[str, Any]] = []
    for node in chain:
        msg = node.get("message")
        if msg is None:
            continue

        author = msg.get("author") or {}
        role = author.get("role", "")

        # Skip system messages.
        if role == "system":
            continue

        content_obj = msg.get("content") or {}
        parts = content_obj.get("parts") or []
        text = "".join(str(p) for p in parts).strip()

        # Skip empty content.
        if not text:
            continue

        timestamp = msg.get("create_time")

        messages.append(
            {
                "role": role,
                "content": text,
                "timestamp": timestamp,
            }
        )

    return messages


# ---------------------------------------------------------------------------
# parse_conversations_file
# ---------------------------------------------------------------------------


def parse_conversations_file(file_path: str) -> list[dict[str, Any]]:
    """Read and parse a ChatGPT ``conversations.json`` export file.

    For each conversation object, calls :func:`extract_linear_conversation`
    to obtain an ordered message list.

    Returns a list of conversation dicts::

        {
            "id": str,
            "title": str,
            "messages": list[dict],
            "create_time": float | None,
            "source": "chatgpt",
        }

    Gracefully handles:
    * File not found -> empty list
    * Invalid JSON -> empty list
    * Malformed individual conversations -> logged warning, skipped
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("Conversations file not found: %s", file_path)
        return []

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read conversations file: %s", exc)
        return []

    # Warn about potentially large files.
    file_size = path.stat().st_size
    if file_size > 50 * 1024 * 1024:  # 50 MB
        warnings.warn(
            f"Large conversations file ({file_size / 1024 / 1024:.1f} MB). "
            "Consider using streaming JSON parser (ijson) for better memory usage.",
            ResourceWarning,
            stacklevel=2,
        )

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in conversations file: %s", exc)
        return []

    if not isinstance(data, list):
        logger.warning("Expected JSON array, got %s", type(data).__name__)
        return []

    results: list[dict[str, Any]] = []

    for conv in data:
        try:
            conv_id = conv["id"]
            title = conv.get("title", "Untitled")
            mapping = conv["mapping"]
            current_node = conv["current_node"]
            create_time = conv.get("create_time")

            messages = extract_linear_conversation(mapping, current_node)

            results.append(
                {
                    "id": conv_id,
                    "title": title,
                    "messages": messages,
                    "create_time": create_time,
                    "source": "chatgpt",
                }
            )
        except (KeyError, TypeError) as exc:
            conv_id_str = conv.get("id", "<unknown>") if isinstance(conv, dict) else "<invalid>"
            logger.warning(
                "Skipping malformed conversation %s: %s", conv_id_str, exc
            )

    return results


# ---------------------------------------------------------------------------
# conversations_to_memory_items
# ---------------------------------------------------------------------------


def conversations_to_memory_items(
    conversations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert parsed conversations to OMG memory item format.

    Each conversation becomes ONE memory item with::

        {
            "key": "chatgpt-{id[:8]}",
            "content": "# {title}\\n\\n**role**: content\\n\\n...",
            "source_cli": "chatgpt",
            "tags": ["chatgpt", "imported"],
        }

    * Conversations with no messages are skipped.
    * Content is truncated to 5 000 chars max.
    """
    items: list[dict[str, Any]] = []

    for conv in conversations:
        messages = conv.get("messages", [])
        if not messages:
            continue

        conv_id = conv.get("id", "unknown")
        title = conv.get("title", "Untitled")

        # Build content string.
        parts = [f"# {title}", ""]
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"**{role}**: {content}")

        full_content = "\n\n".join(parts)

        # Truncate to max length.
        if len(full_content) > _MAX_CONTENT_LENGTH:
            full_content = full_content[:_MAX_CONTENT_LENGTH]

        items.append(
            {
                "key": f"chatgpt-{conv_id[:8]}",
                "content": full_content,
                "source_cli": "chatgpt",
                "tags": ["chatgpt", "imported"],
            }
        )

    return items


__all__ = [
    "extract_linear_conversation",
    "parse_conversations_file",
    "conversations_to_memory_items",
]
