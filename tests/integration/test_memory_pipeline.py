"""Integration tests for the full memory pipeline: import → store → export.

Tests exercise real parser → MemoryStore → export flows across all CLI providers
(ChatGPT, Claude, Gemini, Kimi) and cross-CLI aggregation scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path

from runtime.memory_store import MemoryStore


# ---------------------------------------------------------------------------
# 1. ChatGPT parse → store → export pipeline
# ---------------------------------------------------------------------------


def test_chatgpt_parse_store_export_pipeline(tmp_path: Path) -> None:
    """Full pipeline: ChatGPT conversations.json → parse → store → export."""
    from runtime.memory_parsers.chatgpt_parser import (
        conversations_to_memory_items,
        parse_conversations_file,
    )
    from runtime.memory_parsers.export import export_from_store

    # Build a minimal but valid conversations.json
    conversations = [
        {
            "id": "conv-test-123456",
            "title": "Test Conversation",
            "create_time": 1700000000.0,
            "current_node": "n3",
            "mapping": {
                "n1": {"parent": None, "message": None},
                "n2": {
                    "parent": "n1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Hello, how are you?"]},
                        "create_time": 1700000001.0,
                    },
                },
                "n3": {
                    "parent": "n2",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["I'm doing well, thanks!"]},
                        "create_time": 1700000002.0,
                    },
                },
            },
        }
    ]
    conv_file = tmp_path / "conversations.json"
    conv_file.write_text(json.dumps(conversations))

    # Parse
    parsed = parse_conversations_file(str(conv_file))
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Test Conversation"
    assert len(parsed[0]["messages"]) == 2  # user + assistant (system skipped, None skipped)

    # Convert to memory items
    items = conversations_to_memory_items(parsed)
    assert len(items) == 1
    assert items[0]["source_cli"] == "chatgpt"
    assert items[0]["key"].startswith("chatgpt-")

    # Store
    store = MemoryStore(str(tmp_path / "store.json"))
    for item in items:
        store.add(item["key"], item["content"], item["source_cli"], item["tags"])
    assert store.count() == 1

    # Export and verify round-trip content integrity
    markdown = export_from_store(store)
    assert "chatgpt" in markdown.lower()
    assert "Test Conversation" in markdown
    assert store.count() > 0


# ---------------------------------------------------------------------------
# 2. Claude paste import → store → search pipeline
# ---------------------------------------------------------------------------


def test_claude_paste_import_search_pipeline(tmp_path: Path) -> None:
    """Claude paste → store → search verifies content and source_cli tagging."""
    from runtime.memory_parsers.claude_import import import_from_paste

    store = MemoryStore(str(tmp_path / "store.json"))
    text = "- I prefer Python\n- I work at Acme Corp\n- I like dark mode"

    count = import_from_paste(text, store)
    assert count == 3
    assert store.count() == 3

    # Search by keyword
    results = store.search("Python")
    assert len(results) == 1
    assert "Python" in results[0]["content"]
    assert results[0]["source_cli"] == "claude-web"

    # Search another keyword
    results_acme = store.search("Acme")
    assert len(results_acme) == 1
    assert results_acme[0]["source_cli"] == "claude-web"


# ---------------------------------------------------------------------------
# 3. Gemini paste import → store pipeline
# ---------------------------------------------------------------------------


def test_gemini_paste_import_pipeline(tmp_path: Path) -> None:
    """Gemini paste → store verifies item count and source_cli filtering."""
    from runtime.memory_parsers.gemini_import import import_from_paste

    store = MemoryStore(str(tmp_path / "store.json"))
    text = "- I prefer dark mode\n- My timezone is UTC+9"

    count = import_from_paste(text, store)
    assert count == 2
    assert store.count() == 2

    items = store.list_all(source_cli="gemini-web")
    assert len(items) == 2
    contents = {item["content"] for item in items}
    assert "I prefer dark mode" in contents
    assert "My timezone is UTC+9" in contents


# ---------------------------------------------------------------------------
# 4. Kimi paste import → store pipeline
# ---------------------------------------------------------------------------


def test_kimi_paste_import_pipeline(tmp_path: Path) -> None:
    """Kimi paste → store verifies item count and source_cli filtering."""
    from runtime.memory_parsers.kimi_import import import_from_paste

    store = MemoryStore(str(tmp_path / "store.json"))
    text = "- I prefer Python\n- I work remotely"

    count = import_from_paste(text, store)
    assert count == 2
    assert store.count() == 2

    items = store.list_all(source_cli="kimi-web")
    assert len(items) == 2
    contents = {item["content"] for item in items}
    assert "I prefer Python" in contents
    assert "I work remotely" in contents


# ---------------------------------------------------------------------------
# 5. Cross-CLI memory aggregation
# ---------------------------------------------------------------------------


def test_cross_cli_memory_aggregation(tmp_path: Path) -> None:
    """Import from multiple CLIs into one store, verify per-source filtering."""
    from runtime.memory_parsers.claude_import import import_from_paste as claude_import
    from runtime.memory_parsers.gemini_import import import_from_paste as gemini_import
    from runtime.memory_parsers.kimi_import import import_from_paste as kimi_import

    store = MemoryStore(str(tmp_path / "store.json"))

    claude_import("- Claude memory 1\n- Claude memory 2", store)
    gemini_import("- Gemini memory 1", store)
    kimi_import("- Kimi memory 1\n- Kimi memory 2\n- Kimi memory 3", store)

    assert store.count() == 6

    claude_items = store.list_all(source_cli="claude-web")
    gemini_items = store.list_all(source_cli="gemini-web")
    kimi_items = store.list_all(source_cli="kimi-web")
    assert len(claude_items) == 2
    assert len(gemini_items) == 1
    assert len(kimi_items) == 3

    # Verify all items returned without filter
    all_items = store.list_all()
    assert len(all_items) == 6


# ---------------------------------------------------------------------------
# 6. Export to file pipeline
# ---------------------------------------------------------------------------


def test_export_to_file_pipeline(tmp_path: Path) -> None:
    """Import → store → export to file verifies file creation and content."""
    from runtime.memory_parsers.claude_import import import_from_paste
    from runtime.memory_parsers.export import export_from_store

    store = MemoryStore(str(tmp_path / "store.json"))
    import_from_paste("- Memory 1\n- Memory 2", store)
    assert store.count() == 2

    output_file = str(tmp_path / "export.md")
    markdown = export_from_store(store, output_file)

    # File must exist with content
    assert Path(output_file).exists()
    file_content = Path(output_file).read_text()
    assert "Memory 1" in file_content
    assert "Memory 2" in file_content

    # Returned markdown matches file content
    assert "Memory 1" in markdown
    assert "Memory 2" in markdown
    assert "OMG Shared Memory Export" in markdown


# ---------------------------------------------------------------------------
# 7. Persistence across MemoryStore instances
# ---------------------------------------------------------------------------


def test_persistence_across_instances(tmp_path: Path) -> None:
    """Data persists: write with store1, read back with store2."""
    from runtime.memory_parsers.claude_import import import_from_paste

    store_path = str(tmp_path / "store.json")

    # Write with first instance
    store1 = MemoryStore(store_path)
    import_from_paste("- Persistent memory", store1)
    assert store1.count() == 1

    # Read with fresh instance — same file
    store2 = MemoryStore(store_path)
    assert store2.count() == 1
    items = store2.list_all()
    assert items[0]["content"] == "Persistent memory"
    assert items[0]["source_cli"] == "claude-web"


# ---------------------------------------------------------------------------
# 8. Import/export round-trip
# ---------------------------------------------------------------------------


def test_import_export_round_trip(tmp_path: Path) -> None:
    """export_all → import_items preserves items across stores."""
    store1 = MemoryStore(str(tmp_path / "store1.json"))
    store1.add("key1", "content1", "codex", ["tag1"])
    store1.add("key2", "content2", "gemini", ["tag2"])
    assert store1.count() == 2

    # Export from store1
    exported = store1.export_all()
    assert len(exported) == 2

    # Import into store2
    store2 = MemoryStore(str(tmp_path / "store2.json"))
    count = store2.import_items(exported)
    assert count == 2
    assert store2.count() == 2

    # Verify content integrity
    all_items = store2.list_all()
    keys = {item["key"] for item in all_items}
    assert "key1" in keys
    assert "key2" in keys

    # Re-import should skip duplicates (same IDs)
    count_dup = store2.import_items(exported)
    assert count_dup == 0
    assert store2.count() == 2
