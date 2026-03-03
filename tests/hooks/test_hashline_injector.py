"""Tests for hooks/hashline-injector.py — hashline injection and stripping."""

import hashlib
import json
import os
import sys
import tempfile
import time

import pytest
from unittest.mock import patch, MagicMock

# Ensure hooks dir is on sys.path for imports
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(HOOKS_DIR))

# Import with underscore (Python module name)
# The file is hashline-injector.py but importlib handles the dash
import importlib

hashline_injector = importlib.import_module("hashline-injector")

inject_hashlines = hashline_injector.inject_hashlines
strip_hashlines = hashline_injector.strip_hashlines
_line_hash_id = hashline_injector._line_hash_id
_get_cached_hashes = hashline_injector._get_cached_hashes
_cache_hashes = hashline_injector._cache_hashes
_is_enabled = hashline_injector._is_enabled
_load_cache = hashline_injector._load_cache
HASH_CHARSET = hashline_injector.HASH_CHARSET


# --- Test _line_hash_id ---


class TestLineHashId:
    """Tests for the 2-char hash ID generation."""

    def test_returns_two_chars(self):
        result = _line_hash_id("hello world")
        assert len(result) == 2

    def test_chars_from_valid_charset(self):
        result = _line_hash_id("function hello() {")
        assert result[0] in HASH_CHARSET
        assert result[1] in HASH_CHARSET

    def test_deterministic(self):
        """Same input always produces same hash."""
        a = _line_hash_id("const x = 42")
        b = _line_hash_id("const x = 42")
        assert a == b

    def test_different_lines_can_differ(self):
        """Different inputs should generally produce different hashes."""
        # With 256 possible 2-char combos (16*16), collisions are possible
        # but statistically unlikely for very different strings
        hashes = set()
        for i in range(50):
            hashes.add(_line_hash_id(f"unique line number {i}"))
        # At least some should differ (extremely unlikely all 50 collide)
        assert len(hashes) > 1

    def test_empty_line(self):
        result = _line_hash_id("")
        assert len(result) == 2
        assert result[0] in HASH_CHARSET
        assert result[1] in HASH_CHARSET

    def test_hash_uses_sha256_nibble_mapping(self):
        """Verify the hash computation matches expected SHA-256 → nibble logic."""
        line = "test line"
        digest = hashlib.sha256(line.encode("utf-8")).digest()
        first_byte = digest[0]
        high = (first_byte >> 4) & 0x0F
        low = first_byte & 0x0F
        expected = HASH_CHARSET[high] + HASH_CHARSET[low]
        assert _line_hash_id(line) == expected


# --- Test inject_hashlines ---


class TestInjectHashlines:
    """Tests for hashline injection."""

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_adds_correct_line_numbers(self):
        content = "line one\nline two\nline three"
        result = inject_hashlines(content)
        lines = result.split("\n")
        assert lines[0].startswith("1#")
        assert lines[1].startswith("2#")
        assert lines[2].startswith("3#")

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_format_matches_spec(self):
        """Format: {line_num}#{hash_id}|{original_line}"""
        content = "hello world"
        result = inject_hashlines(content)
        # Should match pattern: digit(s) # 2-uppercase-letters | original
        import re
        assert re.match(r"^\d+#[A-Z]{2}\|hello world$", result)

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_preserves_original_content(self):
        content = "  indented\n\ttabbed\n\nempty above"
        result = inject_hashlines(content)
        stripped = strip_hashlines(result)
        assert stripped == content

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_single_line(self):
        content = "only line"
        result = inject_hashlines(content)
        assert result.startswith("1#")
        assert result.endswith("|only line")

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_empty_content(self):
        content = ""
        result = inject_hashlines(content)
        # Empty string split gives [""], so one "line"
        assert result.startswith("1#")

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_multiline_preserves_line_count(self):
        content = "a\nb\nc\nd\ne"
        result = inject_hashlines(content)
        assert len(result.split("\n")) == 5

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_hash_ids_are_valid_charset(self):
        content = "line1\nline2\nline3\nline4\nline5"
        result = inject_hashlines(content)
        for line in result.split("\n"):
            # Extract hash_id between # and |
            hash_part = line.split("#")[1].split("|")[0]
            assert len(hash_part) == 2
            assert hash_part[0] in HASH_CHARSET
            assert hash_part[1] in HASH_CHARSET


# --- Test strip_hashlines ---


