"""Tests for omg_natives — Rust bindings with Python fallbacks.

Verifies:
- Module imports cleanly
- Attributes (RUST_AVAILABLE, OMG_RUST_ENABLED) exist
- Python fallback functions work without Rust compiled
- Cargo.toml and src/lib.rs exist on disk
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate project root (two levels up from tests/performance/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestOalNativesImport:
    """Verify the omg_natives package loads and exposes expected attrs."""

    def test_module_importable(self):
        """omg_natives should be importable without error."""
        import omg_natives  # noqa: F401

    def test_rust_available_attr_exists(self):
        """omg_natives.RUST_AVAILABLE must exist and be a bool."""
        import omg_natives

        assert hasattr(omg_natives, "RUST_AVAILABLE")
        assert isinstance(omg_natives.RUST_AVAILABLE, bool)

    def test_omg_rust_enabled_attr_exists(self):
        """omg_natives.OMG_RUST_ENABLED must exist and be a bool."""
        import omg_natives

        assert hasattr(omg_natives, "OMG_RUST_ENABLED")
        assert isinstance(omg_natives.OMG_RUST_ENABLED, bool)


class TestPythonFallbacks:
    """Verify pure-Python fallback implementations work correctly."""

    def test_grep_fallback_works(self, tmp_path):
        """grep() should find lines matching a pattern in a file."""
        import omg_natives

        sample = tmp_path / "sample.txt"
        sample.write_text("hello world\nfoo bar\nhello again\n")

        results = omg_natives.grep("hello", str(sample))
        assert isinstance(results, list)
        assert len(results) == 2
        assert "hello world" in results
        assert "hello again" in results

    def test_glob_fallback_works(self, tmp_path):
        """glob_match() should find files matching a pattern."""
        import omg_natives

        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.py").write_text("z")

        results = omg_natives.glob_match("*.py", str(tmp_path))
        assert isinstance(results, list)
        # Should find a.py at top level
        assert "a.py" in results

    def test_flag_disabled_by_default(self, monkeypatch):
        """RUST_AVAILABLE should be False when Rust is not compiled."""
        import omg_natives

        # Without the compiled .so, RUST_AVAILABLE must be False
        assert omg_natives.RUST_AVAILABLE is False

    def test_normalize_fallback(self):
        """normalize() should strip and normalize line endings."""
        import omg_natives

        assert omg_natives.normalize("  hello\r\nworld  ") == "hello\nworld"

    def test_strip_tags_fallback(self):
        """strip_tags() should remove HTML tags."""
        import omg_natives

        assert omg_natives.strip_tags("<p>hello</p>") == "hello"
        assert omg_natives.strip_tags("<b>bold</b> text") == "bold text"


class TestRustStructure:
    """Verify Rust project files exist on disk."""

    def test_cargo_toml_exists(self):
        """Cargo.toml must exist in crates/omg-natives/."""
        cargo = PROJECT_ROOT / "crates" / "omg-natives" / "Cargo.toml"
        assert cargo.exists(), f"Missing: {cargo}"
        content = cargo.read_text()
        assert 'name = "omg-natives"' in content
        assert "pyo3" in content

    def test_lib_rs_exists(self):
        """src/lib.rs must exist with pymodule entry point."""
        lib_rs = PROJECT_ROOT / "crates" / "omg-natives" / "src" / "lib.rs"
        assert lib_rs.exists(), f"Missing: {lib_rs}"
        content = lib_rs.read_text()
        assert "#[pymodule]" in content
        assert "pub mod grep" in content

    def test_all_module_stubs_exist(self):
        """All 12 module stub .rs files must exist."""
        src = PROJECT_ROOT / "crates" / "omg-natives" / "src"
        expected = [
            "grep.rs", "shell.rs", "text.rs", "keys.rs",
            "highlight.rs", "glob.rs", "task.rs", "ps.rs",
            "prof.rs", "image.rs", "clipboard.rs", "html.rs",
        ]
        for name in expected:
            path = src / name
            assert path.exists(), f"Missing module stub: {path}"
            content = path.read_text()
            assert "placeholder" in content or "#[pyfunction]" in content
