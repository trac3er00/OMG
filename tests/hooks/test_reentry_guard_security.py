#!/usr/bin/env python3
"""Security tests for hook_reentry_guard in hooks/_common.py.

Tests verify:
1. Issue #1: os.O_NOFOLLOW flag prevents symlink following attacks
2. Issue #2: Exception handling doesn't cause RuntimeError on caller exceptions
"""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

# Add hooks to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import hook_reentry_guard


def test_hook_reentry_guard_prevents_symlink_following():
    """Test that hook_reentry_guard uses O_NOFOLLOW to prevent symlink attacks."""
    old_val = os.environ.get("CLAUDE_PROJECT_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        try:
            lock_dir = os.path.join(tmpdir, ".omg", "state", "ledger")
            os.makedirs(lock_dir, exist_ok=True)
            lock_file = os.path.join(lock_dir, ".test-hook.reentry.lock")
            target_file = os.path.join(tmpdir, "sensitive-file.txt")

            # Create a sensitive file
            with open(target_file, "w") as f:
                f.write("sensitive data")

            # Create a symlink at the lock file path pointing to the sensitive file
            os.symlink(target_file, lock_file)

            # Try to acquire the lock - should fail-open (yield True) due to O_NOFOLLOW
            # and NOT overwrite the sensitive file
            with hook_reentry_guard("test-hook") as acquired:
                # Should fail-open (True) rather than following the symlink
                assert acquired is True

            # Verify sensitive file was NOT modified
            with open(target_file, "r") as f:
                content = f.read()
            assert content == "sensitive data", f"Sensitive file was modified: {content}"

            # Verify symlink still exists (wasn't replaced)
            assert os.path.islink(lock_file), "Symlink should still exist"
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_val


def test_hook_reentry_guard_handles_caller_exceptions():
    """Test that exceptions raised by the caller don't cause RuntimeError."""
    old_val = os.environ.get("CLAUDE_PROJECT_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        try:
            # Test that we can raise an exception inside the context without causing
            # "RuntimeError: generator already yielded"
            try:
                with hook_reentry_guard("test-hook") as acquired:
                    assert acquired is True
                    raise ValueError("Simulated caller exception")
            except ValueError as e:
                # This should be the exception we raised, not a RuntimeError
                assert str(e) == "Simulated caller exception"
            except RuntimeError as e:
                # If we get here, the fix didn't work
                if "generator" in str(e).lower():
                    raise AssertionError(
                        f"Got RuntimeError from contextmanager: {e}. "
                        "This indicates the yield is still inside try/except."
                    )
                raise
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_val


def test_hook_reentry_guard_concurrent_access():
    """Test that concurrent access to the same hook is properly blocked."""
    old_val = os.environ.get("CLAUDE_PROJECT_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        try:
            results = {"first": None, "second": None}
            first_acquired = threading.Event()
            second_can_check = threading.Event()

            def first_thread():
                with hook_reentry_guard("concurrent-test") as acquired:
                    results["first"] = acquired
                    first_acquired.set()
                    # Hold the lock; assert the wait succeeded so we don't
                    # release early before the second thread checks
                    waited = second_can_check.wait(timeout=2)
                    assert waited, "Timed out waiting for second thread to signal"

            def second_thread():
                # Wait for first thread to acquire; assert so we don't
                # proceed without confirmation the first thread holds the lock
                waited = first_acquired.wait(timeout=2)
                assert waited, "Timed out waiting for first thread to acquire lock"
                with hook_reentry_guard("concurrent-test") as acquired:
                    results["second"] = acquired
                second_can_check.set()

            t1 = threading.Thread(target=first_thread)
            t2 = threading.Thread(target=second_thread)

            t1.start()
            t2.start()

            t1.join(timeout=3)
            t2.join(timeout=3)

            # First thread should acquire the lock
            assert results["first"] is True, "First thread should acquire lock"
            # Second thread should be told to skip (False)
            assert results["second"] is False, "Second thread should be told to skip"
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_val


def test_hook_reentry_guard_fail_open_behavior():
    """Test that the guard fails open (yields True) on unexpected errors."""
    old_val = os.environ.get("CLAUDE_PROJECT_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        try:
            # Create a read-only lock directory to trigger an error
            lock_dir = os.path.join(tmpdir, ".omg", "state", "ledger")
            os.makedirs(lock_dir, exist_ok=True)

            # Make the directory read-only to cause os.open to fail
            os.chmod(lock_dir, 0o444)

            try:
                # Should fail-open (yield True) rather than crashing
                with hook_reentry_guard("test-hook") as acquired:
                    assert acquired is True, "Should fail-open (True) on error"
            finally:
                # Restore permissions for cleanup
                os.chmod(lock_dir, 0o755)
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_val


def test_hook_reentry_guard_writes_diagnostics():
    """Test that the guard writes PID and timestamp when lock is acquired."""
    old_val = os.environ.get("CLAUDE_PROJECT_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
        try:
            with hook_reentry_guard("diag-test") as acquired:
                assert acquired is True

                # Check that diagnostics were written
                lock_file = os.path.join(tmpdir, ".omg", "state", "ledger", ".diag-test.reentry.lock")
                assert os.path.exists(lock_file), "Lock file should exist"

                with open(lock_file, "r") as f:
                    data = json.load(f)

                assert "pid" in data, "Diagnostics should include PID"
                assert "ts" in data, "Diagnostics should include timestamp"
                assert data["pid"] == os.getpid(), "PID should match current process"
                assert isinstance(data["ts"], (int, float)), "Timestamp should be numeric"
        finally:
            if old_val is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_val


if __name__ == "__main__":
    # Run tests manually if pytest not available
    test_hook_reentry_guard_prevents_symlink_following()
    print("✓ test_hook_reentry_guard_prevents_symlink_following passed")

    test_hook_reentry_guard_handles_caller_exceptions()
    print("✓ test_hook_reentry_guard_handles_caller_exceptions passed")

    test_hook_reentry_guard_concurrent_access()
    print("✓ test_hook_reentry_guard_concurrent_access passed")

    test_hook_reentry_guard_fail_open_behavior()
    print("✓ test_hook_reentry_guard_fail_open_behavior passed")

    test_hook_reentry_guard_writes_diagnostics()
    print("✓ test_hook_reentry_guard_writes_diagnostics passed")

    print("\nAll security tests passed!")
