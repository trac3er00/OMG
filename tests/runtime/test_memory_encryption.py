from __future__ import annotations

import warnings
from pathlib import Path

import pytest

import runtime.memory_store as memory_store_module
from runtime.memory_store import MemoryStore


def test_plaintext_decrypt_emits_deprecation_warning(tmp_path: Path) -> None:
    store = MemoryStore(store_path=str(tmp_path / "store.sqlite3"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = store._decrypt_text("plaintext-data", purpose="test")

    assert result == "plaintext-data"
    assert any(
        "plaintext" in str(warning.message).lower()
        or "deprecation" in str(warning.message).lower()
        for warning in caught
    ), (
        f"Expected plaintext deprecation warning, got: {[str(x.message) for x in caught]}"
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
