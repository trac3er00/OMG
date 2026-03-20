"""Tests for memory CLI commands (NF2c)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "omg.py"


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run omg.py with the given arguments.

    Security Review: This function uses subprocess.run to invoke our own CLI.
    This pattern has been reviewed and is safe because:
    - It only executes the project's own omg.py script (SCRIPT path is hardcoded)
    - Arguments come from test code, not external user input
    - This is a test utility for verifying CLI behavior
    """
    merged_env = dict(os.environ)
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
        timeout=30,
    )


class TestMemoryExport:
    """Tests for cmd_memory_export."""

    def test_export_json_format_outputs_valid_json(self, tmp_path: Path) -> None:
        """Test that export with json format outputs valid JSON."""
        store_path = tmp_path / "test_store.sqlite3"
        env = {"OMG_MEMORY_STORE": str(store_path)}

        # Initialize an empty store by writing empty array


        result = _run(["memory", "export", "--format", "json"], env=env)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should be valid JSON
        try:
            data = json.loads(result.stdout)
            assert isinstance(data, list)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.stdout}")

    def test_export_markdown_format_has_header(self, tmp_path: Path) -> None:
        """Test that markdown export includes proper header."""
        store_path = tmp_path / "test_store.sqlite3"
        env = {"OMG_MEMORY_STORE": str(store_path)}


        result = _run(["memory", "export", "--format", "markdown"], env=env)

        assert result.returncode == 0
        assert "# OMG Shared Memory Export" in result.stdout

    def test_export_to_file(self, tmp_path: Path) -> None:
        """Test export writes to file when --output is specified."""
        store_path = tmp_path / "test_store.sqlite3"
        output_path = tmp_path / "export.json"
        env = {"OMG_MEMORY_STORE": str(store_path)}


        result = _run(["memory", "export", "--format", "json", "--output", str(output_path)], env=env)

        assert result.returncode == 0
        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert isinstance(data, list)


class TestMemoryImport:
    """Tests for cmd_memory_import."""

    def test_import_json_file(self, tmp_path: Path) -> None:
        """Test importing a JSON file with memory items."""
        db_path = tmp_path / "store.sqlite3"
        import_path = tmp_path / "import.json"
        env = {"OMG_MEMORY_STORE": str(db_path)}

        items = [
            {
                "id": "test-id-001",
                "key": "test-key",
                "content": "Test content",
                "source_cli": "test",
                "tags": ["test"],
            }
        ]
        import_path.write_text(json.dumps(items), encoding="utf-8")

        result = _run(["memory", "import", str(import_path)], env=env)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["status"] == "ok"
        assert output["imported"] == 1
        assert output["quarantined"] is True

    def test_import_with_review_flag(self, tmp_path: Path) -> None:
        """Test that --review sets quarantined=False."""
        store_path = tmp_path / "test_store.sqlite3"
        import_path = tmp_path / "import.json"
        env = {"OMG_MEMORY_STORE": str(store_path)}



        items = [
            {
                "id": "test-id-002",
                "key": "reviewed-key",
                "content": "Reviewed content",
                "source_cli": "test",
                "tags": ["reviewed"],
            }
        ]
        import_path.write_text(json.dumps(items), encoding="utf-8")

        result = _run(["memory", "import", str(import_path), "--review"], env=env)

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ok"
        assert output["quarantined"] is False

    def test_import_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        """Test that importing nonexistent file returns error."""
        store_path = tmp_path / "test_store.sqlite3"
        env = {"OMG_MEMORY_STORE": str(store_path)}


        result = _run(["memory", "import", "/nonexistent/file.json"], env=env)

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["status"] == "error"


