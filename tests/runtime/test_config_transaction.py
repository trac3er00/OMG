from __future__ import annotations

import os
import time
from pathlib import Path
from typing import cast

import pytest

from runtime.config_transaction import ConfigReceipt, ConfigTransaction, ConfigTransactionError


def _sha256_hex(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_plan_execute_verify_multifile_round_trip(fake_home: Path, tmp_path: Path) -> None:
    _ = fake_home
    json_path = tmp_path / "settings.json"
    toml_path = tmp_path / "settings.toml"
    md_path = tmp_path / "README.md"

    _ = json_path.write_text('{"old": true}\n', encoding="utf-8")
    _ = toml_path.write_text('enabled = false\n', encoding="utf-8")
    _ = md_path.write_text('# Old\n', encoding="utf-8")

    json_new = '{"new": true}\n'
    toml_new = 'enabled = true\nname = "omg"\n'
    md_new = '# New\n\nUpdated.\n'

    tx = ConfigTransaction()
    tx.plan(json_path, json_new)
    tx.plan(toml_path, toml_new)
    tx.plan(md_path, md_new)

    receipt = tx.execute()

    assert receipt["executed"] is True
    assert receipt["rollback"] is None
    assert Path(receipt["backup_path"]).is_dir()
    assert json_path.read_text(encoding="utf-8") == json_new
    assert toml_path.read_text(encoding="utf-8") == toml_new
    assert md_path.read_text(encoding="utf-8") == md_new

    assert len(receipt["planned_writes"]) == 3
    planned_by_path = {entry["path"]: entry for entry in receipt["planned_writes"]}
    assert planned_by_path[str(json_path)]["content_hash"] == _sha256_hex(json_new)
    assert planned_by_path[str(toml_path)]["content_hash"] == _sha256_hex(toml_new)
    assert planned_by_path[str(md_path)]["content_hash"] == _sha256_hex(md_new)

    assert receipt["verification"][str(json_path)] == "ok"
    assert receipt["verification"][str(toml_path)] == "ok"
    assert receipt["verification"][str(md_path)] == "ok"


def test_dry_run_keeps_files_unchanged(fake_home: Path, tmp_path: Path) -> None:
    _ = fake_home
    a_path = tmp_path / "a.json"
    b_path = tmp_path / "b.toml"

    a_old = '{"a": 1}\n'
    b_old = 'enabled = false\n'
    _ = a_path.write_text(a_old, encoding="utf-8")
    _ = b_path.write_text(b_old, encoding="utf-8")

    tx = ConfigTransaction()
    tx.plan(a_path, '{"a": 2}\n')
    tx.plan(b_path, 'enabled = true\n')
    receipt = tx.dry_run()

    assert receipt["executed"] is False
    assert a_path.read_text(encoding="utf-8") == a_old
    assert b_path.read_text(encoding="utf-8") == b_old
    assert receipt["rollback"] is None
    assert receipt["backup_path"]
    assert Path(receipt["backup_path"]).is_dir()
    assert all(not entry["executed"] for entry in receipt["executed_writes"])


def test_write_failure_triggers_rollback_and_restores_original(
    fake_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = fake_home
    a_path = tmp_path / "a.json"
    b_path = tmp_path / "b.toml"

    a_old = '{"a": 1}\n'
    b_old = 'enabled = false\n'
    a_new = '{"a": 2}\n'
    b_new = 'enabled = true\n'

    _ = a_path.write_text(a_old, encoding="utf-8")
    _ = b_path.write_text(b_old, encoding="utf-8")

    tx = ConfigTransaction()
    tx.plan(a_path, a_new)
    tx.plan(b_path, b_new)

    from runtime import config_transaction as mod

    real_atomic_write = cast(object, getattr(mod, "_ATOMIC_WRITE_TEXT_SAFE"))

    def flaky_atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
        if Path(path) == b_path and content == b_new:
            raise OSError("injected write failure")
        writer = cast("_AtomicWriter", real_atomic_write)
        writer(Path(path), content, mode=mode)

    monkeypatch.setattr(mod, "_ATOMIC_WRITE_TEXT_SAFE", flaky_atomic_write)

    with pytest.raises(ConfigTransactionError, match="injected write failure") as exc_info:
        _ = tx.execute()

    receipt = cast(ConfigReceipt, exc_info.value.receipt)
    assert receipt is not None
    assert receipt["rollback"] is not None
    assert str(a_path) in receipt["rollback"]["restored"]
    assert str(b_path) in receipt["rollback"]["restored"]
    assert receipt["executed"] is True
    assert any(entry["path"] == str(a_path) and entry["executed"] for entry in receipt["executed_writes"])
    assert any(entry["path"] == str(b_path) and (not entry["executed"]) for entry in receipt["executed_writes"])

    assert a_path.read_text(encoding="utf-8") == a_old
    assert b_path.read_text(encoding="utf-8") == b_old


def test_list_backups_returns_newest_first(fake_home: Path, tmp_path: Path) -> None:
    _ = fake_home
    target = tmp_path / "x.md"
    _ = target.write_text("v1\n", encoding="utf-8")

    tx1 = ConfigTransaction()
    tx1.plan(target, "v2\n")
    first = tx1.execute()

    time.sleep(0.02)

    tx2 = ConfigTransaction()
    tx2.plan(target, "v3\n")
    second = tx2.execute()

    listed = tx2.list_backups()
    assert listed[0] == second["backup_path"]
    assert first["backup_path"] in listed


def test_lock_contention_raises_error(fake_home: Path, tmp_path: Path) -> None:
    state_dir = fake_home / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "config-transaction.lock"

    now_ms = int(time.time() * 1000)
    _ = lock_path.write_text(f"{os.getpid()}\n{now_ms}\n", encoding="utf-8")

    tx = ConfigTransaction()
    tx.plan(tmp_path / "x.json", '{"x": 1}\n')
    with pytest.raises(ConfigTransactionError, match="already held"):
        _ = tx.execute()


def test_stale_lock_cleanup_and_reacquire(fake_home: Path, tmp_path: Path) -> None:
    state_dir = fake_home / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "config-transaction.lock"

    old_ts = int(time.time() * 1000) - 20000
    _ = lock_path.write_text("999999\n" + str(old_ts) + "\n", encoding="utf-8")

    target = tmp_path / "stale.json"
    _ = target.write_text('{"before": true}\n', encoding="utf-8")

    tx = ConfigTransaction()
    tx.plan(target, '{"after": true}\n')
    receipt = tx.execute()

    assert receipt["executed"] is True
    assert target.read_text(encoding="utf-8") == '{"after": true}\n'
    assert not lock_path.exists()


class _AtomicWriter:
    def __call__(self, path: Path, content: str, *, mode: int = 0o600) -> None: ...
