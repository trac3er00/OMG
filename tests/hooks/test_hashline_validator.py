"""Tests for hooks/hashline-validator.py — hashline validation and cache update."""

import json
import os
import sys
import tempfile

import pytest
from unittest.mock import patch, MagicMock

# Ensure hooks dir is on sys.path for imports
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(HOOKS_DIR))

import importlib

hashline_validator = importlib.import_module("hashline-validator")

validate_edit = hashline_validator.validate_edit
update_hashes_after_edit = hashline_validator.update_hashes_after_edit
validate_line_ref_format = hashline_validator.validate_line_ref_format
_is_enabled = hashline_validator._is_enabled


# --- Test validate_line_ref_format ---


class TestValidateLineRefFormat:
    """Tests for line_ref format validation."""

    def test_valid_format(self):
        assert validate_line_ref_format("11#VK") is True

    def test_valid_single_digit(self):
        assert validate_line_ref_format("1#ZP") is True

    def test_valid_large_line_number(self):
        assert validate_line_ref_format("9999#BH") is True

    def test_valid_all_charset_chars(self):
        """All valid charset pairs should pass."""
        assert validate_line_ref_format("1#ZZ") is True
        assert validate_line_ref_format("1#PM") is True
        assert validate_line_ref_format("1#YH") is True

    def test_invalid_empty_string(self):
        assert validate_line_ref_format("") is False

    def test_invalid_missing_hash(self):
        assert validate_line_ref_format("11VK") is False

    def test_invalid_wrong_charset(self):
        """Characters outside ZPMQVRWSNKTXJBYH should fail."""
        assert validate_line_ref_format("11#AB") is False
        assert validate_line_ref_format("11#CD") is False
        assert validate_line_ref_format("11#EF") is False

    def test_invalid_single_char(self):
        assert validate_line_ref_format("11#V") is False

    def test_invalid_three_chars(self):
        assert validate_line_ref_format("11#VKP") is False

    def test_invalid_lowercase(self):
        assert validate_line_ref_format("11#vk") is False

    def test_invalid_no_line_number(self):
        assert validate_line_ref_format("#VK") is False

    def test_invalid_non_string(self):
        assert validate_line_ref_format(None) is False
        assert validate_line_ref_format(42) is False
        assert validate_line_ref_format(["11#VK"]) is False

    def test_invalid_trailing_content(self):
        assert validate_line_ref_format("11#VK|extra") is False

    def test_invalid_leading_zero(self):
        """Leading zeros in line numbers are still valid digits."""
        assert validate_line_ref_format("01#VK") is True


# --- Test validate_edit (feature flag disabled) ---


class TestValidateEditDisabled:
    """Tests for validate_edit when feature flag is disabled."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "0"})
    def test_disabled_returns_skipped(self):
        result = validate_edit("any_file.py", "11#VK", "some content")
        assert result == {"valid": True, "skipped": True}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "false"})
    def test_disabled_false_string(self):
        result = validate_edit("any.py", "1#ZP", "x")
        assert result["valid"] is True
        assert result["skipped"] is True


# --- Test validate_edit (feature flag enabled) ---


class TestValidateEditEnabled:
    """Tests for validate_edit with feature flag enabled."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_valid_hash_match(self):
        """Hash match returns {valid: True, line: N}."""
        abs_path = os.path.abspath("test_file.py")
        cached = {str(11): "VK", str(12): "PH"}

        # Patch the injector's _get_cached_hashes via the validator's lazy loader
        mock_injector = MagicMock()
        mock_injector._get_cached_hashes.return_value = cached

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            result = validate_edit("test_file.py", "11#VK", "expected content")

        assert result["valid"] is True
        assert result["line"] == 11

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_hash_mismatch(self):
        """Hash mismatch returns {valid: False, error: 'HASH_MISMATCH'}."""
        cached = {"11": "PH", "12": "VK"}

        mock_injector = MagicMock()
        mock_injector._get_cached_hashes.return_value = cached

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            result = validate_edit("test_file.py", "11#VK", "content")

        assert result["valid"] is False
        assert result["error"] == "HASH_MISMATCH"
        assert result["line"] == 11
        assert result["expected"] == "VK"
        assert result["actual"] == "PH"

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_no_cache_returns_uncached(self):
        """When no cache exists for the file, return {valid: True, uncached: True}."""
        mock_injector = MagicMock()
        mock_injector._get_cached_hashes.return_value = None

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            result = validate_edit("new_file.py", "1#ZP", "content")

        assert result["valid"] is True
        assert result["uncached"] is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_line_not_in_cache_returns_uncached(self):
        """When line number is not in cache (file grew), return uncached."""
        cached = {"1": "VK", "2": "PH"}

        mock_injector = MagicMock()
        mock_injector._get_cached_hashes.return_value = cached

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            result = validate_edit("test.py", "99#VK", "content")

        assert result["valid"] is True
        assert result["uncached"] is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_invalid_line_ref_format(self):
        """Invalid line_ref format returns error without cache lookup."""
        result = validate_edit("test.py", "bad_ref", "content")
        assert result["valid"] is False
        assert result["error"] == "INVALID_LINE_REF"
        assert result["line_ref"] == "bad_ref"

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_invalid_line_ref_wrong_charset(self):
        """line_ref with non-charset chars is rejected."""
        result = validate_edit("test.py", "11#AB", "content")
        assert result["valid"] is False
        assert result["error"] == "INVALID_LINE_REF"

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_injector_import_failure_returns_uncached(self):
        """If injector can't be loaded, treat as uncached (fail open)."""
        with patch.object(hashline_validator, "_get_injector", side_effect=ImportError("nope")):
            result = validate_edit("test.py", "1#VK", "content")

        assert result["valid"] is True
        assert result["uncached"] is True


