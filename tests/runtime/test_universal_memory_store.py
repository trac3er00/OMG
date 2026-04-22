from __future__ import annotations

import json
from pathlib import Path

from runtime.memory_store import MemoryStore


def test_universal_memory_persists_nested_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    store = MemoryStore()
    store.set("user.theme", "dark")
    store.set("team.review.required", True)

    assert store.get("user.theme") == "dark"
    assert store.get("team.review.required") is True
    assert store.list() == {
        "user": {"theme": "dark"},
        "team": {"review": {"required": True}},
    }

    persisted = tmp_path / ".omg" / "memory" / "memory.json"
    assert persisted.exists()
    assert json.loads(persisted.read_text(encoding="utf-8")) == store.list()
