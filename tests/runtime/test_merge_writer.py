"""Tests for merge-writer lock — one authorized writer, many concurrent readers (Task 4)."""
from __future__ import annotations

import json
import os
import sys
import threading
import time

import pytest

# --- Path setup ---
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from runtime.merge_writer import (
    MergeWriter,
    MergeWriterAuthorizationError,
    MergeWriterToken,
    WriteLease,
    create_write_lease,
    get_merge_writer,
    is_lease_valid,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mw(tmp_path: object) -> MergeWriter:
    """Return a MergeWriter rooted in a temporary directory."""
    return MergeWriter(str(tmp_path))


@pytest.fixture
def lock_dir(tmp_path: object) -> str:
    """Return .omg/state inside tmp_path (created on demand by MergeWriter)."""
    return str(tmp_path)  # type: ignore[arg-type]


# =============================================================================
# Test: Lock Acquisition and Release with Provenance
# =============================================================================


class TestAcquireRelease:
    """Test lock acquisition, release, and provenance artifact creation."""

    def test_acquire_returns_token(self, mw: MergeWriter) -> None:
        """acquire() returns a MergeWriterToken with correct fields."""
        token = mw.acquire("run-1", reason="test merge")

        assert isinstance(token, MergeWriterToken)
        assert token.run_id == "run-1"
        assert token.acquired_at
        assert "merge-writer.lock" in token.lock_path
        assert "merge-writer-run-1.json" in token.provenance_path

    def test_acquire_creates_lock_file(self, mw: MergeWriter) -> None:
        """acquire() writes a JSON lock file on disk."""
        mw.acquire("run-2", reason="create lock")

        lock_path = mw._lock_path()
        assert lock_path.exists()

        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-2"
        assert data["reason"] == "create lock"
        assert "acquired_at" in data
        assert "pid" in data

    def test_release_removes_lock_file(self, mw: MergeWriter) -> None:
        """release() removes the lock file and writes provenance."""
        token = mw.acquire("run-3", reason="release test")
        provenance = mw.release(token)

        assert not mw._lock_path().exists()
        assert provenance["schema"] == "MergeWriterProvenance"
        assert provenance["run_id"] == "run-3"
        assert provenance["released_at"]

    def test_release_writes_provenance_to_disk(self, mw: MergeWriter) -> None:
        """Provenance artifact exists at .omg/evidence/merge-writer-<run_id>.json."""
        token = mw.acquire("run-4", reason="provenance check")
        mw.release(token)

        prov_path = mw._provenance_path("run-4")
        assert prov_path.exists()

        data = json.loads(prov_path.read_text(encoding="utf-8"))
        assert data["schema"] == "MergeWriterProvenance"
        assert data["run_id"] == "run-4"
        assert data["acquired_at"] == token.acquired_at
        assert data["released_at"]
        assert data["reason"] == "provenance check"

    def test_reacquire_same_run_id_ok(self, mw: MergeWriter) -> None:
        """Re-acquiring with the same run_id succeeds (idempotent)."""
        token1 = mw.acquire("run-5")
        token2 = mw.acquire("run-5")

        assert token2.run_id == "run-5"
        # Clean up
        mw.release(token2)

    def test_release_wrong_run_id_raises(self, mw: MergeWriter) -> None:
        """release() with a mismatched token raises MergeWriterAuthorizationError."""
        token = mw.acquire("run-owner")

        fake_token = MergeWriterToken(
            run_id="run-imposter",
            acquired_at=token.acquired_at,
            lock_path=token.lock_path,
            provenance_path=token.provenance_path,
        )

        with pytest.raises(MergeWriterAuthorizationError, match="not held by this run_id"):
            mw.release(fake_token)


# =============================================================================
# Test: Lock File Format
# =============================================================================


class TestLockFileFormat:
    """Verify the lock file format matches the spec."""

    def test_lock_file_is_json_with_required_keys(self, mw: MergeWriter) -> None:
        """Lock file must contain run_id, acquired_at, reason, pid."""
        mw.acquire("fmt-run", reason="format check")

        data = json.loads(mw._lock_path().read_text(encoding="utf-8"))
        assert set(data.keys()) == {"run_id", "acquired_at", "reason", "pid"}
        assert data["run_id"] == "fmt-run"
        assert data["reason"] == "format check"
        assert isinstance(data["pid"], int)
        assert data["acquired_at"]  # non-empty ISO string

    def test_lock_file_pid_matches_current_process(self, mw: MergeWriter) -> None:
        """pid in lock file equals os.getpid() of the acquirer."""
        mw.acquire("pid-run")

        data = json.loads(mw._lock_path().read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()


# =============================================================================
# Test: is_locked / get_current_owner / check_authorization
# =============================================================================


class TestLockState:
    """Test lock query methods."""

    def test_not_locked_initially(self, mw: MergeWriter) -> None:
        assert mw.is_locked() is False
        assert mw.get_current_owner() is None
        assert mw.check_authorization("any-run") is False

    def test_is_locked_after_acquire(self, mw: MergeWriter) -> None:
        mw.acquire("locked-run")
        assert mw.is_locked() is True

    def test_not_locked_after_release(self, mw: MergeWriter) -> None:
        token = mw.acquire("temp-run")
        mw.release(token)
        assert mw.is_locked() is False

    def test_get_current_owner(self, mw: MergeWriter) -> None:
        mw.acquire("owner-run")
        assert mw.get_current_owner() == "owner-run"

    def test_check_authorization_true(self, mw: MergeWriter) -> None:
        mw.acquire("auth-run")
        assert mw.check_authorization("auth-run") is True

    def test_check_authorization_false_for_other(self, mw: MergeWriter) -> None:
        mw.acquire("auth-run")
        assert mw.check_authorization("other-run") is False


# =============================================================================
# Test: Unauthorized Mutation Blocked with Governance Reason
# =============================================================================


class TestUnauthorizedMutationBlocked:
    """Verify that unauthorized mutation attempts raise with governance reason."""

    def test_mutation_without_lock_raises(self, mw: MergeWriter) -> None:
        """Worktree worker trying to mutate without holding the lock is blocked."""
        with pytest.raises(MergeWriterAuthorizationError, match="requires merge-writer lock") as exc_info:
            mw.require_authorization("rogue-run", mutation_type="merge", isolation="worktree")

        assert exc_info.value.run_id == "rogue-run"
        assert "requires merge-writer lock" in exc_info.value.reason

    def test_mutation_by_wrong_owner_raises(self, mw: MergeWriter) -> None:
        """Worker with a different run_id than the lock holder is blocked."""
        mw.acquire("real-owner")

        with pytest.raises(MergeWriterAuthorizationError, match="denied") as exc_info:
            mw.require_authorization("imposter", mutation_type="merge", isolation="worktree")

        assert exc_info.value.run_id == "imposter"
        assert "real-owner" in exc_info.value.reason

    def test_mutation_by_lock_holder_passes(self, mw: MergeWriter) -> None:
        """Authorized holder can mutate without exception."""
        mw.acquire("legit-run")
        # Should NOT raise
        mw.require_authorization("legit-run", mutation_type="merge", isolation="worktree")

    def test_read_only_worker_skips_lock_check(self, mw: MergeWriter) -> None:
        """Workers with isolation='none' bypass the merge-writer check entirely."""
        # Lock is NOT held — read-only should still pass
        mw.require_authorization("reader-run", mutation_type="read", isolation="none")

    def test_read_only_container_worker_skips_lock(self, mw: MergeWriter) -> None:
        """Container-isolated workers (deferred/read-only) skip lock check."""
        mw.require_authorization("container-run", mutation_type="read", isolation="container")

    def test_governance_reason_includes_mutation_type(self, mw: MergeWriter) -> None:
        """The error message includes the mutation_type for audit clarity."""
        with pytest.raises(MergeWriterAuthorizationError, match="mutation_type=apply"):
            mw.require_authorization("bad-run", mutation_type="apply", isolation="worktree")


# =============================================================================
# Test: Concurrent Read-Only Workers with One Writer
# =============================================================================


class TestConcurrentReadersOneWriter:
    """Verify many readers can run while one writer holds the lock."""

    def test_readers_run_concurrently_while_writer_merges(self, mw: MergeWriter) -> None:
        """Multiple read-only stubs proceed while one writer holds the lock."""
        results: dict[str, str] = {}
        barrier = threading.Barrier(4, timeout=5)  # 3 readers + 1 writer

        def reader_work(reader_id: str) -> None:
            barrier.wait()
            try:
                mw.require_authorization(reader_id, isolation="none")
                results[reader_id] = "ok"
            except MergeWriterAuthorizationError:
                results[reader_id] = "blocked"

        def writer_work() -> None:
            barrier.wait()
            try:
                mw.require_authorization("writer-run", isolation="worktree")
                results["writer-run"] = "ok"
            except MergeWriterAuthorizationError:
                results["writer-run"] = "blocked"

        # Acquire lock for the writer
        token = mw.acquire("writer-run", reason="concurrent test")

        threads = [
            threading.Thread(target=reader_work, args=(f"reader-{i}",))
            for i in range(3)
        ]
        threads.append(threading.Thread(target=writer_work))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All readers pass, writer passes (it's the lock holder)
        assert results.get("reader-0") == "ok"
        assert results.get("reader-1") == "ok"
        assert results.get("reader-2") == "ok"
        assert results.get("writer-run") == "ok"

        mw.release(token)

    def test_second_writer_blocked(self, mw: MergeWriter) -> None:
        """A second writer cannot acquire the lock while the first holds it."""
        mw.acquire("writer-1")

        with pytest.raises(MergeWriterAuthorizationError, match="already held"):
            mw.acquire("writer-2")


# =============================================================================
# Test: Factory Function
# =============================================================================


class TestFactory:
    """Test get_merge_writer() factory."""

    def test_factory_returns_instance(self, tmp_path: object) -> None:
        mw = get_merge_writer(str(tmp_path))
        assert isinstance(mw, MergeWriter)

    def test_factory_default_project_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        mw = get_merge_writer()
        assert isinstance(mw, MergeWriter)


# =============================================================================
# Test: Write Lease — run-scoped, time-bounded authorization
# =============================================================================


class TestWriteLeaseCreation:
    """Test WriteLease dataclass and create_write_lease factory."""

    def test_create_write_lease_returns_dataclass(self) -> None:
        lease = create_write_lease("run-1", 300.0, ".omg/evidence/merge-writer-run-1.json")
        assert isinstance(lease, WriteLease)
        assert lease.run_id == "run-1"
        assert lease.duration_s == 300.0
        assert lease.evidence_path == ".omg/evidence/merge-writer-run-1.json"
        assert lease.is_active is True

    def test_create_write_lease_records_monotonic_time(self) -> None:
        before = time.monotonic()
        lease = create_write_lease("run-2", 60.0, "evidence.json")
        after = time.monotonic()
        assert before <= lease.created_at <= after

    def test_write_lease_is_frozen(self) -> None:
        lease = create_write_lease("run-3", 60.0, "evidence.json")
        with pytest.raises(AttributeError):
            lease.run_id = "other"  # type: ignore[misc]


class TestWriteLeaseValidation:
    """Test is_lease_valid with valid, expired, and cross-run scenarios."""

    def test_valid_lease_authorizes_active_run(self) -> None:
        """A fresh lease for the correct run_id returns (True, 'valid')."""
        lease = create_write_lease("run-active", 300.0, ".omg/evidence/e.json")
        valid, reason = is_lease_valid(lease, "run-active")
        assert valid is True
        assert reason == "valid"

    def test_expired_lease_fails_deterministically(self) -> None:
        """A lease past its duration returns (False, 'write_lease_expired:...')."""
        lease = create_write_lease("run-exp", 10.0, "evidence.json")
        # Simulate time passing beyond duration
        future_time = lease.created_at + 11.0
        valid, reason = is_lease_valid(lease, "run-exp", current_time=future_time)
        assert valid is False
        assert reason.startswith("write_lease_expired:")
        assert "elapsed=11.0s" in reason
        assert "limit=10.0s" in reason

    def test_cross_run_lease_fails_deterministically(self) -> None:
        """A lease from a different run_id returns (False, 'write_lease_run_id_mismatch:...')."""
        lease = create_write_lease("run-old", 300.0, "evidence.json")
        valid, reason = is_lease_valid(lease, "run-new")
        assert valid is False
        assert reason.startswith("write_lease_run_id_mismatch:")
        assert "run-old" in reason
        assert "run-new" in reason

    def test_inactive_lease_fails(self) -> None:
        """An explicitly deactivated lease returns (False, 'write_lease_inactive')."""
        lease = WriteLease(
            run_id="run-x",
            created_at=time.monotonic(),
            duration_s=300.0,
            evidence_path="evidence.json",
            is_active=False,
        )
        valid, reason = is_lease_valid(lease, "run-x")
        assert valid is False
        assert reason == "write_lease_inactive"

    def test_missing_evidence_path_fails(self) -> None:
        """A lease with empty evidence_path returns (False, 'write_lease_missing_evidence_path')."""
        lease = WriteLease(
            run_id="run-y",
            created_at=time.monotonic(),
            duration_s=300.0,
            evidence_path="",
            is_active=True,
        )
        valid, reason = is_lease_valid(lease, "run-y")
        assert valid is False
        assert reason == "write_lease_missing_evidence_path"

    def test_lease_at_exact_boundary_is_still_valid(self) -> None:
        """A lease at exactly its duration boundary is still valid."""
        lease = create_write_lease("run-edge", 60.0, "evidence.json")
        boundary_time = lease.created_at + 60.0
        valid, _reason = is_lease_valid(lease, "run-edge", current_time=boundary_time)
        assert valid is True

    def test_lease_just_past_boundary_is_expired(self) -> None:
        """A lease 0.1s past its duration boundary is expired."""
        lease = create_write_lease("run-edge", 60.0, "evidence.json")
        past_time = lease.created_at + 60.1
        valid, reason = is_lease_valid(lease, "run-edge", current_time=past_time)
        assert valid is False
        assert "write_lease_expired" in reason
