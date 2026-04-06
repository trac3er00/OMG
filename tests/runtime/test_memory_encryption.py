from __future__ import annotations

import warnings
from pathlib import Path

import pytest

import runtime.memory_store as memory_store_module
from runtime.memory_store import MemoryStore


def test_plaintext_decrypt_raises_value_error(tmp_path: Path) -> None:
    """Phase 2: plaintext reads now raise ValueError (no longer just warn)."""
    store = MemoryStore(store_path=str(tmp_path / "store.sqlite3"))

    with pytest.raises(ValueError) as exc_info:
        store._decrypt_text("plaintext-data", purpose="test")

    assert (
        "migrate" in str(exc_info.value).lower()
        or "encrypt" in str(exc_info.value).lower()
    )


def test_memory_write_without_cryptography_raises_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore(store_path=str(tmp_path / "store.sqlite3"))
    monkeypatch.setattr(memory_store_module, "Fernet", None)
    monkeypatch.setattr(store, "_fernet_available", False, raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        store._encrypt_text("secret", purpose="sqlite-content")

    assert str(excinfo.value) == (
        "cryptography package required for MemoryStore encryption. "
        "Install with: pip install cryptography"
    )