# --- Test update_hashes_after_edit ---


class TestUpdateHashesAfterEdit:
    """Tests for updating cache after an edit."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "0"})
    def test_disabled_returns_true(self):
        assert update_hashes_after_edit("any.py", "content") is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_refreshes_cache_successfully(self):
        """After edit, cache should be updated with new hashes."""
        mock_injector = MagicMock()
        mock_injector._line_hash_id.side_effect = lambda line: "VK"
        mock_injector._cache_hashes.return_value = None

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            result = update_hashes_after_edit("test.py", "line1\nline2\nline3")

        assert result is True
        mock_injector._cache_hashes.assert_called_once()
        call_args = mock_injector._cache_hashes.call_args[0]
        assert call_args[0] == "test.py"
        assert call_args[1] == {"1": "VK", "2": "VK", "3": "VK"}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_correct_line_count_in_cache(self):
        """Cache should have correct number of lines."""
        mock_injector = MagicMock()
        mock_injector._line_hash_id.side_effect = lambda line: "ZP"
        mock_injector._cache_hashes.return_value = None

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            update_hashes_after_edit("test.py", "a\nb\nc\nd\ne")

        call_args = mock_injector._cache_hashes.call_args[0]
        line_hashes = call_args[1]
        assert len(line_hashes) == 5
        assert set(line_hashes.keys()) == {"1", "2", "3", "4", "5"}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_injector_unavailable_returns_false(self):
        """If injector can't be loaded, return False."""
        with patch.object(hashline_validator, "_get_injector", side_effect=ImportError("nope")):
            assert update_hashes_after_edit("test.py", "content") is False

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_cache_write_error_returns_false(self):
        """If cache write raises, return False."""
        mock_injector = MagicMock()
        mock_injector._line_hash_id.side_effect = lambda line: "VK"
        mock_injector._cache_hashes.side_effect = OSError("disk full")

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            assert update_hashes_after_edit("test.py", "content") is False

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_empty_content(self):
        """Empty string split gives [''], so one line."""
        mock_injector = MagicMock()
        mock_injector._line_hash_id.side_effect = lambda line: "ZZ"
        mock_injector._cache_hashes.return_value = None

        with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
            result = update_hashes_after_edit("test.py", "")

        assert result is True
        call_args = mock_injector._cache_hashes.call_args[0]
        assert call_args[1] == {"1": "ZZ"}


# --- Test Feature Flag ---


class TestFeatureFlag:
    """Tests for _is_enabled resolution."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_enabled_env_var(self):
        assert _is_enabled() is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "0"})
    def test_disabled_env_var(self):
        assert _is_enabled() is False

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "yes"})
    def test_enabled_yes(self):
        assert _is_enabled() is True

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "no"})
    def test_disabled_no(self):
        assert _is_enabled() is False

    def test_default_disabled(self):
        """Default should be False per spec."""
        env = os.environ.copy()
        env.pop("OAL_HASHLINE_ENABLED", None)
        with patch.dict(os.environ, env, clear=True):
            with patch.object(hashline_validator, "get_feature_flag", return_value=False):
                assert _is_enabled() is False


# --- Test Hook Entry Point ---


class TestHookEntryPoint:
    """Tests for the stdin/stdout hook entry point."""

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "0"})
    def test_disabled_outputs_skipped(self):
        """When disabled, hook outputs {valid: True, skipped: True}."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            with pytest.raises(SystemExit) as exc_info:
                hashline_validator.main()
            assert exc_info.value.code == 0
        output = json.loads(captured.getvalue())
        assert output == {"valid": True, "skipped": True}

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_valid_input_returns_result(self):
        """Valid input returns validate_edit result."""
        data = {"file_path": "test.py", "line_ref": "1#VK", "expected_line": "hello"}
        mock_injector = MagicMock()
        mock_injector._get_cached_hashes.return_value = {"1": "VK"}

        import io
        captured = io.StringIO()
        with patch.object(hashline_validator, "json_input", return_value=data):
            with patch.object(hashline_validator, "_get_injector", return_value=mock_injector):
                with patch("sys.stdout", captured):
                    with pytest.raises(SystemExit) as exc_info:
                        hashline_validator.main()
                    assert exc_info.value.code == 0

        output = json.loads(captured.getvalue())
        assert output["valid"] is True
        assert output["line"] == 1

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_non_dict_input(self):
        """Non-dict input returns INVALID_INPUT error."""
        import io
        captured = io.StringIO()
        with patch.object(hashline_validator, "json_input", return_value="not a dict"):
            with patch("sys.stdout", captured):
                with pytest.raises(SystemExit) as exc_info:
                    hashline_validator.main()
                assert exc_info.value.code == 0
        output = json.loads(captured.getvalue())
        assert output["valid"] is False
        assert output["error"] == "INVALID_INPUT"

    @patch.dict(os.environ, {"OAL_HASHLINE_ENABLED": "1"})
    def test_always_exits_zero(self):
        """Hook always exits 0 even on errors."""
        data = {"file_path": "", "line_ref": "bad", "expected_line": ""}
        import io
        captured = io.StringIO()
        with patch.object(hashline_validator, "json_input", return_value=data):
            with patch("sys.stdout", captured):
                with pytest.raises(SystemExit) as exc_info:
                    hashline_validator.main()
                assert exc_info.value.code == 0