class TestStripHashlines:
    """Tests for hashline stripping."""

    def test_strips_hashline_prefix(self):
        tagged = "1#VK|function hello() {"
        result = strip_hashlines(tagged)
        assert result == "function hello() {"

    def test_strips_multiline(self):
        tagged = "1#AB|line one\n2#CD|line two\n3#EF|line three"
        # Note: AB, CD, EF may not be in charset but regex allows [A-Z]{2}
        result = strip_hashlines(tagged)
        assert result == "line one\nline two\nline three"

    def test_roundtrip_inject_strip(self):
        """inject then strip should return original content."""
        original = "const x = 1;\nconst y = 2;\nreturn x + y;"
        with patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"}):
            injected = inject_hashlines(original)
        stripped = strip_hashlines(injected)
        assert stripped == original

    def test_no_prefix_passes_through(self):
        """Lines without hashline prefix pass through unchanged."""
        content = "no prefix here\nalso no prefix"
        result = strip_hashlines(content)
        assert result == content

    def test_preserves_pipe_in_content(self):
        """Pipe characters in original content should not be affected."""
        with patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"}):
            original = "a | b | c"
            injected = inject_hashlines(original)
            stripped = strip_hashlines(injected)
            assert stripped == original

    def test_large_line_numbers(self):
        """Strip works with multi-digit line numbers."""
        tagged = "999#ZZ|some content\n1000#PP|more content"
        result = strip_hashlines(tagged)
        assert result == "some content\nmore content"


# --- Test Feature Flag ---


class TestFeatureFlag:
    """Tests for OMG_HASHLINE_ENABLED feature flag."""

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "0"})
    def test_disabled_returns_passthrough(self):
        content = "hello\nworld"
        result = inject_hashlines(content)
        assert result == content  # No modification

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "false"})
    def test_disabled_false_string(self):
        content = "test content"
        result = inject_hashlines(content)
        assert result == content

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_enabled_injects(self):
        content = "test content"
        result = inject_hashlines(content)
        assert result != content
        assert result.startswith("1#")

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "yes"})
    def test_enabled_yes_string(self):
        content = "test"
        result = inject_hashlines(content)
        assert result.startswith("1#")

    @patch.dict(os.environ, {}, clear=False)
    def test_default_disabled(self):
        """Default should be False (disabled) per spec."""
        # Remove env var if set
        env = os.environ.copy()
        env.pop("OMG_HASHLINE_ENABLED", None)
        with patch.dict(os.environ, env, clear=True):
            # get_feature_flag with default=False should return False
            with patch.object(hashline_injector, "get_feature_flag", return_value=False):
                assert not _is_enabled()


# --- Test Sidecar Cache ---


