#!/usr/bin/env python3
"""Tests for protected context registry (PreCompact hook extension).

Tests .claude-context-protect file parsing, default protections,
entry classification (file/regex/literal), and context re-injection.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure hooks directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "hooks"))


class TestProtectedContextFileHonored:
    """Entries in .claude-context-protect are re-injected."""

    def test_protected_context_file_honored(self):
        """File entries listed in .claude-context-protect are collected as protected context."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file to protect
            Path(tmpdir, "important.md").write_text("Critical instructions here")

            # Create .claude-context-protect referencing that file
            Path(tmpdir, ".claude-context-protect").write_text("important.md\n")

            result = collect_protected_context(tmpdir)
            assert "Critical instructions here" in result

    def test_multiple_entries_honored(self):
        """Multiple entries in protect file are all collected."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.txt").write_text("File A content")
            Path(tmpdir, "b.txt").write_text("File B content")
            Path(tmpdir, ".claude-context-protect").write_text("a.txt\nb.txt\n")

            result = collect_protected_context(tmpdir)
            assert "File A content" in result
            assert "File B content" in result


class TestDefaultProtectionsApplied:
    """CLAUDE.md protected when no .claude-context-protect exists."""

    def test_default_protections_applied(self):
        """CLAUDE.md content is protected by default when no protect file exists."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create CLAUDE.md but NO .claude-context-protect
            Path(tmpdir, "CLAUDE.md").write_text(
                "# Project Guidelines\nAlways test first."
            )

            result = collect_protected_context(tmpdir, context_text="some context")
            assert "Project Guidelines" in result
            assert "Always test first" in result

    def test_default_task_definitions_protected(self):
        """Active task definitions (## Task: or - [ ]) are protected by default."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            context = (
                "Random preamble\n"
                "## Task: Build auth module\n"
                "Some details\n"
                "- [ ] Write tests\n"
                "- [x] Already done"
            )
            result = collect_protected_context(tmpdir, context_text=context)
            assert "## Task: Build auth module" in result
            assert "- [ ] Write tests" in result

    def test_default_error_messages_protected(self):
        """Recent error messages (Error:, Exception:, FAILED) are protected by default."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            context = (
                "All good here\n"
                "Error: connection refused\n"
                "More stuff\n"
                "Exception: KeyError 'name'\n"
                "FAILED test_auth.py::test_login"
            )
            result = collect_protected_context(tmpdir, context_text=context)
            assert "Error: connection refused" in result
            assert "Exception: KeyError" in result
            assert "FAILED test_auth" in result


class TestFilePathEntryReadsFile:
    """File path entries read the file content."""

    def test_file_path_entry_reads_file(self):
        """File path entries read and include full file content."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "config.yaml").write_text("setting: value\nmode: debug")
            Path(tmpdir, ".claude-context-protect").write_text("config.yaml\n")

            result = collect_protected_context(tmpdir)
            assert "setting: value" in result
            assert "mode: debug" in result

    def test_nonexistent_file_path_skipped(self):
        """File paths that don't exist are not treated as file entries."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            # Entry looks like a path but file doesn't exist → falls to regex/literal
            Path(tmpdir, ".claude-context-protect").write_text("nonexistent.txt\n")
            context = "line with nonexistent.txt reference"

            result = collect_protected_context(tmpdir, context_text=context)
            # Should try as literal match since file doesn't exist
            assert "nonexistent.txt" in result


class TestRegexPatternEntryMatches:
    """Regex patterns match context lines."""

    def test_regex_pattern_entry_matches(self):
        """Regex patterns match and protect matching context lines."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".claude-context-protect").write_text("^## Task:.*\n")

            context = (
                "Some preamble\n"
                "## Task: Build the thing\n"
                "Other stuff\n"
                "## Task: Test it"
            )
            result = collect_protected_context(tmpdir, context_text=context)
            assert "## Task: Build the thing" in result
            assert "## Task: Test it" in result
            assert "Some preamble" not in result

    def test_regex_anchored_pattern(self):
        """Anchored regex (^/$) works correctly."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".claude-context-protect").write_text("^Error:.*$\n")

            context = "normal line\nError: something broke\nno error here"
            result = collect_protected_context(tmpdir, context_text=context)
            assert "Error: something broke" in result
            assert "normal line" not in result
            assert "no error here" not in result


class TestLiteralStringEntryMatches:
    """Literal strings match exactly."""

    def test_literal_string_entry_matches(self):
        """Literal strings match lines containing the exact string."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".claude-context-protect").write_text("IMPORTANT_NOTE\n")

            context = "line 1\nThis has IMPORTANT_NOTE inside\nline 3"
            result = collect_protected_context(tmpdir, context_text=context)
            assert "IMPORTANT_NOTE" in result
            assert "line 1" not in result
            assert "line 3" not in result


class TestMissingProtectFileNoCrash:
    """Graceful when .claude-context-protect missing."""

    def test_missing_protect_file_no_crash(self):
        """No crash when .claude-context-protect doesn't exist and no CLAUDE.md."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            # No .claude-context-protect, no CLAUDE.md, no special context
            result = collect_protected_context(tmpdir, context_text="just some context")
            # Should not crash, result should be a string (possibly empty)
            assert isinstance(result, str)

    def test_empty_protect_file_no_crash(self):
        """No crash when .claude-context-protect exists but is empty."""
        from _protected_context import collect_protected_context

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".claude-context-protect").write_text("")

            result = collect_protected_context(tmpdir, context_text="some context")
            assert isinstance(result, str)

    def test_comments_and_blanks_ignored(self):
        """Comments (#) and blank lines in protect file are ignored."""
        from _protected_context import load_protect_entries

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".claude-context-protect").write_text(
                "# This is a comment\n"
                "\n"
                "real_entry\n"
                "  \n"
                "# Another comment\n"
                "another_entry\n"
            )

            entries = load_protect_entries(tmpdir)
            assert entries is not None
            assert len(entries) == 2
            assert "real_entry" in entries
            assert "another_entry" in entries