class TestMemoryList:
    """Tests for cmd_memory_list."""

    def test_list_shows_header(self, tmp_path: Path) -> None:
        """Test that list command shows table header."""
        store_path = tmp_path / "test_store.sqlite3"
        env = {"OMG_MEMORY_STORE": str(store_path)}


        result = _run(["memory", "list"], env=env)

        assert result.returncode == 0
        assert "ID | Key | Layer | Confidence | Created At" in result.stdout

    def test_list_shows_entries(self, tmp_path: Path) -> None:
        """Test that list command shows stored entries from SQLite."""
        db_path = tmp_path / "store.sqlite3"

        # Pre-populate a SQLite store with test data
        from runtime.memory_store import MemoryStore
        store = MemoryStore(store_path=str(db_path))
        store.add(key="my-key", content="My content", source_cli="test", tags=[])
        del store

        result = _run(["memory", "list"], env={"OMG_MEMORY_STORE": str(db_path)})

        assert result.returncode == 0
        assert "my-key" in result.stdout

    def test_list_with_layer_filter(self, tmp_path: Path) -> None:
        """Test list filtering by layer (namespace in MemoryStore API)."""
        db_path = tmp_path / "store.sqlite3"

        from runtime.memory_store import MemoryStore
        store = MemoryStore(store_path=str(db_path))
        # Note: MemoryStore uses 'namespace' internally, but CLI uses 'layer' terminology
        store.add(key="project-key", content="Content 1", source_cli="test", tags=[], namespace="project")
        store.add(key="session-key", content="Content 2", source_cli="test", tags=[], namespace="session")
        del store

        result = _run(["memory", "list", "--layer", "project"], env={"OMG_MEMORY_STORE": str(db_path)})

        assert result.returncode == 0
        assert "project-key" in result.stdout
        assert "session-key" not in result.stdout


class TestMemorySync:
    """Tests for cmd_memory_sync."""

    def test_sync_from_claude_paste(self, tmp_path: Path) -> None:
        """Test syncing from Claude.ai paste format."""
        store_path = tmp_path / "test_store.sqlite3"
        paste_path = tmp_path / "paste.txt"
        env = {"OMG_MEMORY_STORE": str(store_path)}


        paste_path.write_text("- User prefers Python\n- User works on OMG project\n", encoding="utf-8")

        result = _run(["memory", "sync", "--from-web", str(paste_path)], env=env)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["status"] == "ok"
        assert output["imported"] == 2
        assert output["source"] == "web-paste"

    def test_sync_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        """Test that syncing from nonexistent file returns error."""
        store_path = tmp_path / "test_store.sqlite3"
        env = {"OMG_MEMORY_STORE": str(store_path)}


        result = _run(["memory", "sync", "--from-web", "/nonexistent/paste.txt"], env=env)

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["status"] == "error"


class TestExportImportRoundTrip:
    """Tests for export/import round-trip data preservation."""

    def test_roundtrip_preserves_data(self, tmp_path: Path) -> None:
        """Test that export then import preserves memory data."""
        store_path = tmp_path / "source_store.sqlite3"
        new_store_path = tmp_path / "dest_store.sqlite3"
        export_path = tmp_path / "export.json"
        env1 = {"OMG_MEMORY_STORE": str(store_path)}
        env2 = {"OMG_MEMORY_STORE": str(new_store_path)}

        # Pre-populate source store via MemoryStore API
        from runtime.memory_store import MemoryStore
        store = MemoryStore(store_path=str(store_path))
        store.add(key="roundtrip-key", content="Important data to preserve",
                  source_cli="test-cli", tags=["tag1", "tag2"])
        del store

        # Export from source store
        export_result = _run(["memory", "export", "--format", "json", "--output", str(export_path)], env=env1)
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        # Import to new store with --review to set quarantined=False
        import_result = _run(["memory", "import", str(export_path), "--review"], env=env2)
        assert import_result.returncode == 0, f"Import failed: {import_result.stderr}"

        # Verify data was preserved by reading dest store
        dest_store = MemoryStore(store_path=str(new_store_path))
        items = dest_store.list_all(include_quarantined=True)
        assert len(items) >= 1
        roundtrip_items = [i for i in items if i.get("key") == "roundtrip-key"]
        assert len(roundtrip_items) == 1
        assert roundtrip_items[0]["content"] == "Important data to preserve"
