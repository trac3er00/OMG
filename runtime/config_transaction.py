from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import time
from typing import Literal, NotRequired, TypedDict, cast

from runtime import mcp_config_writers as _mcp_config_writers


_ATOMIC_WRITE_TEXT_SAFE = cast(
    "_AtomicWriteFn",
    getattr(_mcp_config_writers, "_atomic_write_text_safe"),
)
_FSYNC_DIR = cast("_FsyncDirFn", getattr(_mcp_config_writers, "_fsync_dir"))


class _AtomicWriteFn:
    def __call__(self, path: Path, content: str, *, mode: int = 0o600) -> None: ...


class _FsyncDirFn:
    def __call__(self, path: Path | str) -> None: ...


VerificationStatus = Literal["ok", "mismatch", "missing"]


class PlannedWriteReceipt(TypedDict):
    path: str
    content_hash: str


class ExecutedWriteReceipt(TypedDict):
    path: str
    content_hash: str
    executed: bool
    error: NotRequired[str]


class RollbackReceipt(TypedDict):
    restored: list[str]
    failed: list[str]


class ConfigReceipt(TypedDict):
    planned_writes: list[PlannedWriteReceipt]
    executed_writes: list[ExecutedWriteReceipt]
    backup_path: str
    verification: dict[str, VerificationStatus]
    executed: bool
    rollback: RollbackReceipt | None


class ConfigTransactionError(RuntimeError):
    receipt: ConfigReceipt | None

    def __init__(self, message: str, *, receipt: ConfigReceipt | None = None) -> None:
        super().__init__(message)
        self.receipt = receipt


@dataclass
class _PlannedWrite:
    path: Path
    content: str
    content_hash: str


