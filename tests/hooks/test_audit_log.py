#!/usr/bin/env python3
"""Tests for secret access audit logging (T21).

TDD: Written BEFORE implementation. All tests should FAIL initially.
Tests the log_secret_access() function and _log_allowlist_bypass() integration.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
HOOKS_DIR = PROJECT_ROOT / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


# ---------------------------------------------------------------------------
# Test 1: Basic — log creates file and writes one valid JSONL entry
# ---------------------------------------------------------------------------
class TestLogCreatesEntry:
    def test_log_creates_file_and_writes_entry(self):
        from secret_audit import log_secret_access

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)
            log_secret_access(
                project_dir=tmpdir,
                tool="Read",
                file_path="config.json",
                decision="allow",
                reason="not a secret",
                allowlisted=False,
            )
            log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
            assert os.path.exists(log_path), "JSONL file must be created"
            with open(log_path) as f:
                entry = json.loads(f.readline())
            assert entry["decision"] == "allow"


# ---------------------------------------------------------------------------
# Test 2: Schema — all required fields present with correct types
# ---------------------------------------------------------------------------
class TestEntrySchema:
    def test_entry_has_all_required_fields(self):
        from secret_audit import log_secret_access

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)
            log_secret_access(
                project_dir=tmpdir,
                tool="Write",
                file_path="app/main.py",
                decision="deny",
                reason="secret file blocked",
                allowlisted=False,
            )
            log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
            with open(log_path) as f:
                entry = json.loads(f.readline())

            # Required fields
            assert "ts" in entry
            assert "tool" in entry
            assert "file" in entry
            assert "decision" in entry
            assert "reason" in entry
            assert "allowlisted" in entry

            # Types
            assert isinstance(entry["ts"], str)
            assert isinstance(entry["tool"], str)
            assert isinstance(entry["file"], str)
            assert entry["decision"] in ("allow", "deny", "ask")
            assert isinstance(entry["reason"], str)
            assert isinstance(entry["allowlisted"], bool)

            # ts is valid ISO8601
            datetime.fromisoformat(entry["ts"])

    def test_entry_values_match_input(self):
        from secret_audit import log_secret_access

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)
            log_secret_access(
                project_dir=tmpdir,
                tool="Edit",
                file_path="src/utils.ts",
                decision="ask",
                reason="needs review",
                allowlisted=True,
            )
            log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
            with open(log_path) as f:
                entry = json.loads(f.readline())

            assert entry["tool"] == "Edit"
            assert entry["file"] == "src/utils.ts"
            assert entry["decision"] == "ask"
            assert entry["reason"] == "needs review"
            assert entry["allowlisted"] is True


# ---------------------------------------------------------------------------
# Test 3: Secret path masking — sensitive paths redacted
# ---------------------------------------------------------------------------
class TestSecretPathMasking:
    @pytest.mark.parametrize("secret_path", [
        ".env",
        ".env.local",
        "config/.env.production",
        "keys/server.pem",
        "certs/tls.key",
        "secrets/api-tokens.json",
        ".aws/credentials",
        ".ssh/id_rsa",
        "credentials.json",
        "passwords.txt",
        "tokens.yaml",
        "server.p12",
    ])
    def test_secret_paths_are_redacted(self, secret_path):
        from secret_audit import mask_secret_path

        result = mask_secret_path(secret_path)
        assert result == "[REDACTED]", f"Expected [REDACTED] for {secret_path}, got {result}"

    @pytest.mark.parametrize("safe_path", [
        "config.json",
        "src/main.py",
        "README.md",
        "package.json",
        ".env.example",
        ".env.sample",
        ".env.template",
        "app/routes/index.ts",
    ])
    def test_non_secret_paths_not_masked(self, safe_path):
        from secret_audit import mask_secret_path

        result = mask_secret_path(safe_path)
        assert result == safe_path, f"Expected {safe_path} to NOT be redacted, got {result}"

    def test_redacted_path_in_log_entry(self):
        from secret_audit import log_secret_access

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)
            log_secret_access(
                project_dir=tmpdir,
                tool="Read",
                file_path=".env.local",
                decision="deny",
                reason="secret file blocked",
                allowlisted=False,
            )
            log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
            with open(log_path) as f:
                entry = json.loads(f.readline())

            assert entry["file"] == "[REDACTED]", "Secret path should be redacted in log entry"


# ---------------------------------------------------------------------------
# Test 4: 5MB rotation — file rotated when exceeding 5MB
# ---------------------------------------------------------------------------
class TestRotation:
    def test_rotation_at_5mb(self):
        from secret_audit import log_secret_access, SECRET_ACCESS_MAX_BYTES

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = os.path.join(tmpdir, ".omg", "state", "ledger")
            os.makedirs(ledger_dir, exist_ok=True)
            log_path = os.path.join(ledger_dir, "secret-access.jsonl")

            # Write a file just over 5MB
            with open(log_path, "w") as f:
                f.write("x" * (SECRET_ACCESS_MAX_BYTES + 1))

            # Trigger rotation by logging
            log_secret_access(
                project_dir=tmpdir,
                tool="Read",
                file_path="test.py",
                decision="allow",
                reason="ok",
                allowlisted=False,
            )

            # Old file should be archived
            archive_path = log_path + ".1"
            assert os.path.exists(archive_path), "Archive .1 should exist after rotation"
            # New log should contain only the new entry
            with open(log_path) as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 1, "Rotated log should have only the new entry"

    def test_old_archive_replaced(self):
        from secret_audit import log_secret_access, SECRET_ACCESS_MAX_BYTES

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = os.path.join(tmpdir, ".omg", "state", "ledger")
            os.makedirs(ledger_dir, exist_ok=True)
            log_path = os.path.join(ledger_dir, "secret-access.jsonl")
            archive_path = log_path + ".1"

            # Create an existing archive
            with open(archive_path, "w") as f:
                f.write("old-archive-content\n")

            # Write main file over 5MB
            with open(log_path, "w") as f:
                f.write("x" * (SECRET_ACCESS_MAX_BYTES + 1))

            log_secret_access(
                project_dir=tmpdir,
                tool="Read",
                file_path="test.py",
                decision="allow",
                reason="ok",
                allowlisted=False,
            )

            # Old archive should be replaced
            with open(archive_path) as f:
                content = f.read()
            assert "old-archive-content" not in content, "Old archive should be replaced"


# ---------------------------------------------------------------------------
# Test 5: Multiple entries appended
# ---------------------------------------------------------------------------
class TestMultipleEntries:
    def test_multiple_entries_appended(self):
        from secret_audit import log_secret_access

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)

            for i in range(3):
                log_secret_access(
                    project_dir=tmpdir,
                    tool="Read",
                    file_path=f"file{i}.py",
                    decision="allow",
                    reason=f"reason {i}",
                    allowlisted=False,
                )

            log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
            with open(log_path) as f:
                lines = [l.strip() for l in f if l.strip()]

            assert len(lines) == 3, f"Expected 3 entries, got {len(lines)}"
            for i, line in enumerate(lines):
                entry = json.loads(line)
                assert entry["file"] == f"file{i}.py"


# ---------------------------------------------------------------------------
# Test 6: Directory auto-creation
# ---------------------------------------------------------------------------
class TestDirectoryCreation:
    def test_creates_ledger_directory_if_missing(self):
        from secret_audit import log_secret_access

        with tempfile.TemporaryDirectory() as tmpdir:
            # Do NOT pre-create .omg/state/ledger
            log_secret_access(
                project_dir=tmpdir,
                tool="Read",
                file_path="test.py",
                decision="allow",
                reason="ok",
                allowlisted=False,
            )
            log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
            assert os.path.exists(log_path), "Should create directory and file automatically"


# ---------------------------------------------------------------------------
# Test 7: _log_allowlist_bypass integration
# ---------------------------------------------------------------------------
class TestAllowlistBypassLogging:
    def test_log_allowlist_bypass_writes_entry(self):
        from policy_engine import _log_allowlist_bypass

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".omg", "state", "ledger"), exist_ok=True)
            # Set project dir so _log_allowlist_bypass can find it
            old_env = os.environ.get("CLAUDE_PROJECT_DIR")
            os.environ["CLAUDE_PROJECT_DIR"] = tmpdir
            try:
                _log_allowlist_bypass("config/.env", "Read", "allowlisted by policy")

                log_path = os.path.join(tmpdir, ".omg", "state", "ledger", "secret-access.jsonl")
                assert os.path.exists(log_path), "Allowlist bypass should write audit log"
                with open(log_path) as f:
                    entry = json.loads(f.readline())

                assert entry["decision"] == "allow"
                assert entry["allowlisted"] is True
                assert "allowlisted by policy" in entry["reason"]
            finally:
                if old_env is not None:
                    os.environ["CLAUDE_PROJECT_DIR"] = old_env
                elif "CLAUDE_PROJECT_DIR" in os.environ:
                    del os.environ["CLAUDE_PROJECT_DIR"]


# ---------------------------------------------------------------------------
# Test 8: Resilience — errors don't propagate
# ---------------------------------------------------------------------------
class TestResilience:
    def test_log_does_not_raise_on_unwritable_dir(self):
        from secret_audit import log_secret_access

        # Pass a path that can't be created (null byte)
        # The function should silently fail, not raise
        try:
            log_secret_access(
                project_dir="/nonexistent/path/that/does/not/exist",
                tool="Read",
                file_path="test.py",
                decision="allow",
                reason="ok",
                allowlisted=False,
            )
        except Exception:
            pytest.fail("log_secret_access should not raise exceptions")
