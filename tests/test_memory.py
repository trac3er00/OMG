#!/usr/bin/env python3
"""Tests for runtime.memory_store.MemoryStore API."""
import os
from pathlib import Path

import pytest

from runtime.memory_store import MemoryStore


def test_memory_set_and_get(tmp_path: Path) -> None:
    """Set a value and retrieve it back."""
    store_path = tmp_path / "memory.json"
    store = MemoryStore(store_path=str(store_path))

    store.set("user.theme", "dark")
    result = store.get("user.theme")

    assert result == "dark"
    store.close()


def test_memory_persistence(tmp_path: Path) -> None:
    """Set a value, create a new MemoryStore instance, and retrieve it."""
    store_path = tmp_path / "memory.json"

    store1 = MemoryStore(store_path=str(store_path))
    store1.set("user.editor", "vim")
    store1.close()

    store2 = MemoryStore(store_path=str(store_path))
    result = store2.get("user.editor")

    assert result == "vim"
    store2.close()


def test_memory_list(tmp_path: Path) -> None:
    """Set multiple values and verify list_all returns all."""
    store_path = tmp_path / "memory.json"
    store = MemoryStore(store_path=str(store_path))

    store.set("user.theme", "dark")
    store.set("user.editor", "emacs")
    store.set("project.style", "google")

    all_items = store.list_all()

    keys_found = {item["key"] for item in all_items}
    assert "cmms::user.theme" in keys_found
    assert "cmms::user.editor" in keys_found
    assert "cmms::project.style" in keys_found
    store.close()


def test_memory_user_preferences(tmp_path: Path) -> None:
    """Test user.theme and user.editor keys."""
    store_path = tmp_path / "memory.json"
    store = MemoryStore(store_path=str(store_path))

    store.set("user.theme", "light")
    store.set("user.editor", "code")

    assert store.get("user.theme") == "light"
    assert store.get("user.editor") == "code"
    store.close()


def test_memory_project_rules(tmp_path: Path) -> None:
    """Test project.style key."""
    store_path = tmp_path / "memory.json"
    store = MemoryStore(store_path=str(store_path))

    store.set("project.style", "pep8")

    assert store.get("project.style") == "pep8"
    store.close()