class ConfigTransaction:
    def __init__(
        self,
        *,
        stale_lock_ms: int = 10000,
        lock_path: Path | None = None,
        backup_root: Path | None = None,
    ) -> None:
        home = Path.home()
        self._lock_path: Path = lock_path or (home / ".omg" / "state" / "config-transaction.lock")
        self._backup_root: Path = backup_root or (home / ".omg" / "backups")
        self._stale_lock_ms: int = stale_lock_ms
        self._planned: list[_PlannedWrite] = []
        self._last_backup_path: str | None = None
        self._last_backup_index: dict[str, str | None] = {}
        self._last_planned_paths: list[str] = []

    def plan(self, target_path: Path | str, content: str) -> None:
        path = Path(target_path).resolve()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self._planned.append(_PlannedWrite(path=path, content=content, content_hash=digest))

    def execute(self) -> ConfigReceipt:
        return self._run(executed=True)

    def dry_run(self) -> ConfigReceipt:
        return self._run(executed=False)

    def rollback(self) -> RollbackReceipt:
        if not self._last_backup_path:
            raise ConfigTransactionError("rollback requested before any backup snapshot")

        restored: list[str] = []
        failed: list[str] = []
        backup_dir = Path(self._last_backup_path)
        for target in self._last_planned_paths:
            backup_file = self._last_backup_index.get(target)
            target_path = Path(target)
            try:
                if backup_file is None:
                    if target_path.exists() or target_path.is_symlink():
                        target_path.unlink()
                        _FSYNC_DIR(target_path.parent)
                    restored.append(target)
                    continue
                source = backup_dir / backup_file
                if not source.exists():
                    failed.append(target)
                    continue
                content = source.read_text(encoding="utf-8")
                _ATOMIC_WRITE_TEXT_SAFE(target_path, content)
                restored.append(target)
            except OSError:
                failed.append(target)
        return {"restored": restored, "failed": failed}

    def list_backups(self) -> list[str]:
        if not self._backup_root.exists():
            return []
        dirs = [path for path in self._backup_root.iterdir() if path.is_dir()]
        dirs.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
        return [str(path) for path in dirs]

    def _run(self, *, executed: bool) -> ConfigReceipt:
        self._acquire_lock()
        try:
            backup_path = self._snapshot_backups()
            receipt: ConfigReceipt = {
                "planned_writes": [
                    {"path": str(item.path), "content_hash": item.content_hash}
                    for item in self._planned
                ],
                "executed_writes": [],
                "backup_path": backup_path,
                "verification": {},
                "executed": executed,
                "rollback": None,
            }

            if executed:
                for item in self._planned:
                    try:
                        _ATOMIC_WRITE_TEXT_SAFE(item.path, item.content)
                        receipt["executed_writes"].append(
                            {
                                "path": str(item.path),
                                "content_hash": item.content_hash,
                                "executed": True,
                            }
                        )
                    except OSError as exc:
                        receipt["executed_writes"].append(
                            {
                                "path": str(item.path),
                                "content_hash": item.content_hash,
                                "executed": False,
                                "error": str(exc),
                            }
                        )
                        rollback_data = self.rollback()
                        receipt["rollback"] = rollback_data
                        raise ConfigTransactionError(str(exc), receipt=receipt) from exc
            else:
                for item in self._planned:
                    receipt["executed_writes"].append(
                        {
                            "path": str(item.path),
                            "content_hash": item.content_hash,
                            "executed": False,
                        }
                    )

            receipt["verification"] = self._verify_written_content()
            return receipt
        finally:
            self._release_lock()

    def _verify_written_content(self) -> dict[str, VerificationStatus]:
        verification: dict[str, VerificationStatus] = {}
        for item in self._planned:
            if not item.path.exists():
                verification[str(item.path)] = "missing"
                continue
            content = item.path.read_text(encoding="utf-8")
            actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            verification[str(item.path)] = "ok" if actual_hash == item.content_hash else "mismatch"
        return verification

    def _snapshot_backups(self) -> str:
        backup_dir = self._new_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=False)

        index: dict[str, str | None] = {}
        planned_paths: list[str] = []
        for idx, item in enumerate(self._planned):
            path_str = str(item.path)
            planned_paths.append(path_str)
            if not item.path.exists():
                index[path_str] = None
                continue
            backup_name = f"{idx:04d}.bak"
            backup_path = backup_dir / backup_name
            original = item.path.read_text(encoding="utf-8")
            _ATOMIC_WRITE_TEXT_SAFE(backup_path, original)
            index[path_str] = backup_name

        self._last_backup_path = str(backup_dir)
        self._last_backup_index = index
        self._last_planned_paths = planned_paths
        return str(backup_dir)

    def _new_backup_dir(self) -> Path:
        self._backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
        base = self._backup_root / f"{stamp}-{os.getpid()}"
        if not base.exists():
            return base
        counter = 1
        while True:
            candidate = self._backup_root / f"{stamp}-{os.getpid()}-{counter}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _acquire_lock(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_lock_if_needed()
        try:
            fd = os.open(str(self._lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ConfigTransactionError(
                f"config transaction lock already held: {self._lock_path}"
            ) from exc
        try:
            ts_ms = int(time.time() * 1000)
            payload = f"{os.getpid()}\n{ts_ms}\n".encode("utf-8")
            written = 0
            while written < len(payload):
                written += os.write(fd, payload[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
        _FSYNC_DIR(self._lock_path.parent)

    def _release_lock(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            return
        _FSYNC_DIR(self._lock_path.parent)

    def _cleanup_stale_lock_if_needed(self) -> None:
        if not self._lock_path.exists():
            return

        try:
            raw = self._lock_path.read_text(encoding="utf-8").splitlines()
            pid = int(raw[0].strip()) if raw else -1
            ts_ms = int(raw[1].strip()) if len(raw) > 1 else 0
        except (OSError, ValueError):
            try:
                self._lock_path.unlink(missing_ok=True)
                _FSYNC_DIR(self._lock_path.parent)
            except OSError:
                pass
            return

        age_ms = int(time.time() * 1000) - ts_ms
        if age_ms <= self._stale_lock_ms:
            return
        if self._pid_is_alive(pid):
            return

        try:
            self._lock_path.unlink(missing_ok=True)
            _FSYNC_DIR(self._lock_path.parent)
        except OSError:
            pass

    def _pid_is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True
