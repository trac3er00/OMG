"""Tests for hooks/hashline-formatter-bridge.py — formatter-aware hash cache reconciliation."""

import json
import os
import sys
import tempfile

import pytest
from unittest.mock import patch, MagicMock, mock_open

# Ensure hooks dir is on sys.path for imports
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(HOOKS_DIR))

import importlib

hashline_formatter_bridge = importlib.import_module("hashline-formatter-bridge")

detect_formatter_change = hashline_formatter_bridge.detect_formatter_change
refresh_cache_after_format = hashline_formatter_bridge.refresh_cache_after_format
reconcile_post_format = hashline_formatter_bridge.reconcile_post_format
_is_enabled = hashline_formatter_bridge._is_enabled


# --- Test detect_formatter_change ---


class TestDetectFormatterChange:
    """Tests for detect_formatter_change()."""

    def test_identical_content_returns_false(self):
        assert detect_formatter_change("f.py", "x=1\ny=2", "x=1\ny=2") is False

    def test_different_content_returns_true(self):
        assert detect_formatter_change("f.py", "x=1", "x = 1") is True

    def test_trailing_whitespace_only_returns_false(self):
        """Trailing whitespace stripped before compare."""
        assert detect_formatter_change("f.py", "x=1  \ny=2  ", "x=1\ny=2") is False

    def test_leading_whitespace_change_returns_true(self):
        """Leading whitespace (indentation) changes are real."""
        assert detect_formatter_change("f.py", "x=1", "  x=1") is True

    def test_empty_content_returns_false(self):
        assert detect_formatter_change("f.py", "", "") is False

    def test_added_line_returns_true(self):
        assert detect_formatter_change("f.py", "a\nb", "a\nb\nc") is True

    def test_removed_line_returns_true(self):
        assert detect_formatter_change("f.py", "a\nb\nc", "a\nb") is True

    def test_reordered_lines_returns_true(self):
        assert detect_formatter_change("f.py", "a\nb\nc", "c\nb\na") is True

    def test_trailing_newline_diff_is_structural(self):
        """Trailing newline changes line count — detected as a change."""
        assert detect_formatter_change("f.py", "x=1\n", "x=1") is True

    def test_content_change_within_line_returns_true(self):
        assert detect_formatter_change("f.py", "import os,sys", "import os, sys") is True


# --- Test refresh_cache_after_format ---


