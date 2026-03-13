"""Gemini Web paste-based memory import — parse and import memories from Gemini Web interface."""

from __future__ import annotations

import re
from typing import Any  # pyright: ignore[reportExplicitAny]

EXTRACTION_PROMPT = (
    "What do you remember about me? List all preferences, facts, and context you have stored. "
    "Format each as a bullet point starting with '- '."
)


def parse_gemini_paste(text: str) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny]
    """Parse memories from Gemini Web paste text.

    Supports bullet points (- item) and numbered lists (1. item).

    Args:
        text: Raw text pasted from Gemini Web interface.

    Returns:
        List of memory items with keys, content, source_cli, and tags.
    """
    if not text or not text.strip():
        return []

    items: list[str] = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try bullet point format: "- item"
        if line.startswith("-"):
            content = line[1:].strip()
            if content:
                items.append(content)
            continue

        # Try numbered format: "1. item", "2. item", etc.
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            content = match.group(1).strip()
            if content:
                items.append(content)
            continue

    # Convert to memory item dicts
    result: list[dict[str, Any]] = []
    for i, content in enumerate(items):
        result.append(
            {
                "key": f"gemini-memory-{i+1}",
                "content": content,
                "source_cli": "gemini-web",
                "tags": ["gemini-web", "imported"],
            }
        )

    return result


def import_from_paste(text: str, store: Any) -> int:  # pyright: ignore[reportAny]
    """Import memories from Gemini Web paste into the memory store.

    Args:
        text: Raw text pasted from Gemini Web interface.
        store: MemoryStore instance to add items to.

    Returns:
        Number of items successfully imported.
    """
    items = parse_gemini_paste(text)
    count = 0

    for item in items:
        store.add(  # pyright: ignore[reportAny]
            key=item["key"],
            content=item["content"],
            source_cli=item["source_cli"],
            tags=item["tags"],
        )
        count += 1

    return count


__all__ = ["EXTRACTION_PROMPT", "parse_gemini_paste", "import_from_paste"]
