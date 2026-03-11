"""Claude.ai paste-based memory import."""

import re
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from runtime.memory_store import MemoryStore


class MemoryItem(TypedDict):
    """Memory item structure."""

    key: str
    content: str
    source_cli: str
    tags: list[str]


EXTRACTION_PROMPT = (
    "List every memory you have stored about me. "
    "Format each memory as a bullet point starting with '- '. "
    "Include all preferences, facts, and context you remember."
)


def parse_claude_paste(text: str) -> list[MemoryItem]:
    """Parse Claude.ai paste-based memory list into structured items.

    Handles multiple formats:
    - Bullet points: "- item", "* item", "• item"
    - Numbered lists: "1. item", "2. item"
    - Plain paragraphs: one per line

    Args:
        text: Freeform text pasted from Claude.ai memory list

    Returns:
        List of memory item dicts with keys: key, content, source_cli, tags
    """
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    items: list[MemoryItem] = []
    item_index = 1

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        content = stripped

        if content.startswith("- "):
            content = content[2:].strip()
        elif content.startswith("* "):
            content = content[2:].strip()
        elif content.startswith("• "):
            content = content[2:].strip()
        elif re.match(r"^\d+\.\s", content):
            content = re.sub(r"^\d+\.\s+", "", content).strip()

        if not content:
            continue

        item: MemoryItem = {
            "key": f"claude-memory-{item_index}",
            "content": content,
            "source_cli": "claude-web",
            "tags": ["claude-web", "imported"],
        }
        items.append(item)
        item_index += 1

    return items


def import_from_paste(text: str, store: "MemoryStore") -> int:
    """Import memories from Claude.ai paste into a MemoryStore.

    Args:
        text: Pasted memory list from Claude.ai
        store: MemoryStore instance to add items to

    Returns:
        Count of items successfully added to store
    """
    items = parse_claude_paste(text)
    count = 0

    for item in items:
        content = item.get("content", "")
        if content:  # Skip empty content
            key = item.get("key", "")
            source_cli = item.get("source_cli", "claude-web")
            tags = item.get("tags", [])
            if isinstance(key, str) and isinstance(source_cli, str) and isinstance(tags, list):
                store.add(
                    key=key,
                    content=content,
                    source_cli=source_cli,
                    tags=tags,
                )
                count += 1

    return count