class TestRefreshCacheAfterFormat:
    """Tests for refresh_cache_after_format()."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "false"})
    def test_disabled_returns_true(self):
        """When feature is disabled, returns True (skip)."""
        # Force re-evaluation
        assert refresh_cache_after_format("f.py", "x=1") is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_enabled_caches_hashes(self):
        """When enabled, computes hashes and caches them."""
        mock_cache = MagicMock()
        mock_hash = MagicMock(return_value="VK")
        mock_injector = MagicMock()
        mock_injector._line_hash_id = mock_hash
        mock_injector._cache_hashes = mock_cache

        with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
            result = refresh_cache_after_format("f.py", "line1\nline2\nline3")

        assert result is True
        mock_cache.assert_called_once()
        args = mock_cache.call_args
        assert args[0][0] == "f.py"
        assert args[0][1] == {"1": "VK", "2": "VK", "3": "VK"}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_enabled_injector_import_failure(self):
        """Returns False when injector cannot be loaded."""
        with patch.object(hashline_formatter_bridge, "_injector", None):
            with patch("importlib.import_module", side_effect=ImportError("no module")):
                result = refresh_cache_after_format("f.py", "x=1")
        assert result is False

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_enabled_cache_write_failure(self):
        """Returns False when _cache_hashes raises."""
        mock_injector = MagicMock()
        mock_injector._line_hash_id = MagicMock(return_value="ZP")
        mock_injector._cache_hashes = MagicMock(side_effect=OSError("disk full"))

        with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
            result = refresh_cache_after_format("f.py", "x=1")
        assert result is False

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_single_line_content(self):
        """Single line gets hash at key '1'."""
        mock_cache = MagicMock()
        mock_injector = MagicMock()
        mock_injector._line_hash_id = MagicMock(return_value="BH")
        mock_injector._cache_hashes = mock_cache

        with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
            result = refresh_cache_after_format("f.py", "single")

        assert result is True
        args = mock_cache.call_args[0]
        assert args[1] == {"1": "BH"}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_empty_content(self):
        """Empty string still has one empty line."""
        mock_cache = MagicMock()
        mock_injector = MagicMock()
        mock_injector._line_hash_id = MagicMock(return_value="NQ")
        mock_injector._cache_hashes = mock_cache

        with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
            result = refresh_cache_after_format("f.py", "")

        assert result is True
        assert mock_cache.call_args[0][1] == {"1": "NQ"}


# --- Test reconcile_post_format ---


class TestReconcilePostFormat:
    """Tests for reconcile_post_format()."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "false"})
    def test_disabled_returns_skipped(self):
        result = reconcile_post_format("f.py")
        assert result == {"skipped": True}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_file_not_found(self):
        """Non-existent file returns refreshed=False."""
        mock_injector = MagicMock()
        mock_injector._get_cached_hashes = MagicMock(return_value=None)
        mock_injector._line_hash_id = MagicMock(return_value="VK")
        mock_injector._cache_hashes = MagicMock()

        with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
            result = reconcile_post_format("/nonexistent/path/file.py")

        assert result["refreshed"] is False
        assert result["lines_updated"] == 0

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_cache_valid_no_refresh(self):
        """When cache is valid (mtime matches), no refresh needed."""
        mock_injector = MagicMock()
        mock_injector._get_cached_hashes = MagicMock(return_value={"1": "VK"})

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x=1")
            tmp_path = f.name

        try:
            with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
                result = reconcile_post_format(tmp_path)

            assert result["refreshed"] is False
            assert result["lines_updated"] == 0
        finally:
            os.unlink(tmp_path)

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_cache_stale_triggers_refresh(self):
        """When cache returns None (stale mtime), refresh happens."""
        mock_cache = MagicMock()
        mock_injector = MagicMock()
        mock_injector._get_cached_hashes = MagicMock(return_value=None)
        mock_injector._line_hash_id = MagicMock(return_value="BH")
        mock_injector._cache_hashes = mock_cache

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\nline3")
            tmp_path = f.name

        try:
            with patch.object(hashline_formatter_bridge, "_injector", mock_injector):
                result = reconcile_post_format(tmp_path)

            assert result["refreshed"] is True
            assert result["lines_updated"] == 3
            assert result["file"] == tmp_path
            mock_cache.assert_called_once()
        finally:
            os.unlink(tmp_path)

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_injector_import_failure(self):
        """Returns refreshed=False when injector cannot be loaded."""
        with patch.object(hashline_formatter_bridge, "_injector", None):
            with patch("importlib.import_module", side_effect=ImportError("boom")):
                result = reconcile_post_format("f.py")

        assert result["refreshed"] is False


# --- Test _is_enabled ---


