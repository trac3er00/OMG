"""Tests for fsync-safe atomic write primitives.

Verifies the durability contract: write -> fsync(fd) -> rename -> fsync(dir).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from runtime.mcp_config_writers import (
    _atomic_write_text,
    _atomic_write_text_safe,
    _fsync_dir,
    _write_json,
)


# ---------------------------------------------------------------------------
# _fsync_dir helper
# ---------------------------------------------------------------------------


class TestFsyncDir:
    def test_fsync_dir_opens_and_syncs_directory(self, tmp_path: Path) -> None:
        """_fsync_dir must os.open(dir, O_RDONLY), os.fsync(fd), os.close(fd)."""
        with patch("runtime.mcp_config_writers.os.open", return_value=42) as m_open, \
             patch("runtime.mcp_config_writers.os.fsync") as m_fsync, \
             patch("runtime.mcp_config_writers.os.close") as m_close:
            _fsync_dir(tmp_path)
            m_open.assert_called_once_with(str(tmp_path), os.O_RDONLY)
            m_fsync.assert_called_once_with(42)
            m_close.assert_called_once_with(42)

    def test_fsync_dir_closes_fd_on_fsync_failure(self, tmp_path: Path) -> None:
        """fd must be closed even if os.fsync raises."""
        with patch("runtime.mcp_config_writers.os.open", return_value=42), \
             patch("runtime.mcp_config_writers.os.fsync", side_effect=OSError("disk error")), \
             patch("runtime.mcp_config_writers.os.close") as m_close:
            with pytest.raises(OSError, match="disk error"):
                _fsync_dir(tmp_path)
            m_close.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# _atomic_write_text_safe — fsync ordering
# ---------------------------------------------------------------------------


class TestAtomicWriteTextSafeFsync:
    def test_fsync_called_on_fd_before_replace(self, tmp_path: Path) -> None:
        """os.fsync(fd) must happen BEFORE os.replace()."""
        target = tmp_path / "config.json"
        call_order: list[str] = []

        orig_fsync = os.fsync
        orig_replace = os.replace
        orig_open = os.open
        orig_write = os.write
        orig_close = os.close

        def tracking_open(path, flags, *args, **kwargs):
            fd = orig_open(path, flags, *args, **kwargs)
            return fd

        def tracking_fsync(fd):
            call_order.append(f"fsync:{fd}")
            orig_fsync(fd)

        def tracking_replace(src, dst):
            call_order.append("replace")
            orig_replace(src, dst)

        with patch("runtime.mcp_config_writers.os.fsync", side_effect=tracking_fsync), \
             patch("runtime.mcp_config_writers.os.replace", side_effect=tracking_replace):
            _atomic_write_text_safe(target, "hello\n")

        # There should be at least one fsync before replace
        replace_idx = call_order.index("replace")
        fsync_indices = [i for i, v in enumerate(call_order) if v.startswith("fsync:")]
        assert any(i < replace_idx for i in fsync_indices), (
            f"fsync must precede replace. Order: {call_order}"
        )

    def test_fsync_called_on_dir_after_replace(self, tmp_path: Path) -> None:
        """os.fsync() on directory fd must happen AFTER os.replace()."""
        target = tmp_path / "config.json"
        call_order: list[str] = []

        orig_open = os.open
        real_replace = os.replace

        def tracking_fsync(fd):
            call_order.append(f"fsync:{fd}")

        def tracking_open(path, flags, *args, **kwargs):
            fd = orig_open(path, flags, *args, **kwargs)
            if flags == os.O_RDONLY and str(path) == str(tmp_path):
                call_order.append(f"open_dir:{fd}")
            return fd

        replace_called = False

        def mock_replace(src, dst):
            nonlocal replace_called
            call_order.append("replace")
            replace_called = True
            real_replace(src, dst)

        with patch("runtime.mcp_config_writers.os.replace", side_effect=mock_replace), \
             patch("runtime.mcp_config_writers.os.fsync", side_effect=tracking_fsync), \
             patch("runtime.mcp_config_writers.os.open", side_effect=tracking_open), \
             patch("runtime.mcp_config_writers.os.close"):
            _atomic_write_text_safe(target, "hello\n")

        assert replace_called, "os.replace was never called"
        replace_idx = call_order.index("replace")
        # There should be a dir open + fsync AFTER replace
        dir_events_after = [
            v for i, v in enumerate(call_order)
            if i > replace_idx and (v.startswith("open_dir:") or v.startswith("fsync:"))
        ]
        assert len(dir_events_after) >= 1, (
            f"Expected dir fsync after replace. Order: {call_order}"
        )


# ---------------------------------------------------------------------------
# _atomic_write_text_safe — symlink rejection
# ---------------------------------------------------------------------------


class TestAtomicWriteTextSafeSymlink:
    def test_rejects_symlink_target(self, tmp_path: Path) -> None:
        """Writing to a path that is a symlink must raise OSError."""
        real_file = tmp_path / "real.json"
        real_file.write_text("{}")
        link_path = tmp_path / "link.json"
        link_path.symlink_to(real_file)

        with pytest.raises(OSError, match="[Ss]ymlink"):
            _atomic_write_text_safe(link_path, '{"new": true}\n')

    def test_rejects_preexisting_symlink_tmp_path(self, tmp_path: Path) -> None:
        """If the .tmp path is already a symlink, must raise OSError."""
        target = tmp_path / "config.json"
        evil_tmp = target.with_name("config.json.tmp")
        evil_target = tmp_path / "evil.txt"
        evil_target.write_text("pwned")
        evil_tmp.symlink_to(evil_target)

        with pytest.raises(OSError, match="[Ss]ymlink"):
            _atomic_write_text_safe(target, "safe content\n")

    def test_non_symlink_target_succeeds(self, tmp_path: Path) -> None:
        """Regular file target must work normally."""
        target = tmp_path / "config.json"
        target.write_text("old")
        _atomic_write_text_safe(target, "new content\n")
        assert target.read_text() == "new content\n"


# ---------------------------------------------------------------------------
# _atomic_write_text_safe — basic behavior
# ---------------------------------------------------------------------------


class TestAtomicWriteTextSafeBasic:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c.txt"
        _atomic_write_text_safe(target, "deep\n")
        assert target.read_text() == "deep\n"

    def test_default_mode_is_0o600(self, tmp_path: Path) -> None:
        target = tmp_path / "secret.json"
        _atomic_write_text_safe(target, "{}\n")
        stat = target.stat()
        assert oct(stat.st_mode & 0o777) == oct(0o600)

    def test_custom_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "public.json"
        _atomic_write_text_safe(target, "{}\n", mode=0o644)
        stat = target.stat()
        assert oct(stat.st_mode & 0o777) == oct(0o644)

    def test_cleans_up_tmp_on_write_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "config.json"
        with patch("runtime.mcp_config_writers.os.write", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                _atomic_write_text_safe(target, "data\n")
        tmp_file = target.with_name("config.json.tmp")
        assert not tmp_file.exists(), "tmp file must be cleaned up on failure"


# ---------------------------------------------------------------------------
# _atomic_write_text backward compat delegation
# ---------------------------------------------------------------------------


class TestAtomicWriteTextBackwardCompat:
    def test_delegates_to_safe(self, tmp_path: Path) -> None:
        """_atomic_write_text must delegate to _atomic_write_text_safe."""
        target = tmp_path / "test.json"
        with patch("runtime.mcp_config_writers._atomic_write_text_safe") as m:
            _atomic_write_text(target, "content")
            m.assert_called_once_with(target, "content")


# ---------------------------------------------------------------------------
# _write_json output format invariant
# ---------------------------------------------------------------------------


class TestWriteJsonFormat:
    def test_output_format_is_indent2_plus_trailing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        data: dict[str, object] = {"key": "value", "nested": {"a": 1}}
        _write_json(target, data)
        content = target.read_text()
        expected = json.dumps(data, indent=2) + "\n"
        assert content == expected

    def test_empty_dict_format(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.json"
        _write_json(target, {})
        content = target.read_text()
        assert content == "{}\n"

    def test_trailing_newline_present(self, tmp_path: Path) -> None:
        target = tmp_path / "check.json"
        _write_json(target, {"x": 1})
        content = target.read_text()
        assert content.endswith("\n")
        assert not content.endswith("\n\n")
