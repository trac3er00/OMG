from __future__ import annotations
import pytest
from runtime.team_memory import TeamMemory


def test_write_and_read(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    entry = tm.write(
        "preferences", {"preference": "naming", "value": "camelCase"}, author="alice"
    )
    assert entry.author == "alice"
    results = tm.read()
    assert len(results) == 1


def test_viewer_cannot_write(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    with pytest.raises(PermissionError):
        tm.write("preferences", {"preference": "x", "value": "y"}, role="viewer")


def test_read_by_category(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    tm.write("preferences", {"preference": "p1", "value": "v1"}, author="alice")
    tm.write("failures", {"what": "bug", "why": "typo"}, author="bob")
    prefs = tm.read(category="preferences")
    assert len(prefs) == 1
    assert prefs[0].category == "preferences"


def test_read_by_author(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    tm.write("preferences", {"preference": "p1", "value": "v1"}, author="alice")
    tm.write("preferences", {"preference": "p2", "value": "v2"}, author="bob")
    alice_entries = tm.read(author="alice")
    assert len(alice_entries) == 1
    assert alice_entries[0].author == "alice"


def test_admin_can_delete(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    entry = tm.write("preferences", {"preference": "x", "value": "y"}, author="alice")
    success = tm.delete(entry.entry_id, role="admin")
    assert success is True
    results = tm.read()
    assert len(results) == 0


def test_non_admin_cannot_delete(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    entry = tm.write("preferences", {"preference": "x", "value": "y"}, author="alice")
    with pytest.raises(PermissionError):
        tm.delete(entry.entry_id, role="developer")


def test_empty_store_returns_empty(tmp_path: "Path") -> None:
    tm = TeamMemory(str(tmp_path))
    results = tm.read()
    assert results == []
