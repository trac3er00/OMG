"""Export memory items to markdown format."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def export_to_markdown(items: list[dict[str, Any]]) -> str:
    """Convert list of memory items to markdown string.

    Args:
        items: List of memory item dicts with keys: id, key, content, source_cli, tags, created_at, updated_at

    Returns:
        Markdown string with formatted memory items.
    """
    # Generate current timestamp in ISO format
    now = datetime.now(timezone.utc).isoformat()

    # Start with header
    lines = [
        "# OMG Shared Memory Export",
        "",
        f"Generated: {now}",
        f"Total items: {len(items)}",
        "",
        "---",
        "",
    ]

    # Add each item
    for idx, item in enumerate(items, start=1):
        key = item.get("key", "unknown")
        content = item.get("content", "")
        source_cli = item.get("source_cli", "unknown")
        tags = item.get("tags", [])
        created_at = item.get("created_at", "")
        updated_at = item.get("updated_at", "")

        # Format tags as comma-separated string
        tags_str = ", ".join(tags) if tags else ""

        lines.append(f"## Memory {idx}: {key}")
        lines.append("")
        lines.append(f"**Source**: {source_cli}")
        lines.append(f"**Tags**: {tags_str}")
        lines.append(f"**Created**: {created_at}")
        lines.append(f"**Updated**: {updated_at}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_to_file(items: list[dict[str, Any]], output_path: str) -> None:
    """Write export_to_markdown(items) to the given file path.

    Creates parent directories if missing. Overwrites if file exists.

    Args:
        items: List of memory item dicts
        output_path: Path where to write the markdown file
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    markdown = export_to_markdown(items)
    _ = path.write_text(markdown)


def export_from_store(store: Any, output_path: str | None = None) -> str:  # pyright: ignore[reportExplicitAny]
    """Export all items from a MemoryStore to markdown.

    Gets all items from store.export_all(). If output_path is given, writes to file.
    Always returns the markdown string.

    Args:
        store: MemoryStore instance
        output_path: Optional path to write markdown file to

    Returns:
        Markdown string representation of all items
    """
    items = store.export_all()
    markdown = export_to_markdown(items)

    if output_path is not None:
        export_to_file(items, output_path)

    return markdown


__all__ = ["export_to_markdown", "export_to_file", "export_from_store"]