class TestSidecarCache:
    """Tests for hashline sidecar cache (.omg/state/hashline_cache.json)."""

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_cache_stores_on_inject(self):
        """When file_path provided, hashes should be cached."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("hello\nworld")
            tmp_path = f.name

        try:
            with patch.object(hashline_injector, "atomic_json_write") as mock_write:
                with patch.object(hashline_injector, "_load_cache", return_value={}):
                    inject_hashlines("hello\nworld", tmp_path)
                    assert mock_write.called
                    # Verify cache data structure
                    call_args = mock_write.call_args
                    cache_data = call_args[0][1]
                    abs_path = os.path.abspath(tmp_path)
                    assert abs_path in cache_data
                    entry = cache_data[abs_path]
                    assert "mtime" in entry
                    assert "line_hashes" in entry
                    assert "1" in entry["line_hashes"]
                    assert "2" in entry["line_hashes"]
        finally:
            os.unlink(tmp_path)

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_cache_retrieves_valid(self):
        """Cached hashes should be returned when mtime matches."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("hello\nworld")
            tmp_path = f.name

        try:
            abs_path = os.path.abspath(tmp_path)
            mtime = os.path.getmtime(abs_path)
            cached_data = {
                abs_path: {
                    "mtime": mtime,
                    "line_hashes": {"1": "ZZ", "2": "PP"},
                }
            }
            with patch.object(hashline_injector, "_load_cache", return_value=cached_data):
                result = _get_cached_hashes(tmp_path)
                assert result is not None
                assert result["1"] == "ZZ"
                assert result["2"] == "PP"
        finally:
            os.unlink(tmp_path)

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_cache_invalidation_on_mtime_change(self):
        """Cache should be invalidated when file mtime changes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("hello\nworld")
            tmp_path = f.name

        try:
            abs_path = os.path.abspath(tmp_path)
            # Set cached mtime to something different
            cached_data = {
                abs_path: {
                    "mtime": 0.0,  # Very old mtime
                    "line_hashes": {"1": "ZZ", "2": "PP"},
                }
            }
            with patch.object(hashline_injector, "_load_cache", return_value=cached_data):
                result = _get_cached_hashes(tmp_path)
                assert result is None  # Should be invalidated

        finally:
            os.unlink(tmp_path)

    def test_cache_returns_none_for_missing_file(self):
        """Cache lookup for non-existent file returns None."""
        result = _get_cached_hashes("/nonexistent/file.py")
        assert result is None

    def test_cache_returns_none_for_uncached_file(self):
        """Cache lookup for file not in cache returns None."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("content")
            tmp_path = f.name

        try:
            with patch.object(hashline_injector, "_load_cache", return_value={}):
                result = _get_cached_hashes(tmp_path)
                assert result is None
        finally:
            os.unlink(tmp_path)

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_cache_hashes_writes_correctly(self):
        """_cache_hashes should write correct structure via atomic_json_write."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test")
            tmp_path = f.name

        try:
            line_hashes = {"1": "VK", "2": "PH"}
            with patch.object(hashline_injector, "atomic_json_write") as mock_write:
                with patch.object(hashline_injector, "_load_cache", return_value={}):
                    _cache_hashes(tmp_path, line_hashes)
                    assert mock_write.called
                    data = mock_write.call_args[0][1]
                    abs_path = os.path.abspath(tmp_path)
                    assert data[abs_path]["line_hashes"] == line_hashes
                    assert isinstance(data[abs_path]["mtime"], float)
        finally:
            os.unlink(tmp_path)


# --- Test Performance ---


class TestPerformance:
    """Performance tests — injection must complete within budget."""

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_1000_lines_under_20ms(self):
        """1000-line file injection should complete in < 20ms."""
        content = "\n".join(f"line {i}: some typical code content here" for i in range(1000))

        # Warm up
        inject_hashlines(content)

        # Measure
        start = time.perf_counter()
        for _ in range(10):
            inject_hashlines(content)
        elapsed_ms = (time.perf_counter() - start) / 10 * 1000

        assert elapsed_ms < 20, f"Injection took {elapsed_ms:.1f}ms, budget is 20ms"

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_strip_1000_lines_under_20ms(self):
        """1000-line strip should complete in < 20ms."""
        content = "\n".join(f"line {i}: some code" for i in range(1000))
        injected = inject_hashlines(content)

        start = time.perf_counter()
        for _ in range(10):
            strip_hashlines(injected)
        elapsed_ms = (time.perf_counter() - start) / 10 * 1000

        assert elapsed_ms < 20, f"Strip took {elapsed_ms:.1f}ms, budget is 20ms"


# --- Test Hook Entry Point ---


class TestHookEntryPoint:
    """Tests for the stdin/stdout hook entry point."""

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "0"})
    def test_disabled_exits_immediately(self):
        """When disabled, hook should exit 0 without processing."""
        with pytest.raises(SystemExit) as exc_info:
            hashline_injector.main()
        assert exc_info.value.code == 0

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_non_read_tool_exits(self):
        """Non-read tools should be ignored."""
        data = {"tool_name": "Write", "tool_input": {"content": "test"}}
        with patch.object(hashline_injector, "json_input", return_value=data):
            with pytest.raises(SystemExit) as exc_info:
                hashline_injector.main()
            assert exc_info.value.code == 0

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_read_tool_injects(self):
        """Read tool with content should inject hashlines."""
        data = {
            "tool_name": "Read",
            "tool_input": {"content": "hello\nworld", "file_path": "test.py"},
        }
        captured = {}

        def mock_dump(obj, fp):
            captured["output"] = obj

        with patch.object(hashline_injector, "json_input", return_value=data):
            with patch("json.dump", side_effect=mock_dump):
                with pytest.raises(SystemExit):
                    hashline_injector.main()

        assert "output" in captured
        output_content = captured["output"]["tool_input"]["content"]
        assert output_content.startswith("1#")

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_empty_content_exits(self):
        """Empty content should exit without injecting."""
        data = {"tool_name": "Read", "tool_input": {"content": ""}}
        with patch.object(hashline_injector, "json_input", return_value=data):
            with pytest.raises(SystemExit) as exc_info:
                hashline_injector.main()
            assert exc_info.value.code == 0


# --- Test Edge Cases ---


class TestEdgeCases:
    """Edge case tests."""

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_unicode_content(self):
        content = "안녕하세요\nこんにちは\n🎉"
        result = inject_hashlines(content)
        stripped = strip_hashlines(result)
        assert stripped == content

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_content_with_existing_hash_pattern(self):
        """Content that looks like a hashline should still be handled correctly."""
        content = "1#VK|already tagged"
        result = inject_hashlines(content)
        # Should inject on top of existing content
        assert result.startswith("1#")
        stripped = strip_hashlines(result)
        # Strip should remove the OUTER prefix, leaving the original
        assert stripped == content

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_very_long_line(self):
        content = "x" * 10000
        result = inject_hashlines(content)
        assert result.startswith("1#")
        stripped = strip_hashlines(result)
        assert stripped == content

    @patch.dict(os.environ, {"OMG_HASHLINE_ENABLED": "1"})
    def test_inject_without_file_path_no_cache(self):
        """Injecting without file_path should not attempt cache."""
        with patch.object(hashline_injector, "_cache_hashes") as mock_cache:
            inject_hashlines("test")
            mock_cache.assert_not_called()

    def test_charset_has_16_unique_chars(self):
        """HASH_CHARSET must have exactly 16 unique characters."""
        assert len(HASH_CHARSET) == 16
        assert len(set(HASH_CHARSET)) == 16

    def test_all_charset_chars_are_uppercase(self):
        """All chars in HASH_CHARSET should be uppercase letters."""
        for c in HASH_CHARSET:
            assert c.isupper() and c.isalpha()
