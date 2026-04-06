from __future__ import annotations

from pathlib import Path

import pytest

from runtime.memory_store import MemoryStore


def test_plaintext_decrypt_raises_error(tmp_path: Path) -> None:
    store = MemoryStore(store_path=str(tmp_path / "store.sqlite3"))
    decrypt = getattr(store, "_decrypt_text")

    with pytest.raises(ValueError) as exc_info:
        _ = decrypt("plaintext-data", purpose="test")

    assert "npx omg memory migrate" in str(exc_info.value)


def test_plaintext_decrypt_error_has_helpful_message(tmp_path: Path) -> None:
    store = MemoryStore(store_path=str(tmp_path / "store.sqlite3"))
    decrypt = getattr(store, "_decrypt_text")

    with pytest.raises(ValueError) as exc_info:
        _ = decrypt("some plain text without enc:v1: prefix", purpose="test")

    error_msg = str(exc_info.value)
    assert "migrate" in error_msg.lower() or "encrypt" in error_msg.lower()


def test_encrypted_prefix_bypasses_plaintext_error(tmp_path: Path) -> None:
    store = MemoryStore(store_path=str(tmp_path / "store.sqlite3"))
    decrypt = getattr(store, "_decrypt_text")

    result = decrypt("enc:v1:some_invalid_ciphertext", purpose="test")

    assert result == ""