class TestIsEnabled:
    """Tests for the _is_enabled feature flag."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_env_true(self):
        assert _is_enabled() is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "false"})
    def test_env_false(self):
        assert _is_enabled() is False

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_env_one(self):
        assert _is_enabled() is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "0"})
    def test_env_zero(self):
        assert _is_enabled() is False

    @patch.dict(os.environ, {}, clear=False)
    def test_default_false(self):
        """When env not set, falls back to get_feature_flag (default False)."""
        env = os.environ.copy()
        env.pop("OAL_HASHLINE_ENABLED", None)
        with patch.dict(os.environ, env, clear=True):
            with patch.object(hashline_formatter_bridge, "get_feature_flag", return_value=False):
                assert _is_enabled() is False


# --- Test main() hook entry point ---


class TestMainHook:
    """Tests for the hook stdin/stdout entry point."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "false"})
    def test_disabled_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            hashline_formatter_bridge.main()
        assert exc_info.value.code == 0

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_non_write_tool_exits_zero(self):
        """Non-write tools are ignored."""
        input_data = {"tool_name": "Read", "tool_input": {"file_path": "f.py"}}
        with patch.object(hashline_formatter_bridge, "json_input", return_value=input_data):
            with pytest.raises(SystemExit) as exc_info:
                hashline_formatter_bridge.main()
        assert exc_info.value.code == 0

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_write_tool_triggers_reconcile(self):
        """Write tool triggers reconcile_post_format."""
        input_data = {"tool_name": "Write", "tool_input": {"file_path": "test.py"}}
        mock_reconcile = MagicMock(return_value={"refreshed": True, "lines_updated": 5, "file": "test.py"})

        with patch.object(hashline_formatter_bridge, "json_input", return_value=input_data):
            with patch.object(hashline_formatter_bridge, "reconcile_post_format", mock_reconcile):
                with pytest.raises(SystemExit) as exc_info:
                    hashline_formatter_bridge.main()

        assert exc_info.value.code == 0
        mock_reconcile.assert_called_once_with("test.py")

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_edit_tool_triggers_reconcile(self):
        """Edit tool also triggers reconcile."""
        input_data = {"tool_name": "Edit", "tool_input": {"file_path": "e.py"}}
        mock_reconcile = MagicMock(return_value={"refreshed": False, "lines_updated": 0, "file": "e.py"})

        with patch.object(hashline_formatter_bridge, "json_input", return_value=input_data):
            with patch.object(hashline_formatter_bridge, "reconcile_post_format", mock_reconcile):
                with pytest.raises(SystemExit) as exc_info:
                    hashline_formatter_bridge.main()

        assert exc_info.value.code == 0
        mock_reconcile.assert_called_once_with("e.py")

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_missing_file_path_exits_zero(self):
        """Missing file_path is gracefully handled."""
        input_data = {"tool_name": "Write", "tool_input": {}}
        with patch.object(hashline_formatter_bridge, "json_input", return_value=input_data):
            with pytest.raises(SystemExit) as exc_info:
                hashline_formatter_bridge.main()
        assert exc_info.value.code == 0

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_invalid_input_exits_zero(self):
        """Non-dict input is gracefully handled."""
        with patch.object(hashline_formatter_bridge, "json_input", return_value="garbage"):
            with pytest.raises(SystemExit) as exc_info:
                hashline_formatter_bridge.main()
        assert exc_info.value.code == 0

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_filePath_camelcase_key(self):
        """Supports camelCase 'filePath' key too."""
        input_data = {"tool_name": "Write", "tool_input": {"filePath": "camel.py"}}
        mock_reconcile = MagicMock(return_value={"refreshed": True, "lines_updated": 1, "file": "camel.py"})

        with patch.object(hashline_formatter_bridge, "json_input", return_value=input_data):
            with patch.object(hashline_formatter_bridge, "reconcile_post_format", mock_reconcile):
                with pytest.raises(SystemExit) as exc_info:
                    hashline_formatter_bridge.main()

        assert exc_info.value.code == 0
        mock_reconcile.assert_called_once_with("camel.py")

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "true"})
    def test_multiedit_tool_triggers_reconcile(self):
        """MultiEdit tool also triggers reconcile."""
        input_data = {"tool_name": "MultiEdit", "tool_input": {"file_path": "m.py"}}
        mock_reconcile = MagicMock(return_value={"refreshed": True, "lines_updated": 10, "file": "m.py"})

        with patch.object(hashline_formatter_bridge, "json_input", return_value=input_data):
            with patch.object(hashline_formatter_bridge, "reconcile_post_format", mock_reconcile):
                with pytest.raises(SystemExit) as exc_info:
                    hashline_formatter_bridge.main()

        assert exc_info.value.code == 0
        mock_reconcile.assert_called_once_with("m.py")
