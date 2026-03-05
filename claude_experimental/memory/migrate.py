"""Legacy Markdown Memory Migration Utility.

Migrates existing .omg/state/memory/*.md files to SQLite MemoryStore.
Preserves original files (copy, don't move) for safe rollback.
Idempotent: running twice doesn't create duplicates (dedup via content hash).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import cast

from claude_experimental.memory.store import MemoryStore


def migrate_markdown_memories(
    project_dir: str,
    target_store: MemoryStore | None = None,
) -> dict[str, int]:
    """Migrate markdown memories from .omg/state/memory/ to SQLite store.

    Args:
        project_dir: Root project directory containing .omg/state/memory/
        target_store: MemoryStore instance (default: project-scoped store)

    Returns:
        Dict with keys:
        - files_found: Number of .md files discovered
        - memories_migrated: Number successfully inserted
        - errors: Number of files that failed to process
        - skipped_duplicates: Number skipped due to content hash collision
    """
    store = target_store or MemoryStore(scope="project")
    memory_dir = os.path.join(project_dir, ".omg", "state", "memory")

    result = {
        "files_found": 0,
        "memories_migrated": 0,
        "errors": 0,
        "skipped_duplicates": 0,
    }

    # Handle missing directory gracefully
    if not os.path.isdir(memory_dir):
        return result

    # Collect all .md files
    md_files = sorted(
        [f for f in os.listdir(memory_dir) if f.endswith(".md")],
        reverse=True,  # Process newest first
    )
    result["files_found"] = len(md_files)

    for filename in md_files:
        filepath = os.path.join(memory_dir, filename)

        try:
            # Read file content
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if not content.strip():
                result["errors"] += 1
                continue

            # Extract date from filename (format: YYYY-MM-DD-*.md)
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
            if date_match:
                date_str = date_match.group(1)
                try:
                    created_at = datetime.strptime(date_str, "%Y-%m-%d").timestamp()
                except ValueError:
                    created_at = datetime.now().timestamp()
            else:
                created_at = datetime.now().timestamp()

            # Compute content hash for deduplication
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check if memory with same content hash already exists
            existing = _find_memory_by_content_hash(store, content_hash)
            if existing is not None:
                result["skipped_duplicates"] += 1
                continue

            # Calculate importance: normalized to 500 chars
            importance = min(len(content) / 500.0, 1.0)

            # Build metadata
            metadata: dict[str, object] = {
                "content_hash": content_hash,
                "source_file": filename,
                "migrated_from": "markdown",
            }

            # Insert into store
            memory_id = store.save(
                content=content,
                memory_type="semantic",
                importance=importance,
                scope="project",
                metadata=metadata,
            )

            if memory_id > 0:
                result["memories_migrated"] += 1
            else:
                result["errors"] += 1

        except (OSError, IOError) as e:
            result["errors"] += 1
            continue

    return result


def _find_memory_by_content_hash(
    store: MemoryStore, content_hash: str
) -> dict[str, object] | None:
    """Search for existing memory with matching content hash in metadata.

    Args:
        store: MemoryStore instance
        content_hash: SHA256 hex digest to search for

    Returns:
        Memory dict if found, None otherwise
    """
    conn = store.connect()
    try:
        # Search metadata JSON for content_hash field
        rows = cast(
            list[tuple[object, ...]],
            conn.execute(
                """
                SELECT id, content, memory_type, importance, scope, metadata,
                       created_at, accessed_at, access_count, schema_version
                FROM memories
                WHERE scope = ? AND json_extract(metadata, '$.content_hash') = ?
                LIMIT 1
                """,
                ("project", content_hash),
            ).fetchall(),
        )

        if rows:
            row = rows[0]
            return {
                "id": row[0],
                "content": row[1],
                "memory_type": row[2],
                "importance": row[3],
                "scope": row[4],
                "metadata": json.loads(row[5]) if isinstance(row[5], str) else row[5],
                "created_at": row[6],
                "accessed_at": row[7],
                "access_count": row[8],
                "schema_version": row[9],
            }
        return None
    except Exception:
        # If query fails (e.g., json_extract not available), return None
        return None
    finally:
        conn.close()
